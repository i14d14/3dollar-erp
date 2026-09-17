import unittest
from datetime import date
from decimal import Decimal
from pydantic import ValidationError

from src.extended_core.accounting.models import (
    Account,
    AccountType,
    AccountsPayable,
    AgingBucket,
    AgingItem,
    AgingReport,
    APStatus,
    IncomeStatement,
    JournalEntry,
    JournalLine,
    TrialBalance,
    TrialBalanceItem,
)


class TestAccountingModels(unittest.TestCase):
    def test_journal_entry_balanced(self):
        lines = [
            JournalLine(
                line_id="JL-1",
                entry_id="JE-1",
                account_code="1101",
                debit=Decimal("1000.0"),
                credit=Decimal("0.0"),
            ),
            JournalLine(
                line_id="JL-2",
                entry_id="JE-1",
                account_code="4111",
                debit=Decimal("0.0"),
                credit=Decimal("1000.0"),
            ),
        ]
        entry = JournalEntry(
            entry_id="JE-1",
            entry_date=date.today(),
            source_event="TEST",
            reference_id="REF-1",
            description="Balanced entry",
            lines=lines,
        )
        self.assertEqual(len(entry.lines), 2)

    def test_journal_entry_imbalance_raises_error(self):
        lines = [
            JournalLine(
                line_id="JL-1",
                entry_id="JE-2",
                account_code="1101",
                debit=Decimal("1000.0"),
                credit=Decimal("0.0"),
            ),
            JournalLine(
                line_id="JL-2",
                entry_id="JE-2",
                account_code="4111",
                debit=Decimal("0.0"),
                credit=Decimal("950.0"),
            ),
        ]
        with self.assertRaises(ValidationError) as ctx:
            JournalEntry(
                entry_id="JE-2",
                entry_date=date.today(),
                source_event="TEST",
                reference_id="REF-2",
                description="Imbalanced entry",
                lines=lines,
            )
        self.assertIn("Double-entry bookkeeping imbalance", str(ctx.exception))

    def test_ap_and_aging_models(self):
        ap = AccountsPayable(
            ap_id="AP-100",
            po_id="PO-100",
            supplier_name="大同供應商",
            due_date=date.today(),
            amount=Decimal("5000.0"),
            status=APStatus.UNPAID,
        )
        self.assertEqual(ap.amount, Decimal("5000.0"))
        self.assertEqual(ap.status, APStatus.UNPAID)

        item = AgingItem(
            item_id="AR-1",
            reference_id="SO-1",
            partner_name="科技公司",
            amount=Decimal("1000.0"),
            paid_amount=Decimal("0.0"),
            outstanding_amount=Decimal("1000.0"),
            due_date=date.today(),
            days_overdue=15,
            bucket=AgingBucket.DAYS_1_30,
            status="UNPAID",
        )
        report = AgingReport(
            report_type="RECEIVABLE",
            as_of_date=date.today(),
            total_outstanding=Decimal("1000.0"),
            current_amount=Decimal("0.0"),
            days_1_30_amount=Decimal("1000.0"),
            days_31_60_amount=Decimal("0.0"),
            days_60_plus_amount=Decimal("0.0"),
            items=[item],
        )
        self.assertEqual(report.days_1_30_amount, Decimal("1000.0"))


if __name__ == "__main__":
    unittest.main()
