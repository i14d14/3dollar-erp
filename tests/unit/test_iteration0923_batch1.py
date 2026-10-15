import unittest
from pathlib import Path


class TestIteration0923Batch1(unittest.TestCase):
    """Targeted unit tests for Iteration 0923 Batch 1 front-end and template invariants."""

    def setUp(self):
        self.templates_dir = Path(__file__).resolve().parents[2] / "src" / "channel_ui" / "web" / "templates"

    def test_stock_table_simplified_button_text(self):
        stock_table_path = self.templates_dir / "partials" / "stock_table.html"
        self.assertTrue(stock_table_path.exists())
        content = stock_table_path.read_text(encoding="utf-8")
        self.assertIn("⚠️ 低於安全量", content)
        self.assertNotIn("• 一鍵下單", content)

    def test_accounting_reports_cards_match_excel_sheets(self):
        accounting_path = self.templates_dir / "accounting.html"
        self.assertTrue(accounting_path.exists())
        content = accounting_path.read_text(encoding="utf-8")

        # Must match 3 financial statements (Inventory stocktaking moved to /inventory per Bug 6)
        self.assertIn("即時損益表", content)
        self.assertIn("會計總帳試算表", content)
        self.assertIn("應收應付帳齡分析", content)
        self.assertNotIn("Executive_Summary", content)
        self.assertNotIn("頁籤: Aging_Analysis", content)

    def test_crm_quote_modal_resets_form_state(self):
        crm_path = self.templates_dir / "crm.html"
        self.assertTrue(crm_path.exists())
        content = crm_path.read_text(encoding="utf-8")

        # openQuoteModal must call form.reset() and clear dynamic items container
        self.assertIn("form.reset()", content)
        self.assertIn("container.innerHTML = ''", content)
        self.assertIn("quote-items-container", content)

    def test_toast_notification_multiline_support(self):
        toast_path = self.templates_dir / "partials" / "toast_notification.html"
        self.assertTrue(toast_path.exists())
        content = toast_path.read_text(encoding="utf-8")

        # Truncate must be replaced with break-words and whitespace-normal
        self.assertIn("break-words", content)
        self.assertIn("whitespace-normal", content)
        self.assertNotIn("truncate", content)


if __name__ == "__main__":
    unittest.main()
