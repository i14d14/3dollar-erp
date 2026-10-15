import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.shared.database import Database


class TestWebAccountingGUI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_web_acct.db"
        self.db = Database(db_path=self.db_path)
        self.app = create_app(db=self.db)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_accounting_main_page(self):
        response = self.client.get("/accounting")
        self.assertEqual(response.status_code, 200)
        self.assertIn("探吉 會計與記帳系統", response.text)
        self.assertIn("會計總分類帳試算表", response.text)
        self.assertIn("借貸嚴格平衡", response.text)

    def test_get_accounting_tabs(self):
        for tab in ["trial_balance", "income_statement", "aging", "journal"]:
            res = self.client.get(f"/accounting?tab={tab}")
            self.assertEqual(res.status_code, 200)

    def test_manual_journal_entry_success(self):
        res = self.client.post(
            "/accounting/journal-entries",
            data={
                "entry_date": "2026-09-14",
                "description": "測試業主增資款",
                "account_code_1": "1101",
                "debit_1": "20000",
                "credit_1": "0",
                "account_code_2": "3101",
                "debit_2": "0",
                "credit_2": "20000",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("HX-Redirect"), "/accounting?tab=journal")

    def test_manual_journal_entry_imbalance_fails(self):
        res = self.client.post(
            "/accounting/journal-entries",
            headers={"HX-Request": "true"},
            data={
                "entry_date": "2026-09-14",
                "description": "失衡測試傳票",
                "account_code_1": "1101",
                "debit_1": "20000",
                "credit_1": "0",
                "account_code_2": "3101",
                "debit_2": "0",
                "credit_2": "19000",
            },
        )
        # Should return 400 with HTMX toast container
        self.assertEqual(res.status_code, 400)
        self.assertIn("toast-container", res.text)
        self.assertIn("傳票借貸不平衡", res.text)

    def test_settle_ar_and_ap(self):
        # Fetch AR from seed
        with self.db.transaction() as conn:
            ar_row = conn.execute("SELECT ar_id FROM accounts_receivable WHERE status != 'PAID' LIMIT 1").fetchone()
            ap_row = conn.execute("SELECT ap_id FROM accounts_payable WHERE status != 'PAID' LIMIT 1").fetchone()

        self.assertIsNotNone(ar_row)
        self.assertIsNotNone(ap_row)

        # Settle AR
        res_ar = self.client.post(f"/accounting/ar/{ar_row['ar_id']}/settle")
        self.assertEqual(res_ar.status_code, 200)

        # Settle AP
        res_ap = self.client.post(f"/accounting/ap/{ap_row['ap_id']}/settle")
        self.assertEqual(res_ap.status_code, 200)

    def test_excel_exports(self):
        # 1. Trial Balance Excel
        res_tb = self.client.get("/accounting/export/trial-balance.xlsx")
        self.assertEqual(res_tb.status_code, 200)
        self.assertEqual(
            res_tb.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(res_tb.content), 1000)

        # 2. Income Statement Excel
        res_is = self.client.get("/accounting/export/income-statement.xlsx")
        self.assertEqual(res_is.status_code, 200)
        self.assertEqual(
            res_is.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(res_is.content), 1000)


    def test_ar_aging_customer_name_prioritization_and_fallback(self):
        # 1. Insert an AR entry linked to a known contact in crm_contacts
        with self.db.transaction() as conn:
            inv_row = conn.execute("SELECT order_id, invoice_id FROM invoices LIMIT 1").fetchone()
            contact_row = conn.execute("SELECT contact_id, company_name FROM crm_contacts LIMIT 1").fetchone()
            contact_id = contact_row["contact_id"]
            company_name = contact_row["company_name"]
            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES ('AR-TEST-CUST01', ?, ?, ?, '2026-09-01', 5000.0, 0, 'UNPAID')
                """,
                (inv_row["order_id"], inv_row["invoice_id"], contact_id),
            )

        # 2. Query view service directly
        view_service = self.app.state.view_service
        ar_aging = view_service.get_aging_view("RECEIVABLE")
        cust01_item = next((it for it in ar_aging.items if it.item_id == "AR-TEST-CUST01"), None)
        self.assertIsNotNone(cust01_item)
        self.assertEqual(cust01_item.partner_name, company_name)
        self.assertEqual(cust01_item.partner_id, contact_id)

        # 3. Verify fallback for unmapped customer (AR-HIST-01 with CUST-EPSILON-宏亞光學)
        hist_item = next((it for it in ar_aging.items if it.item_id == "AR-HIST-01"), None)
        self.assertIsNotNone(hist_item)
        self.assertEqual(hist_item.partner_name, "CUST-EPSILON-宏亞光學")
        self.assertEqual(hist_item.partner_id, "CUST-EPSILON-宏亞光學")

        # 4. Verify rendered HTML contains customer name and muted ID tag
        res = self.client.get("/accounting?tab=aging")
        self.assertEqual(res.status_code, 200)
        self.assertIn(company_name, res.text)
        self.assertIn(f"({contact_id})", res.text)

        # 5. Verify AR Settle Modal renders customer name and ID tag
        res_modal = self.client.get("/accounting/ar/AR-TEST-CUST01/settle-modal")
        self.assertEqual(res_modal.status_code, 200)
        self.assertIn(company_name, res_modal.text)
        self.assertIn(f"({contact_id})", res_modal.text)

    def test_journal_entries_name_priority_and_ar_receipt_description(self):
        # 1. Verify GET /accounting?tab=journal has account_name before code in select options
        res = self.client.get("/accounting?tab=journal")
        self.assertEqual(res.status_code, 200)
        self.assertIn("現金 (1101) - ASSET", res.text)
        self.assertIn("(1101)", res.text)

        # 2. Insert AR entry linked to known contact
        with self.db.transaction() as conn:
            inv_row = conn.execute("SELECT order_id, invoice_id FROM invoices LIMIT 1").fetchone()
            contact_row = conn.execute("SELECT contact_id, company_name FROM crm_contacts LIMIT 1").fetchone()
            contact_id = contact_row["contact_id"]
            company_name = contact_row["company_name"]
            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES ('AR-JOURNAL-TEST', ?, ?, ?, '2026-09-01', 888.0, 0, 'UNPAID')
                """,
                (inv_row["order_id"], inv_row["invoice_id"], contact_id),
            )

        # 3. Settle AR via web endpoint
        res_settle = self.client.post("/accounting/ar/AR-JOURNAL-TEST/settle")
        self.assertEqual(res_settle.status_code, 200)

        # 4. Check journal entries view
        view_service = self.app.state.view_service
        journal_entries = view_service.get_journal_entries_view()
        ar_receipt = next((e for e in journal_entries if e.reference_id == "AR-JOURNAL-TEST"), None)
        self.assertIsNotNone(ar_receipt)
        self.assertIn(f"收取客戶 {company_name} ({contact_id}) 款項", ar_receipt.description)

        # 5. Check rendered journal tab displays account_name before account_code
        res_tab = self.client.get("/accounting?tab=journal")
        self.assertEqual(res_tab.status_code, 200)
        self.assertIn(f"收取客戶 {company_name} ({contact_id}) 款項", res_tab.text)


if __name__ == "__main__":
    unittest.main()
