import sqlite3
import shutil
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = Path("d:/3dollar_erp/erp.db")
backup_path = Path("d:/3dollar_erp/erp.db.bak_remove_unique")

# 1. Backup DB
print(f"Creating backup at {backup_path}...")
shutil.copy2(db_path, backup_path)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check initial counts
cursor.execute("SELECT count(*) FROM invoices")
inv_count_before = cursor.fetchone()[0]
cursor.execute("SELECT count(*) FROM accounts_receivable")
ar_count_before = cursor.fetchone()[0]
print(f"Before migration: {inv_count_before} invoices, {ar_count_before} accounts_receivable records.")

try:
    cursor.execute("PRAGMA foreign_keys = OFF;")
    cursor.execute("BEGIN TRANSACTION;")

    # 2. Rebuild invoices table
    print("Rebuilding 'invoices' table...")
    cursor.execute("""
    CREATE TABLE invoices_new (
        invoice_id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES sales_orders(order_id),
        invoice_number TEXT NOT NULL UNIQUE,
        random_code TEXT NOT NULL,
        tax_type TEXT NOT NULL DEFAULT '1',
        total_amount NUMERIC NOT NULL,
        tax_amount NUMERIC NOT NULL,
        buyer_tax_id TEXT,
        buyer_name TEXT,
        qrcode_l TEXT,
        qrcode_r TEXT,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    INSERT INTO invoices_new (
        invoice_id, order_id, invoice_number, random_code, tax_type,
        total_amount, tax_amount, buyer_tax_id, buyer_name, qrcode_l, qrcode_r, status, issued_at
    )
    SELECT 
        invoice_id, order_id, invoice_number, random_code, tax_type,
        total_amount, tax_amount, buyer_tax_id, buyer_name, qrcode_l, qrcode_r, status, issued_at
    FROM invoices;
    """)
    cursor.execute("DROP TABLE invoices;")
    cursor.execute("ALTER TABLE invoices_new RENAME TO invoices;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_order_id ON invoices(order_id);")

    # 3. Rebuild accounts_receivable table
    print("Rebuilding 'accounts_receivable' table...")
    cursor.execute("""
    CREATE TABLE accounts_receivable_new (
        ar_id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES sales_orders(order_id),
        invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
        customer_id TEXT NOT NULL,
        due_date DATE NOT NULL,
        amount NUMERIC NOT NULL,
        paid_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'UNPAID',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    INSERT INTO accounts_receivable_new (
        ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status, created_at
    )
    SELECT
        ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status, created_at
    FROM accounts_receivable;
    """)
    cursor.execute("DROP TABLE accounts_receivable;")
    cursor.execute("ALTER TABLE accounts_receivable_new RENAME TO accounts_receivable;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar_order_id ON accounts_receivable(order_id);")

    cursor.execute("COMMIT;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Check FK integrity
    fk_errors = cursor.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_errors:
        print(f"ERROR: Foreign key violations detected: {fk_errors}")
        sys.exit(1)
    else:
        print("Foreign key check PASSED: 0 violations.")

    # Check counts after
    cursor.execute("SELECT count(*) FROM invoices")
    inv_count_after = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM accounts_receivable")
    ar_count_after = cursor.fetchone()[0]
    assert inv_count_before == inv_count_after, f"Invoice count mismatch: {inv_count_before} vs {inv_count_after}"
    assert ar_count_before == ar_count_after, f"AR count mismatch: {ar_count_before} vs {ar_count_after}"
    print(f"After migration: {inv_count_after} invoices, {ar_count_after} accounts_receivable records. Counts match perfectly.")

    # Verify table schema
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='invoices'")
    print("New invoices schema:")
    print(cursor.fetchone()[0])
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='accounts_receivable'")
    print("New accounts_receivable schema:")
    print(cursor.fetchone()[0])

    print("Migration SUCCESS!")

except Exception as e:
    cursor.execute("ROLLBACK;")
    print(f"FAILED with error: {e}")
    conn.close()
    shutil.copy2(backup_path, db_path)
    print("Restored from backup.")
    sys.exit(1)
finally:
    conn.close()
