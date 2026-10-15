from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestAccountingUndoWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_accounting_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.accounting_service = AccountingService(db=self.db)

        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_journal_entry_returns_toast_with_undo_and_reversal_offsets_ledger(self) -> None:
        initial_entries = self.accounting_service.get_journal_entries(limit=100)
        initial_count = len(initial_entries)
        tb_init = self.accounting_service.get_trial_balance()
        cash_init = next((it.balance_debit - it.balance_credit for it in tb_init.items if it.account_code == "1101"), Decimal("0"))
        capital_init = next((it.balance_credit - it.balance_debit for it in tb_init.items if it.account_code == "3101"), Decimal("0"))

        # Create manual journal entry: Dr 1101 (現金) 50000, Cr 3101 (業主資本) 50000
        resp = self.client.post(
            "/accounting/journal-entries",
            headers={"HX-Request": "true"},
            data={
                "entry_date": "2026-09-22",
                "description": "期初業主投資現金",
                "account_code_1": "1101",
                "debit_1": "50000",
                "credit_1": "0",
                "account_code_2": "3101",
                "debit_2": "0",
                "credit_2": "50000",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("手動傳票建立成功", resp.text)
        self.assertIn("撤回傳票", resp.text)

        # Check DB entries
        entries = self.accounting_service.get_journal_entries(limit=100)
        self.assertEqual(len(entries), initial_count + 1)
        original_entry = next(e for e in entries if e.description == "期初業主投資現金")
        self.assertTrue(original_entry.entry_id.startswith("JE-"))
        self.assertEqual(original_entry.source_event, "MANUAL")
        self.assertIn(f"/accounting/journal-entries/{original_entry.entry_id}/undo", resp.text)

        # Check trial balance before undo (+50000)
        tb_before = self.accounting_service.get_trial_balance()
        cash_before = next((it.balance_debit - it.balance_credit for it in tb_before.items if it.account_code == "1101"), Decimal("0"))
        capital_before = next((it.balance_credit - it.balance_debit for it in tb_before.items if it.account_code == "3101"), Decimal("0"))
        self.assertEqual(cash_before - cash_init, Decimal("50000"))
        self.assertEqual(capital_before - capital_init, Decimal("50000"))

        # Click Undo (Reversal entry)
        undo_resp = self.client.post(
            f"/accounting/journal-entries/{original_entry.entry_id}/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn('id="toast-container"', undo_resp.text)
        self.assertIn("已成功撤回傳票", undo_resp.text)
        self.assertIn("已立案紅字反向沖銷傳票", undo_resp.text)

        # Verify Append-Only ledger: initial + 2 entries exist now (original + reversal)
        entries_after = self.accounting_service.get_journal_entries(limit=100)
        self.assertEqual(len(entries_after), initial_count + 2)
        rev_entry = next(e for e in entries_after if e.reference_id == original_entry.entry_id)
        self.assertTrue(rev_entry.entry_id.startswith("REV-"))
        self.assertEqual(rev_entry.source_event, "REVERSAL")

        # Verify trial balance is restored to initial net balance
        tb_after = self.accounting_service.get_trial_balance()
        cash_after = next((it.balance_debit - it.balance_credit for it in tb_after.items if it.account_code == "1101"), Decimal("0"))
        capital_after = next((it.balance_credit - it.balance_debit for it in tb_after.items if it.account_code == "3101"), Decimal("0"))
        self.assertEqual(cash_after, cash_init)
        self.assertEqual(capital_after, capital_init)

        # Duplicate undo must be rejected
        dup_undo_resp = self.client.post(
            f"/accounting/journal-entries/{original_entry.entry_id}/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(dup_undo_resp.status_code, 400)
        self.assertIn("不可重複撤回", dup_undo_resp.text)
