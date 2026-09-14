from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.channel_ui.web.dtos import (
    DashboardSummaryDTO,
    InventoryStockDTO,
    LowStockItemDTO,
    OrderRowDTO,
    StockLedgerRowDTO,
)
from src.core.services.invoice_service import InvoiceService
from src.shared.database import Database, default_db

STATUS_BADGES: Dict[str, str] = {
    "DRAFT": "bg-slate-100 text-slate-700 border border-slate-300",
    "CONFIRMED": "bg-sky-100 text-sky-700 border border-sky-300",
    "SHIPPED": "bg-amber-100 text-amber-700 border border-amber-300",
    "COMPLETED": "bg-emerald-100 text-emerald-700 border border-emerald-300",
    "CANCELLED": "bg-rose-100 text-rose-700 border border-rose-300",
}


class WebViewService:
    def __init__(self, db: Database = default_db) -> None:
        self.db = db
        self.invoice_service = InvoiceService(db=db)

    def get_dashboard_summary(self) -> DashboardSummaryDTO:
        with self.db.transaction() as conn:
            today_str = datetime.date.today().isoformat()

            # 1. Today's orders count
            row_orders = conn.execute(
                "SELECT COUNT(*) as count FROM sales_orders WHERE date(created_at) = date(?)",
                (today_str,),
            ).fetchone()
            today_orders = row_orders["count"] if row_orders else 0

            # 2. Pending shipments (Confirmed orders)
            row_pending = conn.execute(
                "SELECT COUNT(*) as count FROM sales_orders WHERE status = 'CONFIRMED'"
            ).fetchone()
            pending_shipments = row_pending["count"] if row_pending else 0

            # 3. Low stock alerts count & items
            stock_rows = conn.execute(
                """
                SELECT p.sku, p.name, p.safety_stock, w.name as warehouse_name,
                       COALESCE(SUM(l.qty_delta), 0) as physical_balance
                FROM products p
                CROSS JOIN warehouses w
                LEFT JOIN stock_ledger l ON l.sku = p.sku AND l.warehouse_id = w.warehouse_id
                WHERE p.is_active = 1 AND w.is_active = 1
                GROUP BY p.sku, w.warehouse_id
                HAVING physical_balance < p.safety_stock
                ORDER BY p.sku ASC
                """
            ).fetchall()

            low_stock_items: List[LowStockItemDTO] = []
            for r in stock_rows:
                low_stock_items.append(
                    LowStockItemDTO(
                        sku=r["sku"],
                        product_name=r["name"],
                        physical_balance=Decimal(str(r["physical_balance"])),
                        safety_stock=int(r["safety_stock"]),
                        warehouse_name=r["warehouse_name"],
                    )
                )

            # 4. Total unpaid AR
            row_ar = conn.execute(
                "SELECT COALESCE(SUM(amount - paid_amount), 0) as unpaid FROM accounts_receivable WHERE status != 'PAID'"
            ).fetchone()
            unpaid_val = Decimal(str(row_ar["unpaid"])) if row_ar else Decimal("0.0")

        # 5. Recent orders
        recent_orders = self.list_orders(limit=8)

        return DashboardSummaryDTO(
            today_orders_count=today_orders,
            pending_shipments_count=pending_shipments,
            low_stock_alerts_count=len(low_stock_items),
            unpaid_ar_amount_formatted=f"NT$ {unpaid_val:,.2f}",
            recent_orders=recent_orders,
            low_stock_items=low_stock_items,
        )

    def list_orders(self, limit: int = 100) -> List[OrderRowDTO]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT so.order_id, so.customer_id, so.channel, so.status, so.total_amount, so.created_at,
                       do.do_id, do.tracking_number,
                       inv.invoice_number,
                       ar.ar_id
                FROM sales_orders so
                LEFT JOIN delivery_orders do ON do.order_id = so.order_id
                LEFT JOIN invoices inv ON inv.order_id = so.order_id
                LEFT JOIN accounts_receivable ar ON ar.order_id = so.order_id
                ORDER BY so.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        orders: List[OrderRowDTO] = []
        for r in rows:
            status = r["status"]
            do_id = r["do_id"]
            inv_num = r["invoice_number"]
            ar_id = r["ar_id"]

            is_reconciled = bool(do_id and inv_num and ar_id)

            orders.append(
                OrderRowDTO(
                    order_id=r["order_id"],
                    customer_id=r["customer_id"],
                    channel=r["channel"],
                    status=status,
                    status_badge_class=STATUS_BADGES.get(status, STATUS_BADGES["DRAFT"]),
                    total_amount_formatted=f"NT$ {Decimal(str(r['total_amount'])):,.2f}",
                    created_at=str(r["created_at"])[:16],
                    do_id=do_id,
                    tracking_number=r["tracking_number"],
                    invoice_number=inv_num,
                    is_reconciled=is_reconciled,
                    can_confirm=(status == "DRAFT"),
                    can_ship=(status == "CONFIRMED"),
                    can_invoice=(status in ("CONFIRMED", "SHIPPED") and inv_num is None),
                    has_shipping_label=bool(do_id),
                    has_invoice_pdf=bool(inv_num),
                )
            )
        return orders

    def get_order_row(self, order_id: str) -> Optional[OrderRowDTO]:
        with self.db.transaction() as conn:
            r = conn.execute(
                """
                SELECT so.order_id, so.customer_id, so.channel, so.status, so.total_amount, so.created_at,
                       do.do_id, do.tracking_number,
                       inv.invoice_number,
                       ar.ar_id
                FROM sales_orders so
                LEFT JOIN delivery_orders do ON do.order_id = so.order_id
                LEFT JOIN invoices inv ON inv.order_id = so.order_id
                LEFT JOIN accounts_receivable ar ON ar.order_id = so.order_id
                WHERE so.order_id = ?
                """,
                (order_id,),
            ).fetchone()

        if not r:
            return None

        status = r["status"]
        do_id = r["do_id"]
        inv_num = r["invoice_number"]
        ar_id = r["ar_id"]

        is_reconciled = bool(do_id and inv_num and ar_id)

        return OrderRowDTO(
            order_id=r["order_id"],
            customer_id=r["customer_id"],
            channel=r["channel"],
            status=status,
            status_badge_class=STATUS_BADGES.get(status, STATUS_BADGES["DRAFT"]),
            total_amount_formatted=f"NT$ {Decimal(str(r['total_amount'])):,.2f}",
            created_at=str(r["created_at"])[:16],
            do_id=do_id,
            tracking_number=r["tracking_number"],
            invoice_number=inv_num,
            is_reconciled=is_reconciled,
            can_confirm=(status == "DRAFT"),
            can_ship=(status == "CONFIRMED"),
            can_invoice=(status in ("CONFIRMED", "SHIPPED") and inv_num is None),
            has_shipping_label=bool(do_id),
            has_invoice_pdf=bool(inv_num),
        )

    def list_inventory_stocks(self) -> List[InventoryStockDTO]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT w.warehouse_id, w.name as warehouse_name,
                       p.sku, p.name as product_name, p.safety_stock,
                       COALESCE(SUM(l.qty_delta), 0) as physical_balance,
                       COALESCE((
                           SELECT SUM(locked_qty)
                           FROM stock_locks
                           WHERE warehouse_id = w.warehouse_id AND sku = p.sku AND status = 'LOCKED'
                       ), 0) as locked_qty
                FROM warehouses w
                CROSS JOIN products p
                LEFT JOIN stock_ledger l ON l.warehouse_id = w.warehouse_id AND l.sku = p.sku
                WHERE w.is_active = 1 AND p.is_active = 1
                GROUP BY w.warehouse_id, p.sku
                ORDER BY w.warehouse_id ASC, p.sku ASC
                """
            ).fetchall()

        stocks: List[InventoryStockDTO] = []
        for r in rows:
            physical = Decimal(str(r["physical_balance"]))
            locked = Decimal(str(r["locked_qty"]))
            available = physical - locked
            safety = int(r["safety_stock"])
            stocks.append(
                InventoryStockDTO(
                    warehouse_id=r["warehouse_id"],
                    warehouse_name=r["warehouse_name"],
                    sku=r["sku"],
                    product_name=r["product_name"],
                    physical_balance=physical,
                    locked_qty=locked,
                    available_qty=available,
                    safety_stock=safety,
                    is_low_stock=(physical < safety),
                )
            )
        return stocks

    def list_recent_ledger_movements(self, limit: int = 50) -> List[StockLedgerRowDTO]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT l.ledger_id, l.warehouse_id, w.name as warehouse_name,
                       l.sku, p.name as product_name,
                       l.qty_delta, l.balance_after, l.reference_type, l.reference_id,
                       l.notes, l.created_at
                FROM stock_ledger l
                JOIN warehouses w ON w.warehouse_id = l.warehouse_id
                JOIN products p ON p.sku = l.sku
                ORDER BY l.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        movements: List[StockLedgerRowDTO] = []
        for r in rows:
            delta = Decimal(str(r["qty_delta"]))
            if delta > 0:
                delta_str = f"+{delta}"
                delta_class = "text-emerald-600 font-semibold"
            else:
                delta_str = f"{delta}"
                delta_class = "text-rose-600 font-semibold"

            movements.append(
                StockLedgerRowDTO(
                    ledger_id=r["ledger_id"],
                    warehouse_id=r["warehouse_id"],
                    warehouse_name=r["warehouse_name"],
                    sku=r["sku"],
                    product_name=r["product_name"],
                    qty_delta_formatted=delta_str,
                    qty_delta_class=delta_class,
                    balance_after=Decimal(str(r["balance_after"])),
                    reference_type=r["reference_type"],
                    reference_id=r["reference_id"],
                    notes=r["notes"] or "",
                    created_at=str(r["created_at"])[:19],
                )
            )
        return movements
