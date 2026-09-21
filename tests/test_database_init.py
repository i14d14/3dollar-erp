import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from src.shared.database import Database

class TestDatabaseInitialization(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(self.db_path)
        self.db.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tables_created(self):
        with self.db.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            "warehouses", "products", "stock_ledger", "stock_locks",
            "purchase_orders", "purchase_order_items", "goods_receipt_notes",
            "sales_orders", "sales_order_items", "delivery_orders",
            "invoices", "accounts_receivable", "accounts",
            "journal_entries", "journal_lines", "crm_contacts",
            "crm_deals", "crm_quotes"
        }
        for table in expected_tables:
            self.assertIn(table, tables, f"Expected table '{table}' not found in database")

    def test_foreign_key_enforcement(self):
        # Trying to insert an order item referencing non-existent order should fail
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO sales_order_items (item_id, order_id, sku, qty, unit_price, subtotal) "
                    "VALUES ('item-1', 'non-existent-order', 'sku-1', 1, 100, 100);"
                )

    def test_transaction_rollback(self):
        try:
            with self.db.transaction() as conn:
                conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('W1', 'Main Warehouse');")
                # Intentional error to trigger rollback
                raise RuntimeError("Force abort transaction")
        except RuntimeError:
            pass

        with self.db.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM warehouses WHERE warehouse_id = 'W1';")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 0, "Transaction did not rollback on failure!")

    def test_transaction_commit(self):
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('W1', 'Main Warehouse');")

        with self.db.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM warehouses WHERE warehouse_id = 'W1';")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["name"], "Main Warehouse")

    def test_invoices_and_ar_allow_multiple_per_order(self):
        """Verify that invoices and accounts_receivable allow multiple records referencing the same order_id (1:N ready)."""
        with self.db.transaction() as conn:
            conn.execute("INSERT INTO sales_orders (order_id, customer_id, total_amount) VALUES ('SO-MULTI-1', 'CUST-1', 5000);")
            
            # Insert two invoices for the same order_id
            conn.execute(
                "INSERT INTO invoices (invoice_id, order_id, invoice_number, random_code, total_amount, tax_amount) "
                "VALUES ('INV-1', 'SO-MULTI-1', 'AA-10000001', '1234', 2000, 100);"
            )
            conn.execute(
                "INSERT INTO invoices (invoice_id, order_id, invoice_number, random_code, total_amount, tax_amount) "
                "VALUES ('INV-2', 'SO-MULTI-1', 'AA-10000002', '5678', 3000, 150);"
            )

            # Insert two ARs for the same order_id
            conn.execute(
                "INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount) "
                "VALUES ('AR-1', 'SO-MULTI-1', 'INV-1', 'CUST-1', '2026-10-01', 2000);"
            )
            conn.execute(
                "INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount) "
                "VALUES ('AR-2', 'SO-MULTI-1', 'INV-2', 'CUST-1', '2026-10-01', 3000);"
            )

        # Verify query
        with self.db.transaction() as conn:
            inv_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE order_id = 'SO-MULTI-1';").fetchone()[0]
            ar_count = conn.execute("SELECT COUNT(*) FROM accounts_receivable WHERE order_id = 'SO-MULTI-1';").fetchone()[0]
            self.assertEqual(inv_count, 2)
            self.assertEqual(ar_count, 2)

            # Verify that invoice_number still enforces UNIQUE
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO invoices (invoice_id, order_id, invoice_number, random_code, total_amount, tax_amount) "
                    "VALUES ('INV-3', 'SO-MULTI-1', 'AA-10000001', '9999', 1000, 50);"
                )

if __name__ == "__main__":
    unittest.main()

