import os
from pathlib import Path
import unittest
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestCrmWeb(unittest.TestCase):
    def setUp(self):
        self.test_db_path = Path("d:/3dollar_erp/test_crm_web.db")
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        self.db = Database(self.test_db_path)
        self.event_bus = EventBus()
        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_crm_page_loads_with_seeded_data(self):
        response = self.client.get("/crm")
        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("哩來 (LiLai) CRM", text)
        self.assertIn("四段商機管線看板", text)
        self.assertIn("宏達數位科技有限公司", text)
        self.assertIn("2026 辦公室智慧終端硬體升級案", text)
        self.assertIn("商機管線總值", text)

    def test_crm_contacts_tab(self):
        response = self.client.get("/crm?tab=contacts")
        self.assertEqual(response.status_code, 200)
        self.assertIn("企業客戶主檔與窗口清單", response.text)
        self.assertIn("聯發資通企業股份有限公司", response.text)
        self.assertIn("87654321", response.text)

    def test_create_contact_endpoint_success_and_validation(self):
        # Valid contact
        resp = self.client.post(
            "/crm/contacts",
            data={
                "company_name": "台灣精密儀器股份有限公司",
                "contact_name": "趙特助",
                "tax_id": "54321098",
                "email": "chao@taiwan-precision.tw",
                "phone": "02-2789-0123",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("台灣精密儀器股份有限公司", resp.text)

        # Invalid tax ID via HTMX request
        resp_err = self.client.post(
            "/crm/contacts",
            data={
                "company_name": "無效統編測試",
                "contact_name": "李經理",
                "tax_id": "123",  # Invalid
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp_err.status_code, 400)
        self.assertIn("統一編號格式錯誤", resp_err.text)

        # Duplicate company name rejection
        resp_dup = self.client.post(
            "/crm/contacts",
            data={
                "company_name": "台灣精密儀器股份有限公司",
                "contact_name": "重複錄入人員",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp_dup.status_code, 400)
        self.assertIn("已存在於系統中，不可重複建立", resp_dup.text)

    def test_update_contact_endpoint(self):
        # Fetch an existing contact
        with self.db.transaction() as conn:
            c = conn.execute("SELECT contact_id, company_name FROM crm_contacts LIMIT 1").fetchone()
            contact_id = c["contact_id"]
            orig_company = c["company_name"]

        # Update contact
        resp = self.client.post(
            f"/crm/contacts/{contact_id}",
            data={
                "contact_name": "資深業務協理",
                "tax_id": "99887766",
                "email": "updated@company.tw",
                "phone": "02-9999-8888",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("成功更新客戶資料", resp.text)
        self.assertIn("資深業務協理", resp.text)

        # Verify company name was unchanged in DB
        with self.db.transaction() as conn:
            c_after = conn.execute("SELECT company_name, contact_name, phone FROM crm_contacts WHERE contact_id = ?", (contact_id,)).fetchone()
            self.assertEqual(c_after["company_name"], orig_company)
            self.assertEqual(c_after["contact_name"], "資深業務協理")
            self.assertEqual(c_after["phone"], "02-9999-8888")

    def test_create_deal_and_stage_progression(self):
        # 1. Fetch contact ID
        contact_id = "CUST-TSM03"  # Seeded in demo_seed
        with self.db.transaction() as conn:
            c = conn.execute("SELECT contact_id FROM crm_contacts LIMIT 1").fetchone()
            if c:
                contact_id = c["contact_id"]

        # 2. Create Deal
        resp = self.client.post(
            "/crm/deals",
            data={
                "contact_id": contact_id,
                "title": "人工智慧 edge 設備新案",
                "expected_amount": "88000",
                "stage": "LEAD",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("人工智慧 edge 設備新案", resp.text)

        # Retrieve deal_id
        with self.db.transaction() as conn:
            d = conn.execute("SELECT deal_id FROM crm_deals WHERE title = '人工智慧 edge 設備新案'").fetchone()
            deal_id = d["deal_id"]

        # 3. Advance stage: LEAD -> DISCOVERY
        resp_stage = self.client.post(
            f"/crm/deals/{deal_id}/stage",
            data={"stage": "DISCOVERY"},
            follow_redirects=True,
        )
        self.assertEqual(resp_stage.status_code, 200)

        # Verify in DB
        with self.db.transaction() as conn:
            d_updated = conn.execute("SELECT stage FROM crm_deals WHERE deal_id = ?", (deal_id,)).fetchone()
            self.assertEqual(d_updated["stage"], "DISCOVERY")

    def test_create_quote_and_download_docx_and_pdf(self):
        # Retrieve an active deal
        with self.db.transaction() as conn:
            d = conn.execute("SELECT deal_id FROM crm_deals WHERE stage = 'DISCOVERY' LIMIT 1").fetchone()
            deal_id = d["deal_id"]

        # Create Quote
        resp_quote = self.client.post(
            f"/crm/deals/{deal_id}/quotes",
            data={
                "sku_1": "SKU-PRO-01",
                "qty_1": "4",
                "price_1": "2500",
                "sku_2": "SKU-ACC-02",
                "qty_2": "2",
                "price_2": "650",
                "valid_days": "30",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_quote.status_code, 200)

        # Retrieve quote_id
        with self.db.transaction() as conn:
            q = conn.execute("SELECT quote_id FROM crm_quotes WHERE deal_id = ? ORDER BY created_at DESC LIMIT 1", (deal_id,)).fetchone()
            quote_id = q["quote_id"]

        # 1. Download DOCX
        resp_docx = self.client.get(f"/crm/quotes/{quote_id}/docx")
        self.assertEqual(resp_docx.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.wordprocessingml.document", resp_docx.headers["Content-Type"])
        self.assertGreater(len(resp_docx.content), 5000)

        # 2. View PDF
        resp_pdf = self.client.get(f"/crm/quotes/{quote_id}/pdf")
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf.headers["Content-Type"], "application/pdf")
        self.assertTrue(resp_pdf.content.startswith(b"%PDF-"))

    def test_convert_deal_to_erp_order_endpoint(self):
        # Find a deal in PROPOSAL stage with a quote
        with self.db.transaction() as conn:
            d = conn.execute(
                """
                SELECT d.deal_id
                FROM crm_deals d
                JOIN crm_quotes q ON d.deal_id = q.deal_id
                WHERE d.stage = 'PROPOSAL' AND d.converted_order_id IS NULL
                LIMIT 1
                """
            ).fetchone()
            deal_id = d["deal_id"]

        # Convert to order
        resp = self.client.post(
            f"/crm/deals/{deal_id}/convert-to-order",
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        # Verify DB
        with self.db.transaction() as conn:
            d_won = conn.execute("SELECT stage, converted_order_id FROM crm_deals WHERE deal_id = ?", (deal_id,)).fetchone()
            self.assertEqual(d_won["stage"], "WON")
            self.assertIsNotNone(d_won["converted_order_id"])
            order_id = d_won["converted_order_id"]

            so = conn.execute("SELECT channel, status FROM sales_orders WHERE order_id = ?", (order_id,)).fetchone()
            self.assertEqual(so["channel"], "CRM")
            self.assertEqual(so["status"], "DRAFT")


if __name__ == "__main__":
    unittest.main()
