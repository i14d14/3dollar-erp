from __future__ import annotations
import io
import unittest
from fastapi.testclient import TestClient

from src.ai_wrapper.reporting.excel_generator import AdvancedReportGenerator
from src.channel_ui.web.app import create_app
from src.channel_ui.web.demo_seed import seed_demo_data
from src.shared.database import Database
import tempfile
from pathlib import Path
from src.shared.event_bus import EventBus
import fitz


class TestAiWrapperWeb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.bus = EventBus()
        seed_demo_data(self.db, event_bus=self.bus)
        self.app = create_app(db=self.db, event_bus=self.bus)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_ai_tools_page(self):
        resp = self.client.get("/ai/tools")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("AI 檔案自動化與增強外掛", resp.text)
        self.assertIn("BOM 物料比價", resp.text)
        self.assertIn("原生發票抽取", resp.text)
        self.assertIn("財務營運報表中心", resp.text)

    def test_download_bom_sample(self):
        resp = self.client.get("/ai/bom/sample")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get("content-type"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(resp.content), 1000)

    def test_upload_and_compare_bom(self):
        generator = AdvancedReportGenerator(db=self.db)
        sample_bytes = generator.generate_sample_bom_excel()

        files = {"file": ("test_bom.xlsx", io.BytesIO(sample_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        resp = self.client.post("/ai/bom/compare", files=files)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("BOM 物料比價明細表", resp.text)
        self.assertIn("SKU-PRO-01", resp.text)
        self.assertIn("推薦供應商", resp.text)

    def test_download_invoice_sample_pdf(self):
        resp = self.client.get("/ai/invoice/sample-pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("content-type"), "application/pdf")
        self.assertGreater(len(resp.content), 500)

    def test_upload_and_extract_invoice_pdf(self):
        # Generate sample PDF
        pdf_resp = self.client.get("/ai/invoice/sample-pdf")
        pdf_bytes = pdf_resp.content

        files = {"file": ("test_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        resp = self.client.post("/ai/invoice/extract", files=files)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("AB-98765432", resp.text)
        self.assertIn("祥茂電子精密工業", resp.text)
        self.assertIn("金額勾稽吻合", resp.text)

    def test_confirm_invoice_ap_creation(self):
        form_data = {
            "invoice_number": "AB-98765432",
            "seller_name": "祥茂電子精密工業",
            "seller_tax_id": "88888888",
            "total_amount": "14700",
            "sales_amount": "14000",
            "tax_amount": "700",
            "po_id": "",
        }
        resp = self.client.post("/ai/invoice/confirm-ap", data=form_data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("應付帳款與會計分錄建立成功", resp.text)
        self.assertIn("14,700", resp.text)

    def test_download_executive_financial_report(self):
        resp = self.client.get("/ai/reports/executive-financial")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get("content-type"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(resp.content), 2000)


if __name__ == "__main__":
    unittest.main()
