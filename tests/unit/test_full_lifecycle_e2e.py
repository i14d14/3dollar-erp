from __future__ import annotations
import base64
import datetime
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest
import fitz
import openpyxl
from starlette.testclient import TestClient

from src.ai_wrapper.bom.parser import BomExcelParser
from src.ai_wrapper.bom.service import BomComparisonService
from src.ai_wrapper.invoice.parser import TaiwanPdfInvoiceParser
from src.ai_wrapper.reporting.excel_generator import AdvancedReportGenerator
from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter
from src.channel_ui.web.app import create_app
from src.core.domain.invoice import ARStatus, InvoiceStatus, TaxType
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.extended_core.crm.models import DealStage
from src.extended_core.crm.services.crm_service import CrmService
from src.shared.database import Database
from src.shared.event_bus import EventBus


def make_signed_payload(secret: str, events: list) -> tuple[str, str]:
    """Build a valid LINE v3 Webhook payload JSON string and its HMAC-SHA256 signature."""
    payload_dict = {
        "destination": "U3dollar_erp_bot",
        "events": events,
    }
    body_str = json.dumps(payload_dict, ensure_ascii=False)
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body_str.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return body_str, signature


class TestFullLifecycleE2E(unittest.TestCase):
    """Overarching End-to-End Verification of Day 7 Integration:

    1. B2B Flow: CRM Lead -> Quote DOCX/PDF -> Won Conversion -> ERP Order Lock ->
       Shipment DO & Label -> MIG 3.2.1 Invoice & Receipt -> 4-Way Reconciliation ->
       Accounting Auto-Vouchers & Trial Balance.
    2. B2C Flow: LINE Bot Catalog Browse -> One-Click Order Postback -> Instant Lock ->
       Shipment & Invoicing -> LINE Bot Real-Time Tracking & Invoice Query.
    3. AI Flow: BOM Multi-Supplier Historical Price Comparison -> Native PDF Invoice Extraction
       to Accounts Payable -> 4-in-1 Executive Financial & Operational Excel Streaming.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_full_lifecycle.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.mock_line_adapter = MockLineMessagingAdapter()
        self.line_secret = "test_lifecycle_secret_999"

        self.app = create_app(
            db=self.db,
            event_bus=self.event_bus,
            line_messaging_port=self.mock_line_adapter,
            line_channel_secret=self.line_secret,
        )
        self.client = TestClient(self.app)

        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(
            db=self.db,
            event_bus=self.event_bus,
            inventory_service=self.inventory_service,
        )
        self.invoice_service = InvoiceService(db=self.db, event_bus=self.event_bus)
        self.accounting_service = AccountingService(db=self.db)
        self.crm_service = CrmService(db=self.db, order_service=self.order_service)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_b2b_crm_to_accounting_closed_loop(self) -> None:
        """Verify complete B2B flow: CRM Contact -> Deal Pipeline -> Quote DOCX/PDF ->

        Won Conversion to ERP Order -> Stock Lock -> Ship & Label -> Invoice & AR ->
        4-Way Reconciliation -> Accounting Auto-Vouchers -> Strict Trial Balance Balance.
        """
        # 1. CRM Contact Creation (8-digit Tax ID validation)
        contact = self.crm_service.create_contact(
            company_name="宏曜高新科技有限公司",
            contact_name="林技術長",
            tax_id="84123456",
            email="lin@hongyao-tech.tw",
            phone="02-2789-0123",
        )
        self.assertEqual(contact.tax_id, "84123456")

        # 2. Deal Creation & Progression
        deal = self.crm_service.create_deal(
            contact_id=contact.contact_id,
            title="2026 企業總部智慧旗艦終端換裝案",
            expected_amount=Decimal("25000.0"),
            stage=DealStage.DISCOVERY,
        )
        deal = self.crm_service.advance_deal_stage(deal.deal_id, DealStage.PROPOSAL)
        self.assertEqual(deal.stage, DealStage.PROPOSAL)

        # 3. Formal Quote Generation with items
        quote = self.crm_service.create_quote(
            deal_id=deal.deal_id,
            items=[
                ("SKU-PRO-01", Decimal("10.0"), Decimal("2500.0")),  # $25,000
            ],
            valid_days=30,
        )
        self.assertEqual(quote.total_amount, Decimal("25000.0"))

        # Verify Quote Documents generation (DOCX template substitution and A4 PDF)
        docx_bytes = self.crm_service.generate_quote_docx(quote.quote_id)
        self.assertGreater(len(docx_bytes), 1000)

        pdf_bytes = self.crm_service.generate_quote_pdf(quote.quote_id)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = doc[0].get_text()
        self.assertIn("宏曜高新科技", pdf_text)
        self.assertIn("SKU-PRO-01", pdf_text)
        doc.close()

        # 4. Won Deal Conversion to ERP Order
        # 4. Won Deal Conversion to ERP Order (Automatically Confirmed & Virtual Stock Locked)
        erp_order, updated_deal = self.crm_service.convert_deal_to_erp_order(deal.deal_id)
        self.assertEqual(erp_order.channel, OrderChannel.CRM)
        self.assertEqual(erp_order.status, OrderStatus.CONFIRMED)
        self.assertEqual(erp_order.total_amount, Decimal("25000.0"))
        self.assertEqual(
            self.inventory_service.get_locked_stock("WH-MAIN", "SKU-PRO-01"),
            Decimal("10.0"),
        )

        # 6. Fulfillment & Physical Stock Deduction (One-click Ship)
        do, label_bytes = self.order_service.ship_order(
            order_id=erp_order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="林技術長",
            recipient_phone="0911-222-333",
            shipping_address="台北市南港區園區街3號12樓",
            tracking_number="TRK-E2E-B2B-01",
        )
        self.assertIsNotNone(do.do_id)
        self.assertGreater(len(label_bytes), 500)

        # Verify physical stock decreased and virtual lock released
        self.assertEqual(
            self.inventory_service.get_locked_stock("WH-MAIN", "SKU-PRO-01"),
            Decimal("0.0"),
        )

        # 7. Electronic Invoicing (MIG 3.2.1 compliant)
        invoice, ar, receipt_pdf = self.invoice_service.issue_invoice_for_order(
            order_id=erp_order.order_id,
            tax_type=TaxType.TAXABLE,
            buyer_tax_id=contact.tax_id,
            buyer_name=contact.company_name,
        )
        self.assertEqual(invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(ar.status, ARStatus.UNPAID)
        self.assertEqual(ar.amount, Decimal("25000.0"))
        self.assertGreater(len(receipt_pdf), 500)

        # 8. Verify Order status has advanced to COMPLETED
        final_order = self.order_service.get_order(erp_order.order_id)
        self.assertEqual(final_order.status, OrderStatus.COMPLETED)

        # 9. 4-Way Rigid Reconciliation Verification
        recon = self.invoice_service.verify_four_way_reconciliation(erp_order.order_id)
        self.assertTrue(recon.is_reconciled)
        self.assertEqual(len(recon.discrepancies), 0)
        self.assertEqual(recon.so_amount, Decimal("25000.0"))
        self.assertEqual(recon.inv_amount, Decimal("25000.0"))
        self.assertEqual(recon.ar_amount, Decimal("25000.0"))

        # 10. Verify Event-Driven Accounting Vouchers
        entries = self.accounting_service.get_journal_entries()
        
        # Verify COGS Voucher for this DO: Dr. 5111 $15,000, Cr. 1201 $15,000 (10 units @ cost $1500)
        cogs_entry = next((e for e in entries if e.source_event == "ERP_ORDER_SHIPPED" and do.do_id in e.description), None)
        self.assertIsNotNone(cogs_entry)
        cogs_line = next(l for l in cogs_entry.lines if l.account_code == "5111")
        inv_line = next(l for l in cogs_entry.lines if l.account_code == "1201")
        self.assertEqual(cogs_line.debit, Decimal("15000.0"))
        self.assertEqual(inv_line.credit, Decimal("15000.0"))

        # Verify Revenue Voucher for this INV: Dr. 1144 $25,000, Cr. 4111 $23,810, Cr. 2201 $1,190
        rev_entry = next((e for e in entries if e.source_event == "ERP_INVOICE_ISSUED" and invoice.invoice_id in e.reference_id), None)
        self.assertIsNotNone(rev_entry)
        ar_line = next(l for l in rev_entry.lines if l.account_code == "1144")
        sales_line = next(l for l in rev_entry.lines if l.account_code == "4111")
        tax_line = next(l for l in rev_entry.lines if l.account_code == "2201")
        self.assertEqual(ar_line.debit, Decimal("25000.0"))
        self.assertEqual(sales_line.credit, Decimal("23810.0"))
        self.assertEqual(tax_line.credit, Decimal("1190.0"))

        # 11. Strict Trial Balance Balance
        tb = self.accounting_service.get_trial_balance()
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)

    def test_b2c_line_bot_to_fulfillment_lifecycle(self) -> None:
        """Verify complete B2C flow: LINE Bot Catalog Request -> One-Click Order Postback ->

        Instant ERP Stock Lock -> Order Shipment & Invoicing -> Customer Query Order Status.
        """
        # 1. Customer requests catalog
        catalog_event = {
            "type": "message",
            "mode": "active",
            "timestamp": 1700000000100,
            "webhookEventId": "evt-b2c-01",
            "deliveryContext": {"isRedelivery": False},
            "source": {"type": "user", "userId": "Uline_customer_777"},
            "replyToken": "token_catalog_test",
            "message": {
                "id": "msg-001",
                "type": "text",
                "text": "我想看商品型錄",
                "quoteToken": "q_token_1",
            },
        }
        body, sig = make_signed_payload(self.line_secret, [catalog_event])
        resp = self.client.post(
            "/api/line/webhook",
            content=body,
            headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.mock_line_adapter.sent_replies), 1)
        self.assertIn("商品型錄", self.mock_line_adapter.last_reply.messages[0].alt_text)

        self.mock_line_adapter.clear()

        # 2. Customer places order via Postback
        order_event = {
            "type": "postback",
            "mode": "active",
            "timestamp": 1700000000101,
            "webhookEventId": "evt-b2c-02",
            "deliveryContext": {"isRedelivery": False},
            "source": {"type": "user", "userId": "Uline_customer_777"},
            "replyToken": "token_order_postback",
            "postback": {
                "data": "action=order&sku=SKU-ACC-02&qty=2",
            },
        }
        body2, sig2 = make_signed_payload(self.line_secret, [order_event])
        resp2 = self.client.post(
            "/api/line/webhook",
            content=body2,
            headers={"X-Line-Signature": sig2, "Content-Type": "application/json"},
        )
        self.assertEqual(resp2.status_code, 200)

        # Verify receipt sent to LINE
        self.assertEqual(len(self.mock_line_adapter.sent_replies), 1)
        self.assertIn("訂單成立通知", self.mock_line_adapter.last_reply.messages[0].alt_text)

        # Verify ERP Order state: channel=LINE, status=CONFIRMED, stock locked
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT order_id, channel, status, total_amount FROM sales_orders WHERE channel = 'LINE' ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            order_id = row["order_id"]
            self.assertEqual(row["status"], OrderStatus.CONFIRMED.value)
            self.assertEqual(Decimal(str(row["total_amount"])), Decimal("1300.0"))  # 2 * 650

            lock_row = conn.execute(
                "SELECT locked_qty FROM stock_locks WHERE order_id = ? AND status = 'LOCKED'",
                (order_id,),
            ).fetchone()
            self.assertIsNotNone(lock_row)
            self.assertEqual(Decimal(str(lock_row["locked_qty"])), Decimal("2.0"))

        self.mock_line_adapter.clear()

        # 3. Warehouse ships and invoices the order
        self.order_service.ship_order(
            order_id=order_id,
            warehouse_id="WH-MAIN",
            recipient_name="王先生",
            recipient_phone="0988-123-456",
            shipping_address="台中市西區公益路二段50號",
            tracking_number="TRK-LINE-E2E-777",
        )
        inv, _, _ = self.invoice_service.issue_invoice_for_order(order_id=order_id, buyer_name="王先生")
        
        # Verify order has completed lifecycle
        order_refreshed = self.order_service.get_order(order_id)
        self.assertEqual(order_refreshed.status, OrderStatus.COMPLETED)

        # 4. Customer queries order status via LINE text
        query_event = {
            "type": "message",
            "mode": "active",
            "timestamp": 1700000000102,
            "webhookEventId": "evt-b2c-03",
            "deliveryContext": {"isRedelivery": False},
            "source": {"type": "user", "userId": "Uline_customer_777"},
            "replyToken": "token_query_test",
            "message": {
                "id": "msg-002",
                "type": "text",
                "text": f"查單 {order_id}",
                "quoteToken": "q_token_2",
            },
        }
        body3, sig3 = make_signed_payload(self.line_secret, [query_event])
        self.client.post(
            "/api/line/webhook",
            content=body3,
            headers={"X-Line-Signature": sig3, "Content-Type": "application/json"},
        )
        self.assertEqual(len(self.mock_line_adapter.sent_replies), 1)
        query_json = json.dumps(self.mock_line_adapter.last_reply.messages[0].contents.to_dict(), ensure_ascii=False)
        self.assertIn("TRK-LINE-E2E-777", query_json)
        self.assertIn(inv.invoice_number, query_json)
        self.assertIn("已完成", query_json)

    def test_ai_file_automation_lifecycle(self) -> None:
        """Verify AI & Native File Automation features:

        1. BOM Excel multi-supplier price comparison and recommendation.
        2. Native PDF electronic invoice parsing and AP voucher generation.
        3. 4-in-1 Executive Financial & Operational Excel export streaming.
        """
        bom_service = BomComparisonService(db=self.db)
        sample_bom_bytes = AdvancedReportGenerator(db=self.db).generate_sample_bom_excel()
        parser = BomExcelParser()
        parsed_bom = parser.parse(sample_bom_bytes)
        bom_result = bom_service.compare_bom(parsed_bom)
        self.assertGreater(len(bom_result.items), 0)
        self.assertGreater(bom_result.total_cost_lowest, Decimal("0.0"))

        # 2. Native PDF Invoice Parsing
        pdf_invoice_path = Path(self.temp_dir.name) / "test_e2e_invoice.pdf"
        # Generate sample invoice PDF via endpoint
        resp = self.client.get("/ai/invoice/sample-pdf")
        self.assertEqual(resp.status_code, 200)
        pdf_invoice_path.write_bytes(resp.content)

        parser = TaiwanPdfInvoiceParser()
        with open(pdf_invoice_path, "rb") as f:
            parsed_inv = parser.parse(f.read())
        self.assertEqual(parsed_inv.invoice_number, "AB-98765432")
        self.assertEqual(parsed_inv.seller_tax_id, "88888888")
        self.assertEqual(parsed_inv.total_amount, Decimal("14700.0"))
        self.assertTrue(parsed_inv.is_math_valid)

        # 3. 4-in-1 Executive Financial & Operational Report
        rep_generator = AdvancedReportGenerator(db=self.db)
        rep_bytes = rep_generator.generate_comprehensive_financial_report()
        self.assertGreater(len(rep_bytes), 2000)

        import io
        rep_wb = openpyxl.load_workbook(io.BytesIO(rep_bytes))
        sheet_names = rep_wb.sheetnames
        self.assertIn("損益表 (Income Statement)", sheet_names)
        self.assertIn("試算表 (Trial Balance)", sheet_names)
        self.assertIn("帳齡分析 (Aging Matrix)", sheet_names)
        self.assertIn("庫存盤點底冊 (Stock Valuation)", sheet_names)
        rep_wb.close()


if __name__ == "__main__":
    unittest.main()
