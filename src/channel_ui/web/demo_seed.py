import datetime
from decimal import Decimal
from typing import Optional

from src.core.domain.inventory import ReferenceType
from src.core.domain.order import OrderStatus
from src.core.ports.event_bus_port import EventBusPort
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database


def seed_demo_data(db: Database, event_bus: EventBusPort) -> None:
    """Ensure database schema is created and seed initial realistic demo data if empty."""
    db.init_db()

    with db.transaction() as conn:
        wh_count = conn.execute("SELECT COUNT(*) FROM warehouses").fetchone()[0]
        je_count = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]

    inventory_service = InventoryService(db=db)
    order_service = OrderService(db=db, inventory_service=inventory_service, event_bus=event_bus)
    procurement_service = ProcurementService(db=db, event_bus=event_bus)
    invoice_service = InvoiceService(db=db, event_bus=event_bus)
    accounting_service = AccountingService(db=db)

    today = datetime.date.today()

    # 1. Base Inventory & Orders Seeding (if warehouses empty)
    if wh_count == 0:
        inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        inventory_service.create_warehouse("WH-STORE", "信義旗艦店")

        inventory_service.create_product(
            sku="SKU-PRO-01",
            name="智慧旗艦終端機",
            base_unit="PCS",
            cost_price=Decimal("1500.0"),
            selling_price=Decimal("2500.0"),
            safety_stock=20,
        )
        inventory_service.create_product(
            sku="SKU-ACC-02",
            name="高速傳輸擴充底座",
            base_unit="PCS",
            cost_price=Decimal("300.0"),
            selling_price=Decimal("650.0"),
            safety_stock=10,
        )
        inventory_service.create_product(
            sku="SKU-IOT-03",
            name="無線溫濕度傳感節點",
            base_unit="PCS",
            cost_price=Decimal("450.0"),
            selling_price=Decimal("890.0"),
            safety_stock=15,
        )

        inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-PRO-01",
            qty_delta=Decimal("80.0"),
            unit_cost=Decimal("1500.0"),
            reference_id="INIT-WH-MAIN-01",
            notes="期初總倉入庫",
        )
        inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-ACC-02",
            qty_delta=Decimal("45.0"),
            unit_cost=Decimal("300.0"),
            reference_id="INIT-WH-MAIN-02",
            notes="期初總倉入庫",
        )
        inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-IOT-03",
            qty_delta=Decimal("8.0"),
            unit_cost=Decimal("450.0"),
            reference_id="INIT-WH-MAIN-03",
            notes="低安全存量測試品",
        )
        inventory_service.adjust_stock(
            warehouse_id="WH-STORE",
            sku="SKU-PRO-01",
            qty_delta=Decimal("20.0"),
            unit_cost=Decimal("1500.0"),
            reference_id="INIT-WH-STORE-01",
            notes="門市備貨",
        )
        inventory_service.adjust_stock(
            warehouse_id="WH-STORE",
            sku="SKU-ACC-02",
            qty_delta=Decimal("15.0"),
            unit_cost=Decimal("300.0"),
            reference_id="INIT-WH-STORE-02",
            notes="門市備貨",
        )

        order_service.create_order(
            customer_id="CUST-ALPHA-科技股份有限公司",
            items=[
                ("SKU-PRO-01", Decimal("2.0"), Decimal("2500.0")),
                ("SKU-ACC-02", Decimal("1.0"), Decimal("650.0")),
            ],
        )

        order_2 = order_service.create_order(
            customer_id="CUST-BETA-聯運實業",
            items=[
                ("SKU-ACC-02", Decimal("3.0"), Decimal("650.0")),
            ],
        )
        order_service.confirm_order(order_2.order_id, "WH-MAIN")

        order_3 = order_service.create_order(
            customer_id="CUST-GAMMA-全創數位",
            items=[
                ("SKU-PRO-01", Decimal("1.0"), Decimal("2500.0")),
            ],
        )
        order_service.confirm_order(order_3.order_id, "WH-MAIN")
        order_service.ship_order(
            order_id=order_3.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="陳主管",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區松仁路100號",
        )

    # 2. TanGii (探吉) Accounting Synchronization / Seeding
    if je_count == 0:
        # A. Initial capital injection
        accounting_service.create_journal_entry(
            entry_date=today - datetime.timedelta(days=60),
            source_event="MANUAL",
            reference_id="INIT-CAPITAL",
            description="期初業主資本挹注與營運預備金",
            lines=[
                ("1101", Decimal("300000.0"), Decimal("0.0")),  # Dr 現金 300,000
                ("3101", Decimal("0.0"), Decimal("300000.0")),  # Cr 業主資本 300,000
            ],
        )

        # B. Backfill existing Invoices -> Revenue & AR
        with db.transaction() as conn:
            invoices_rows = conn.execute("SELECT * FROM invoices").fetchall()
            for inv in invoices_rows:
                tot = Decimal(str(inv["total_amount"]))
                tax = Decimal(str(inv["tax_amount"])) if inv["tax_amount"] else Decimal("0.0")
                sales = tot - tax

                lines = [
                    ("1144", tot, Decimal("0.0")),
                    ("4111", Decimal("0.0"), sales),
                ]
                if tax > 0:
                    lines.append(("2201", Decimal("0.0"), tax))

                accounting_service.create_journal_entry(
                    entry_date=today,
                    source_event="ERP_INVOICE_ISSUED",
                    reference_id=inv["invoice_id"],
                    description=f"電子發票開立認列營收 (發票: {inv['invoice_number']})",
                    lines=lines,
                )

        # C. Backfill existing Delivery Orders -> COGS
        with db.transaction() as conn:
            do_rows = conn.execute("SELECT do_id, order_id FROM delivery_orders").fetchall()
            for d in do_rows:
                cost_row = conn.execute(
                    "SELECT SUM(ABS(qty_delta) * unit_cost) as c FROM stock_ledger WHERE reference_id = ?",
                    (d["do_id"],),
                ).fetchone()
                cogs_val = Decimal(str(cost_row["c"])) if cost_row and cost_row["c"] else Decimal("1500.0")
                if cogs_val > 0:
                    accounting_service.create_journal_entry(
                        entry_date=today,
                        source_event="ERP_ORDER_SHIPPED",
                        reference_id=d["do_id"],
                        description=f"銷貨出庫認列銷貨成本 (DO: {d['do_id']})",
                        lines=[
                            ("5111", cogs_val, Decimal("0.0")),
                            ("1201", Decimal("0.0"), cogs_val),
                        ],
                    )

        # D. Procurement with Supplier AP (if no AP exists)
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

            accounting_service.create_accounts_payable(
                po_id=po_id,
                grn_id=grn_id,
                supplier_name="祥茂電子精密工業",
                amount=Decimal("30000.0"),
                due_days=30,
            )
            accounting_service.create_journal_entry(
                entry_date=today - datetime.timedelta(days=10),
                source_event="ERP_GOODS_RECEIVED",
                reference_id=grn_id,
                description="採購入庫入帳 (祥茂電子精密工業)",
                lines=[
                    ("1201", Decimal("30000.0"), Decimal("0.0")),
                    ("2144", Decimal("0.0"), Decimal("30000.0")),
                ],
            )

        # E. Historical Overdue AR item (15 days overdue) for Aging matrix
        overdue_due_date = today - datetime.timedelta(days=15)
        with db.transaction() as conn:
            hist_inv = conn.execute("SELECT invoice_id FROM invoices WHERE invoice_id = 'INV-HIST-01'").fetchone()
            if not hist_inv:
                conn.execute(
                    """
                    INSERT INTO sales_orders (order_id, customer_id, channel, status, total_amount)
                    VALUES ('SO-HIST-01', 'CUST-EPSILON-宏亞光學', 'DIRECT', 'COMPLETED', 10500.0)
                    """
                )
                conn.execute(
                    """
                    INSERT INTO delivery_orders (do_id, order_id, warehouse_id, tracking_number, shipped_at)
                    VALUES ('DO-HIST-01', 'SO-HIST-01', 'WH-MAIN', 'TRK-HIST-01', ?)
                    """,
                    (overdue_due_date.isoformat(),),
                )
                conn.execute(
                    """
                    INSERT INTO invoices (invoice_id, order_id, invoice_number, random_code, tax_type, total_amount, tax_amount, status)
                    VALUES ('INV-HIST-01', 'SO-HIST-01', 'ZZ-99887766', '8888', '1', 10500.0, 500.0, 'ISSUED')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                    VALUES ('AR-HIST-01', 'SO-HIST-01', 'INV-HIST-01', 'CUST-EPSILON-宏亞光學', ?, 10500.0, 0, 'UNPAID')
                    """,
                    (overdue_due_date.isoformat(),),
                )

        accounting_service.create_journal_entry(
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

        # F. Operating Expenses
        accounting_service.create_journal_entry(
            entry_date=today,
            source_event="EXPENSE",
            reference_id="EXP-SEED-01",
            description="辦公室雲端伺服器與耗材支出",
            lines=[
                ("6101", Decimal("3200.0"), Decimal("0.0")),
                ("1101", Decimal("0.0"), Decimal("3200.0")),
            ],
        )
