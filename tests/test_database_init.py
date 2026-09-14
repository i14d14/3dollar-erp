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

if __name__ == "__main__":
    unittest.main()
