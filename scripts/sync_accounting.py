import datetime
from decimal import Decimal
from src.shared.database import default_db
from src.extended_core.accounting.services.accounting_service import AccountingService

def sync_accounting():
    db = default_db
    svc = AccountingService(db=db)
    today = datetime.date.today()

    # 1. Capital injection
    with db.transaction() as conn:
        has_capital = conn.execute("SELECT 1 FROM journal_entries WHERE reference_id = 'INIT-CAPITAL'").fetchone()
    if not has_capital:
        svc.create_journal_entry(
            entry_date=today - datetime.timedelta(days=60),
            source_event="MANUAL",
            reference_id="INIT-CAPITAL",
            description="期初業主資本挹注與營運預備金",
            lines=[
                ("1101", Decimal("300000.0"), Decimal("0.0")),
                ("3101", Decimal("0.0"), Decimal("300000.0")),
            ],
        )
        print("Capital seeded.")

    # 2. Backfill Invoices
    with db.transaction() as conn:
        invoices = [dict(r) for r in conn.execute("SELECT * FROM invoices").fetchall()]
        existing_je_refs = {r[0] for r in conn.execute("SELECT reference_id FROM journal_entries").fetchall()}

    for inv in invoices:
        if inv["invoice_id"] not in existing_je_refs:
            tot = Decimal(str(inv["total_amount"]))
            tax = Decimal(str(inv["tax_amount"])) if inv["tax_amount"] else Decimal("0.0")
            sales = tot - tax
            lines = [
                ("1144", tot, Decimal("0.0")),
                ("4111", Decimal("0.0"), sales),
            ]
            if tax > 0:
                lines.append(("2201", Decimal("0.0"), tax))
            svc.create_journal_entry(
                entry_date=today,
                source_event="ERP_INVOICE_ISSUED",
                reference_id=inv["invoice_id"],
                description=f"電子發票開立認列營收 (發票: {inv['invoice_number']})",
                lines=lines,
            )
            print(f"Invoiced seeded: {inv['invoice_number']}")

    # 3. Backfill Delivery Orders (COGS)
    with db.transaction() as conn:
        dos = [dict(r) for r in conn.execute("SELECT do_id, order_id FROM delivery_orders").fetchall()]
        existing_je_refs = {r[0] for r in conn.execute("SELECT reference_id FROM journal_entries").fetchall()}

    for d in dos:
        if d["do_id"] not in existing_je_refs:
            with db.transaction() as conn:
                cost_row = conn.execute(
                    "SELECT SUM(ABS(qty_delta) * unit_cost) as c FROM stock_ledger WHERE reference_id = ?",
                    (d["do_id"],),
                ).fetchone()
            cost = Decimal(str(cost_row["c"])) if cost_row and cost_row["c"] else Decimal("1500.0")
            if cost > 0:
                svc.create_journal_entry(
                    entry_date=today,
                    source_event="ERP_ORDER_SHIPPED",
                    reference_id=d["do_id"],
                    description=f"銷貨出庫認列銷貨成本 (DO: {d['do_id']})",
                    lines=[
                        ("5111", cost, Decimal("0.0")),
                        ("1201", Decimal("0.0"), cost),
                    ],
                )
                print(f"COGS seeded for DO: {d['do_id']}")

    # 4. Supplier AP
    with db.transaction() as conn:
        ap_count = conn.execute("SELECT COUNT(*) FROM accounts_payable").fetchone()[0]

    if ap_count == 0:
        po_id = "PO-INIT-DEMO-01"
        grn_id = "GRN-INIT-DEMO-01"
        with db.transaction() as conn:
            po_exists = conn.execute("SELECT 1 FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
            if not po_exists:
                conn.execute(
                    "INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount) VALUES (?, ?, 'RECEIVED', ?)",
                    (po_id, "祥茂電子精密工業", 30000.0),
                )
                conn.execute(
                    "INSERT INTO goods_receipt_notes (grn_id, po_id, warehouse_id) VALUES (?, ?, 'WH-MAIN')",
                    (grn_id, po_id),
                )
        svc.create_accounts_payable(
            po_id=po_id,
            grn_id=grn_id,
            supplier_name="祥茂電子精密工業",
            amount=Decimal("30000.0"),
            due_days=30,
        )
        svc.create_journal_entry(
            entry_date=today - datetime.timedelta(days=10),
            source_event="ERP_GOODS_RECEIVED",
            reference_id=grn_id,
            description="採購入庫入帳 (祥茂電子精密工業)",
            lines=[
                ("1201", Decimal("30000.0"), Decimal("0.0")),
                ("2144", Decimal("0.0"), Decimal("30000.0")),
            ],
        )
        print("Supplier AP seeded.")

    # 5. Overdue AR for aging
    overdue_due_date = today - datetime.timedelta(days=15)
    with db.transaction() as conn:
        hist_ar = conn.execute("SELECT 1 FROM accounts_receivable WHERE ar_id = 'AR-HIST-01'").fetchone()
        if not hist_ar:
            conn.execute(
                """
                INSERT OR IGNORE INTO sales_orders (order_id, customer_id, channel, status, total_amount)
                VALUES ('SO-HIST-01', 'CUST-EPSILON-宏亞光學', 'DIRECT', 'COMPLETED', 10500.0)
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO invoices (invoice_id, order_id, invoice_number, random_code, tax_type, total_amount, tax_amount, status)
                VALUES ('INV-HIST-01', 'SO-HIST-01', 'ZZ-99887766', '8888', '1', 10500.0, 500.0, 'ISSUED')
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES ('AR-HIST-01', 'SO-HIST-01', 'INV-HIST-01', 'CUST-EPSILON-宏亞光學', ?, 10500.0, 0, 'UNPAID')
                """,
                (overdue_due_date.isoformat(),),
            )

    with db.transaction() as conn:
        has_hist_je = conn.execute("SELECT 1 FROM journal_entries WHERE reference_id = 'INV-HIST-01'").fetchone()
    if not has_hist_je:
        svc.create_journal_entry(
            entry_date=overdue_due_date,
            source_event="ERP_INVOICE_ISSUED",
            reference_id="INV-HIST-01",
            description="前期電子發票開立 (宏亞光學)",
            lines=[
                ("1144", Decimal("10500.0"), Decimal("0.0")),
                ("4111", Decimal("0.0"), Decimal("10000.0")),
                ("2201", Decimal("0.0"), Decimal("500.0")),
            ],
        )
        print("Historical overdue AR seeded.")

    # 6. Operating Expenses
    with db.transaction() as conn:
        has_exp = conn.execute("SELECT 1 FROM journal_entries WHERE reference_id = 'EXP-SEED-01'").fetchone()
    if not has_exp:
        svc.create_journal_entry(
            entry_date=today,
            source_event="EXPENSE",
            reference_id="EXP-SEED-01",
            description="辦公室雲端伺服器與耗材支出",
            lines=[
                ("6101", Decimal("3200.0"), Decimal("0.0")),
                ("1101", Decimal("0.0"), Decimal("3200.0")),
            ],
        )
        print("Operating expenses seeded.")

if __name__ == "__main__":
    sync_accounting()
