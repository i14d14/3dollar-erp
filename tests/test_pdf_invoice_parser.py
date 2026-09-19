from __future__ import annotations
import datetime
import io
import unittest
from decimal import Decimal
import fitz

from src.ai_wrapper.invoice.parser import TaiwanPdfInvoiceParser
from src.ai_wrapper.invoice.service import InvoiceIntakeService
import tempfile
from pathlib import Path
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database


class TestPdfInvoiceParser(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.db.init_db()

        with self.db.transaction() as conn:
            conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('WH-01', '測試倉')")
            # Existing purchase order for matching test
            conn.execute(
                """
                INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount)
                VALUES ('PO-MATCH-01', '祥茂電子精密工業', 'SUBMITTED', 14700.0)
                """
            )

        self.accounting_service = AccountingService(db=self.db)
        self.parser = TaiwanPdfInvoiceParser()
        self.service = InvoiceIntakeService(db=self.db, accounting_service=self.accounting_service)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _generate_test_invoice_pdf(self) -> bytes:
        doc = fitz.open()
        page = doc.new_page(width=161.57, height=400)

        page.insert_text(fitz.Point(12, 25), "祥茂電子精密工業", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 42), "電子發票證明聯", fontsize=10, fontname="china-t")
        page.insert_text(fitz.Point(12, 56), "(MIG 3.2.1)", fontsize=8, fontname="helv")
        page.insert_text(fitz.Point(12, 72), "115年09-10月", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(12, 88), "AB-98765432", fontsize=11, fontname="helv")
        page.draw_line(fitz.Point(10, 96), fitz.Point(150, 96), color=(0, 0, 0), width=0.8)

        page.insert_text(fitz.Point(12, 110), "開立日期: 2026-09-19 10:30", fontsize=7, fontname="china-t")
        page.insert_text(fitz.Point(12, 124), "隨機碼: 6852", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 138), "總計: NT$ 14,700", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 152), "賣方統編: 88888888", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 166), "買方統編: 12345678", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 180), "銷售額: NT$ 14,000", fontsize=7, fontname="china-t")
        page.insert_text(fitz.Point(12, 192), "營業稅: NT$ 700", fontsize=7, fontname="china-t")

        pdf_bytes = doc.write()
        doc.close()
        return pdf_bytes

    def test_pdf_invoice_parsing_successful(self):
        pdf_bytes = self._generate_test_invoice_pdf()
        extracted = self.parser.parse(pdf_bytes)

        self.assertEqual(extracted.invoice_number, "AB-98765432")
        self.assertEqual(extracted.seller_tax_id, "88888888")
        self.assertEqual(extracted.buyer_tax_id, "12345678")
        self.assertEqual(extracted.random_code, "6852")
        self.assertEqual(extracted.invoice_date, "2026-09-19")
        self.assertEqual(extracted.sales_amount, Decimal("14000.0"))
        self.assertEqual(extracted.tax_amount, Decimal("700.0"))
        self.assertEqual(extracted.total_amount, Decimal("14700.0"))
        self.assertTrue(extracted.is_math_valid)
        self.assertEqual(len(extracted.validation_warnings), 0)

    def test_invoice_matching_with_existing_po(self):
        pdf_bytes = self._generate_test_invoice_pdf()
        extracted = self.parser.parse(pdf_bytes)
        match_result = self.service.match_invoice(extracted)

        self.assertEqual(match_result.status, "MATCHED_PO")
        self.assertEqual(match_result.matched_po_id, "PO-MATCH-01")

    def test_create_ap_from_invoice(self):
        pdf_bytes = self._generate_test_invoice_pdf()
        extracted = self.parser.parse(pdf_bytes)

        ap_id = self.service.create_ap_from_invoice(
            invoice=extracted,
            po_id="PO-MATCH-01",
            supplier_name="祥茂電子精密工業",
        )

        self.assertTrue(ap_id.startswith("AP-"))

        # Verify AP record in database
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM accounts_payable WHERE ap_id = ?", (ap_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["supplier_name"], "祥茂電子精密工業")
            self.assertEqual(Decimal(str(row["amount"])), Decimal("14700.0"))
            self.assertEqual(row["status"], "UNPAID")

        # Verify Journal Entry recorded and balanced
        tb = self.accounting_service.get_trial_balance()
        self.assertTrue(tb.is_balanced)


if __name__ == "__main__":
    unittest.main()
