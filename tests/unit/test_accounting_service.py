import datetime
import unittest
from decimal import Decimal
import tempfile
from pathlib import Path

from src.extended_core.accounting.models import AccountType, AgingBucket
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database


class TestAccountingService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.db.init_db()
        self.service = AccountingService(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_journal_entry_success(self):
        entry = self.service.create_journal_entry(
            entry_date=datetime.date.today(),
            source_event="MANUAL",
            reference_id="REF-001",
            description="資本投入",
            lines=[
                ("1101", Decimal("50000.0"), Decimal("0.0")),  # Dr 現金
                ("3101", Decimal("0.0"), Decimal("50000.0")),  # Cr 業主資本
            ],
        )
        self.assertEqual(len(entry.lines), 2)
        entries = self.service.get_journal_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_id, entry.entry_id)

    def test_create_journal_entry_imbalance_fails(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.create_journal_entry(
                entry_date=datetime.date.today(),
                source_event="MANUAL",
                reference_id="REF-002",
                description="失衡傳票",
                lines=[
                    ("1101", Decimal("50000.0"), Decimal("0.0")),
                    ("3101", Decimal("0.0"), Decimal("49000.0")),
                ],
            )
        self.assertIn("imbalance", str(ctx.exception).lower())

    def test_create_journal_entry_unknown_account_fails(self):
        with self.assertRaises(ValueError) as ctx:
            self.service.create_journal_entry(
                entry_date=datetime.date.today(),
                source_event="MANUAL",
                reference_id="REF-003",
                description="未知科目",
                lines=[
                    ("9999", Decimal("100.0"), Decimal("0.0")),
                    ("1101", Decimal("0.0"), Decimal("100.0")),
                ],
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_trial_balance_and_income_statement(self):
        today = datetime.date.today()
        # 1. 銷貨開票: Dr 應收 10500, Cr 銷貨收入 10000, Cr 銷項稅額 500
        self.service.create_journal_entry(
            entry_date=today,
            source_event="ERP_INVOICE_ISSUED",
            reference_id="INV-001",
            description="銷貨開票",
            lines=[
                ("1144", Decimal("10500.0"), Decimal("0.0")),
                ("4111", Decimal("0.0"), Decimal("10000.0")),
                ("2201", Decimal("0.0"), Decimal("500.0")),
            ],
        )

        # 2. 認列銷貨成本: Dr 銷貨成本 6000, Cr 存貨 6000
        self.service.create_journal_entry(
            entry_date=today,
            source_event="ERP_ORDER_SHIPPED",
            reference_id="DO-001",
            description="銷貨出庫",
            lines=[
                ("5111", Decimal("6000.0"), Decimal("0.0")),
                ("1201", Decimal("0.0"), Decimal("6000.0")),
            ],
        )

        # 3. 營業費用: Dr 營業費用 1500, Cr 現金 1500
        self.service.create_journal_entry(
            entry_date=today,
            source_event="EXPENSE",
            reference_id="EXP-001",
            description="水電文具費",
            lines=[
                ("6101", Decimal("1500.0"), Decimal("0.0")),
                ("1101", Decimal("0.0"), Decimal("1500.0")),
            ],
        )

        # Check Trial Balance
        tb = self.service.get_trial_balance(as_of_date=today)
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)

        # Check Income Statement
        income = self.service.get_income_statement(end_date=today)
        self.assertEqual(income.revenue, Decimal("10000.0"))
        self.assertEqual(income.cogs, Decimal("6000.0"))
        self.assertEqual(income.gross_profit, Decimal("4000.0"))
        self.assertEqual(income.operating_expenses, Decimal("1500.0"))
        self.assertEqual(income.net_profit, Decimal("2500.0"))

    def test_aging_and_settlement(self):
        today = datetime.date.today()
        # Seed an AR
        with self.db.transaction() as conn:
            # Need a product & SO & INV to satisfy foreign key if any
            conn.execute("INSERT INTO products (sku, name) VALUES ('SKU-1', '測試商品')")
            conn.execute("INSERT INTO sales_orders (order_id, customer_id, total_amount) VALUES ('SO-1', '客戶A', 3000)")
            conn.execute(
                """
                INSERT INTO invoices (invoice_id, order_id, invoice_number, random_code, total_amount, tax_amount, qrcode_l, qrcode_r)
                VALUES ('INV-1', 'SO-1', 'AB-11111111', '1234', 3000, 0, 'L', 'R')
                """
            )
            # Create AR with due date 15 days ago (overdue 1-30 days)
            due_date = today - datetime.timedelta(days=15)
            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES ('AR-1', 'SO-1', 'INV-1', '客戶A', ?, 3000, 0, 'UNPAID')
                """,
                (due_date.isoformat(),),
            )

        # Check AR Aging
        ar_aging = self.service.get_ar_aging(as_of_date=today)
        self.assertEqual(ar_aging.total_outstanding, Decimal("3000.0"))
        self.assertEqual(ar_aging.days_1_30_amount, Decimal("3000.0"))
        self.assertEqual(len(ar_aging.items), 1)
        self.assertEqual(ar_aging.items[0].bucket, AgingBucket.DAYS_1_30)

        # Settle AR (without customer_name fallback)
        settle_entry = self.service.settle_receivable(ar_id="AR-1", amount=Decimal("3000.0"))
        self.assertEqual(len(settle_entry.lines), 2)
        self.assertIn("收取客戶 客戶A 款項", settle_entry.description)

        # Settle AR (with customer_name provided)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES ('AR-2', 'SO-1', 'INV-1', 'CUST-2', '2026-09-01', 1000.0, 0, 'UNPAID')
                """
            )
        settle_with_name = self.service.settle_receivable(ar_id="AR-2", customer_name="大發商行")
        self.assertIn("收取客戶 大發商行 (CUST-2) 款項", settle_with_name.description)

        # Re-check AR aging - should be 0 outstanding
        ar_aging_after = self.service.get_ar_aging(as_of_date=today)
        self.assertEqual(ar_aging_after.total_outstanding, Decimal("0.0"))
        self.assertEqual(len(ar_aging_after.items), 0)

        # Test AP creation and settlement
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO purchase_orders (po_id, supplier_name, total_amount) VALUES ('PO-1', '廠商B', 8000)")

        ap = self.service.create_accounts_payable(
            po_id="PO-1",
            supplier_name="廠商B",
            amount=Decimal("8000.0"),
            due_days=30,
        )
        self.assertEqual(ap.amount, Decimal("8000.0"))

        ap_aging = self.service.get_ap_aging(as_of_date=today)
        self.assertEqual(ap_aging.total_outstanding, Decimal("8000.0"))
        self.assertEqual(ap_aging.current_amount, Decimal("8000.0"))

        # Settle AP partial 5000
        self.service.settle_payable(ap_id=ap.ap_id, amount=Decimal("5000.0"))
        ap_aging_partial = self.service.get_ap_aging(as_of_date=today)
        self.assertEqual(ap_aging_partial.total_outstanding, Decimal("3000.0"))


if __name__ == "__main__":
    unittest.main()
