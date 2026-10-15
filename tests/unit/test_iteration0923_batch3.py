import datetime
import uuid
from decimal import Decimal
import unittest
from starlette.testclient import TestClient

from src.ai_wrapper.invoice.models import ExtractedTaiwanInvoice
from src.ai_wrapper.invoice.service import InvoiceIntakeService
from src.channel_ui.web.app import app
from src.core.adapters.mock_invoice_adapter import MockInvoiceProvider
from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter, ShippingLabelData
from src.core.ports.invoice_port import IssueInvoiceRequest
from src.core.domain.invoice import TaxType
from src.extended_core.crm.documents.quote_document_engine import QuoteDocumentEngine
from src.extended_core.crm.models import Contact, Deal, DealStage, Quote, QuoteStatus
from src.shared.database import Database
from src.shared.text_utils import to_half_width


class TestIteration0923Batch3(unittest.TestCase):
    """Comprehensive test suite for Batch 3:
    1. Accounting settlement modal double-check & payment account selection.
    2. Incoming invoice dupe checking & prevention.
    3. Universal PDF text half-width normalization.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.db: Database = app.state.db

    def test_to_half_width_normalization(self):
        # 1. Full-width numbers & English
        self.assertEqual(to_half_width("１２３４５６７８９０"), "1234567890")
        self.assertEqual(to_half_width("ＡＢＣＤＥＦＧａｂｃ"), "ABCDEFGabc")

        # 2. Chinese full-width punctuation
        input_text = "【測試】（台北市：信義區，１段２號；有效～確認！）"
        expected = "[測試](台北市:信義區,1段2號;有效~確認!)"
        self.assertEqual(to_half_width(input_text), expected)

        # 3. Quotes and dashes
        self.assertEqual(to_half_width("“報價單”—『契約』"), '"報價單"-『契約』')

        # 4. None and empty
        self.assertEqual(to_half_width(None), "")
        self.assertEqual(to_half_width(""), "")

        # 5. Pure Chinese characters preserved
        self.assertEqual(to_half_width("三圓科技股份有限公司"), "三圓科技股份有限公司")

    def test_settle_modal_endpoints_return_correct_html(self):
        # 1. Test AR modal
        with self.db.transaction() as conn:
            ar_row = conn.execute(
                "SELECT ar_id FROM accounts_receivable WHERE status != 'PAID' LIMIT 1"
            ).fetchone()
            if not ar_row:
                so = conn.execute("SELECT order_id, customer_id FROM sales_orders LIMIT 1").fetchone()
                inv = conn.execute("SELECT invoice_id FROM invoices LIMIT 1").fetchone()
                ar_id = f"AR-TEST-{uuid.uuid4().hex[:6]}"
                conn.execute(
                    """
                    INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                    VALUES (?, ?, ?, ?, '2026-10-31', 5000, 0, 'UNPAID')
                    """,
                    (ar_id, so["order_id"], inv["invoice_id"], so["customer_id"]),
                )
            else:
                ar_id = ar_row["ar_id"]

        resp_ar = self.client.get(f"/accounting/ar/{ar_id}/settle-modal")
        self.assertEqual(resp_ar.status_code, 200)
        self.assertIn("settle-confirm-modal", resp_ar.text)
        self.assertIn("應收帳款沖銷收款確認", resp_ar.text)
        self.assertIn(f'action="/accounting/ar/{ar_id}/settle"', resp_ar.text.replace("hx-post=", "action="))
        self.assertIn("1101 - 現金", resp_ar.text)
        self.assertIn("1102 - 銀行存款", resp_ar.text)
        self.assertIn("1144 應收帳款", resp_ar.text)

        # 2. Test AP modal
        with self.db.transaction() as conn:
            ap_row = conn.execute(
                "SELECT ap_id FROM accounts_payable WHERE status != 'PAID' LIMIT 1"
            ).fetchone()
            if not ap_row:
                po = conn.execute("SELECT po_id, supplier_name FROM purchase_orders LIMIT 1").fetchone()
                ap_id = f"AP-TEST-{uuid.uuid4().hex[:6]}"
                conn.execute(
                    """
                    INSERT INTO accounts_payable (ap_id, po_id, supplier_name, due_date, amount, paid_amount, status)
                    VALUES (?, ?, ?, '2026-10-31', 8000, 0, 'UNPAID')
                    """,
                    (ap_id, po["po_id"], po["supplier_name"]),
                )
            else:
                ap_id = ap_row["ap_id"]

        resp_ap = self.client.get(f"/accounting/ap/{ap_id}/settle-modal")
        self.assertEqual(resp_ap.status_code, 200)
        self.assertIn("settle-confirm-modal", resp_ap.text)
        self.assertIn("應付帳款沖銷付款確認", resp_ap.text)
        self.assertIn(f'action="/accounting/ap/{ap_id}/settle"', resp_ap.text.replace("hx-post=", "action="))
        self.assertIn("2144 應付帳款", resp_ap.text)

    def test_settle_endpoints_with_payment_account_and_toast(self):
        # 1. Test AR settlement with bank deposit (1102)
        ar_id = f"AR-TEST-BANK-{uuid.uuid4().hex[:6]}"
        with self.db.transaction() as conn:
            so = conn.execute("SELECT order_id, customer_id FROM sales_orders LIMIT 1").fetchone()
            inv = conn.execute("SELECT invoice_id FROM invoices LIMIT 1").fetchone()
            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES (?, ?, ?, ?, '2026-10-31', 12000, 0, 'UNPAID')
                """,
                (ar_id, so["order_id"], inv["invoice_id"], so["customer_id"]),
            )

        resp_ar = self.client.post(
            f"/accounting/ar/{ar_id}/settle",
            data={"payment_account": "1102", "amount": "12000"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp_ar.status_code, 200)
        self.assertIn("已成功沖銷結清應收帳款", resp_ar.text)
        self.assertIn("1102 銀行存款", resp_ar.text)
        self.assertIn("accounting-container", resp_ar.text)

        # Check DB journal entry and AR status
        with self.db.transaction() as conn:
            ar_check = conn.execute("SELECT status, paid_amount FROM accounts_receivable WHERE ar_id = ?", (ar_id,)).fetchone()
            self.assertEqual(ar_check["status"], "PAID")
            self.assertEqual(float(ar_check["paid_amount"]), 12000.0)

            # Check journal lines: Dr 1102, Cr 1144
            entry = conn.execute("SELECT entry_id FROM journal_entries WHERE reference_id = ?", (ar_id,)).fetchone()
            lines = conn.execute("SELECT account_code, debit, credit FROM journal_lines WHERE entry_id = ?", (entry["entry_id"],)).fetchall()
            dr_line = next(l for l in lines if l["account_code"] == "1102")
            cr_line = next(l for l in lines if l["account_code"] == "1144")
            self.assertEqual(float(dr_line["debit"]), 12000.0)
            self.assertEqual(float(cr_line["credit"]), 12000.0)

        # 2. Test AP settlement with cash (1101)
        ap_id = f"AP-TEST-CASH-{uuid.uuid4().hex[:6]}"
        with self.db.transaction() as conn:
            po = conn.execute("SELECT po_id, supplier_name FROM purchase_orders LIMIT 1").fetchone()
            conn.execute(
                """
                INSERT INTO accounts_payable (ap_id, po_id, supplier_name, due_date, amount, paid_amount, status)
                VALUES (?, ?, ?, '2026-10-31', 6500, 0, 'UNPAID')
                """,
                (ap_id, po["po_id"], po["supplier_name"]),
            )

        resp_ap = self.client.post(
            f"/accounting/ap/{ap_id}/settle",
            data={"payment_account": "1101", "amount": "6500"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp_ap.status_code, 200)
        self.assertIn("已成功沖銷支付應付帳款", resp_ap.text)
        self.assertIn("1101 現金", resp_ap.text)

        with self.db.transaction() as conn:
            ap_check = conn.execute("SELECT status, paid_amount FROM accounts_payable WHERE ap_id = ?", (ap_id,)).fetchone()
            self.assertEqual(ap_check["status"], "PAID")
            self.assertEqual(float(ap_check["paid_amount"]), 6500.0)

    def test_invoice_dupe_check_and_prevention(self):
        inv_num = f"AB-{uuid.uuid4().hex[:8].upper()}"
        invoice = ExtractedTaiwanInvoice(
            invoice_number=inv_num,
            seller_name="極客電子零件專賣店",
            seller_tax_id="12345678",
            sales_amount=Decimal("10000"),
            tax_amount=Decimal("500"),
            total_amount=Decimal("10500"),
        )
        intake_service = InvoiceIntakeService(db=self.db)

        # 1. First check: should be NEW (not recorded)
        result1 = intake_service.match_invoice(invoice)
        self.assertIn(result1.status, ["NEW", "MATCHED_PO"])

        # 2. Ingest into AP
        ap_id = intake_service.create_ap_from_invoice(invoice)
        self.assertTrue(ap_id.startswith("AP-"))

        # 3. Second check: should detect duplicate
        result2 = intake_service.match_invoice(invoice)
        self.assertEqual(result2.status, "ALREADY_RECORDED")
        self.assertEqual(result2.existing_ap_id, ap_id)

        # 4. Attempting to ingest the same invoice again must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            intake_service.create_ap_from_invoice(invoice)
        self.assertIn(f"發票號碼 {inv_num} 已經於系統中註冊入帳，嚴禁重複登記", str(ctx.exception))

        # 5. Web endpoint test: re-posting must return 400
        web_resp = self.client.post(
            "/ai/invoice/confirm-ap",
            data={
                "invoice_number": inv_num,
                "seller_name": "極客電子零件專賣店",
                "seller_tax_id": "12345678",
                "total_amount": "10500",
                "sales_amount": "10000",
                "tax_amount": "500",
            },
        )
        self.assertEqual(web_resp.status_code, 400)
        self.assertIn("嚴禁重複登記", web_resp.text)

    def test_pdf_generation_with_fullwidth_inputs(self):
        # 1. Quote PDF with full-width characters in metadata
        contact = Contact(
            contact_id="CUST-FW-01",
            company_name="宏達電（台灣）股份有限公司",
            contact_name="王小明（專案副理）",
            tax_id="１２３４５６７８",
            phone="０９１２－３４５－６７８",
            email="test＠example.com",
        )
        deal = Deal(
            deal_id="DEAL-FW-01",
            contact_id=contact.contact_id,
            title="２０２６年度企業採購專案（第一期）",
            stage=DealStage.PROPOSAL,
        )
        quote = Quote(
            quote_id="QT-FW-01",
            quote_number="QT-FW-01",
            deal_id=deal.deal_id,
            status=QuoteStatus.ACCEPTED,
            valid_until=datetime.date.today() + datetime.timedelta(days=30),
        )
        items_detail = [
            {"sku": "SKU-PRO-01", "name": "智慧旗艦終端機（標準版）", "qty": 2, "unit_price": 5000, "subtotal": 10000}
        ]
        quote_pdf = QuoteDocumentEngine.generate_pdf(contact, deal, quote, items_detail)
        self.assertTrue(quote_pdf.startswith(b"%PDF"))
        self.assertGreater(len(quote_pdf), 1000)

        # 2. Shipping Label PDF with full-width characters
        printer = PdfPrinterAdapter()
        label_data = ShippingLabelData(
            tracking_number="ＴＲＫ－９９８８７７",
            order_id="ＳＯ－１２３４５",
            do_id="ＤＯ－６７８９０",
            recipient_name="陳大華（收）",
            recipient_phone="０９８８－１１２２３３",
            shipping_address="台北市信義區（東側）信義路１００號（８樓）",
        )
        label_pdf = printer.generate_shipping_label_pdf(label_data)
        self.assertTrue(label_pdf.startswith(b"%PDF"))
        self.assertGreater(len(label_pdf), 500)

        # A4 multi-label
        a4_pdf = printer.generate_a4_shipping_labels_pdf([label_data], layout="2x2", start_position=1)
        self.assertTrue(a4_pdf.startswith(b"%PDF"))
        self.assertGreater(len(a4_pdf), 500)

        # Barcode
        barcode_pdf = printer.generate_barcode_label_pdf("ＳＫＵ－００１", "產品名稱（高階型）")
        self.assertTrue(barcode_pdf.startswith(b"%PDF"))
        self.assertGreater(len(barcode_pdf), 500)

        # 3. Invoice PDF
        invoice_provider = MockInvoiceProvider(seller_tax_id="８８８８８８８８", seller_name="三圓科技（股）公司")
        inv = invoice_provider.issue_invoice(
            IssueInvoiceRequest(
                order_id="SO-INV-01",
                total_amount=Decimal("5250"),
                tax_type=TaxType.TAXABLE,
                buyer_tax_id="１２３４５６７８",
                buyer_name="測試買方（公司）",
            )
        )
        inv_pdf = invoice_provider.render_invoice_pdf(inv)
        self.assertTrue(inv_pdf.startswith(b"%PDF"))
        self.assertGreater(len(inv_pdf), 500)


if __name__ == "__main__":
    unittest.main()
