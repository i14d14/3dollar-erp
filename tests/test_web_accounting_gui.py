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


if __name__ == "__main__":
    unittest.main()
