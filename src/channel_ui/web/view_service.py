from __future__ import annotations
import datetime
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional, Tuple

from src.channel_ui.web.dtos import (
    AccountingKPIsDTO,
    AgingItemViewDTO,
    AgingSummaryViewDTO,
    ContactRowDTO,
    CrmKanbanDTO,
    CrmSummaryDTO,
    DashboardSummaryDTO,
    DealCardDTO,
    DeliveryAllocationViewDTO,
    DeliveryOrderViewDTO,
    IncomeStatementViewDTO,
    InventoryStockDTO,
    JournalEntryViewDTO,
    JournalLineViewDTO,
    LowStockItemDTO,
    OrderRowDTO,
    OrderShipModalDTO,
    OrderShipModalItemDTO,
    PurchaseOrderItemDTO,
    PurchaseOrderRowDTO,
    StockLedgerRowDTO,
    TrialBalanceRowDTO,
    TrialBalanceViewDTO,
)
from src.extended_core.accounting.models import AccountType, AgingBucket
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database, default_db

STATUS_BADGES: Dict[str, str] = {
    "DRAFT": "bg-slate-100 text-slate-700 border border-slate-300",
    "CONFIRMED": "bg-sky-100 text-sky-700 border border-sky-300",
    "PARTIALLY_SHIPPED": "bg-indigo-100 text-indigo-700 border border-indigo-300",
    "SHIPPED": "bg-amber-100 text-amber-700 border border-amber-300",
    "COMPLETED": "bg-emerald-100 text-emerald-700 border border-emerald-300",
    "CANCELLED": "bg-rose-100 text-rose-700 border border-rose-300",
}

PO_STATUS_BADGES: Dict[str, Tuple[str, str]] = {
    "DRAFT": ("草稿 (DRAFT)", "bg-slate-100 text-slate-700 border border-slate-300"),
    "SUBMITTED": ("待到貨 (SUBMITTED)", "bg-sky-100 text-sky-800 border border-sky-300"),
    "RECEIVED": ("已驗收入庫 (RECEIVED)", "bg-emerald-100 text-emerald-800 border border-emerald-300"),
    "CANCELLED": ("已取消 (CANCELLED)", "bg-rose-100 text-rose-800 border border-rose-300"),
}

CRM_STAGE_BADGES: Dict[str, Tuple[str, str]] = {
    "LEAD": ("潛在商機", "bg-slate-100 text-slate-700 border border-slate-300"),
    "DISCOVERY": ("需求洽談", "bg-sky-50 text-sky-700 border border-sky-200"),
    "PROPOSAL": ("方案報價", "bg-amber-50 text-amber-700 border border-amber-200"),
    "WON": ("贏單成交", "bg-emerald-50 text-emerald-700 border border-emerald-300"),
    "LOST": ("輸單結案", "bg-rose-50 text-rose-700 border border-rose-200"),
}



class WebViewService:
    def __init__(self, db: Database = default_db) -> None:
        self.db = db
        self.accounting_service = AccountingService(db=db)

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
                SELECT p.sku, p.name,
                       COALESCE(wsl.safety_stock, p.safety_stock, 10) as effective_safety_stock,
                       w.warehouse_id, w.name as warehouse_name,
                       COALESCE(SUM(l.qty_delta), 0) as physical_balance
                FROM products p
                CROSS JOIN warehouses w
                LEFT JOIN warehouse_stock_levels wsl ON wsl.warehouse_id = w.warehouse_id AND wsl.sku = p.sku
                LEFT JOIN stock_ledger l ON l.sku = p.sku AND l.warehouse_id = w.warehouse_id
                WHERE p.is_active = 1 AND w.is_active = 1
                GROUP BY p.sku, w.warehouse_id
                HAVING physical_balance < effective_safety_stock
                ORDER BY p.sku ASC
                """
            ).fetchall()

            low_stock_items: List[LowStockItemDTO] = []
            for r in stock_rows:
                bal = Decimal(str(r["physical_balance"]))
                safe = int(r["effective_safety_stock"])
                suggested_qty = max(1, safe - int(bal))
                
                # Fetch recent supplier if available
                last_supplier_row = conn.execute(
                    """
                    SELECT po.supplier_name
                    FROM purchase_order_items poi
                    JOIN purchase_orders po ON po.po_id = poi.po_id
                    WHERE poi.sku = ?
                    ORDER BY po.created_at DESC
                    LIMIT 1
                    """,
                    (r["sku"],),
                ).fetchone()
                suggested_supplier = last_supplier_row["supplier_name"] if last_supplier_row else ""

                low_stock_items.append(
                    LowStockItemDTO(
                        sku=r["sku"],
                        product_name=r["name"],
                        physical_balance=bal,
                        safety_stock=safe,
                        warehouse_name=r["warehouse_name"],
                        warehouse_id=r["warehouse_id"],
                        suggested_qty=suggested_qty,
                        suggested_supplier=suggested_supplier,
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
                SELECT so.order_id, so.customer_id, so.warehouse_id, so.channel, so.status, so.total_amount, so.created_at,
                       do.do_id, do.tracking_number,
                       inv.invoice_number,
                       ar.ar_id,
                       c.company_name as customer_name
                FROM sales_orders so
                LEFT JOIN delivery_orders do ON do.do_id = (
                    SELECT do_id FROM delivery_orders WHERE order_id = so.order_id ORDER BY rowid DESC LIMIT 1
                )
                LEFT JOIN invoices inv ON inv.order_id = so.order_id
                LEFT JOIN accounts_receivable ar ON ar.order_id = so.order_id
                LEFT JOIN crm_contacts c ON c.contact_id = so.customer_id
                ORDER BY so.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            order_ids = [r["order_id"] for r in rows]
            dos_by_order: Dict[str, List[str]] = {}
            if order_ids:
                placeholders = ",".join(["?"] * len(order_ids))
                all_dos = conn.execute(
                    f"SELECT do_id, order_id FROM delivery_orders WHERE order_id IN ({placeholders}) ORDER BY rowid ASC",
                    order_ids,
                ).fetchall()
                for d in all_dos:
                    dos_by_order.setdefault(d["order_id"], []).append(d["do_id"])

        orders: List[OrderRowDTO] = []
        for r in rows:
            status = r["status"]
            do_id = r["do_id"]
            inv_num = r["invoice_number"]
            ar_id = r["ar_id"]
            oid = r["order_id"]
            do_list = dos_by_order.get(oid, [do_id] if do_id else [])

            is_reconciled = bool(do_id and inv_num and ar_id)
            wh = r["warehouse_id"] if ("warehouse_id" in r.keys() and r["warehouse_id"]) else "WH-MAIN"
            cust_name = r["customer_name"] if ("customer_name" in r.keys() and r["customer_name"]) else None

            orders.append(
                OrderRowDTO(
                    order_id=oid,
                    customer_id=r["customer_id"],
                    channel=r["channel"],
                    status=status,
                    status_badge_class=STATUS_BADGES.get(status, STATUS_BADGES["DRAFT"]),
                    total_amount_formatted=f"NT$ {Decimal(str(r['total_amount'])):,.2f}",
                    created_at=str(r["created_at"])[:16],
                    warehouse_id=wh,
                    customer_name=cust_name,
                    do_id=do_id,
                    tracking_number=r["tracking_number"],
                    invoice_number=inv_num,
                    is_reconciled=is_reconciled,
                    can_confirm=(status == "DRAFT"),
                    can_ship=(status in ("CONFIRMED", "PARTIALLY_SHIPPED")),
                    can_invoice=(status in ("CONFIRMED", "PARTIALLY_SHIPPED", "SHIPPED") and inv_num is None),
                    has_shipping_label=bool(do_id),
                    has_invoice_pdf=bool(inv_num),
                    delivery_orders_count=len(do_list),
                    delivery_order_ids=do_list,
                )
            )
        return orders

    def get_order_row(self, order_id: str) -> Optional[OrderRowDTO]:
        with self.db.transaction() as conn:
            r = conn.execute(
                """
                SELECT so.order_id, so.customer_id, so.warehouse_id, so.channel, so.status, so.total_amount, so.created_at,
                       do.do_id, do.tracking_number,
                       inv.invoice_number,
                       ar.ar_id,
                       c.company_name as customer_name
                FROM sales_orders so
                LEFT JOIN delivery_orders do ON do.do_id = (
                    SELECT do_id FROM delivery_orders WHERE order_id = so.order_id ORDER BY rowid DESC LIMIT 1
                )
                LEFT JOIN invoices inv ON inv.order_id = so.order_id
                LEFT JOIN accounts_receivable ar ON ar.order_id = so.order_id
                LEFT JOIN crm_contacts c ON c.contact_id = so.customer_id
                WHERE so.order_id = ?
                """,
                (order_id,),
            ).fetchone()

            if not r:
                return None

            do_rows = conn.execute(
                "SELECT do_id FROM delivery_orders WHERE order_id = ? ORDER BY rowid ASC",
                (order_id,),
            ).fetchall()
            delivery_order_ids = [d["do_id"] for d in do_rows]

        status = r["status"]
        do_id = r["do_id"]
        inv_num = r["invoice_number"]
        ar_id = r["ar_id"]

        is_reconciled = bool(do_id and inv_num and ar_id)
        wh = r["warehouse_id"] if ("warehouse_id" in r.keys() and r["warehouse_id"]) else "WH-MAIN"
        cust_name = r["customer_name"] if ("customer_name" in r.keys() and r["customer_name"]) else None

        return OrderRowDTO(
            order_id=r["order_id"],
            customer_id=r["customer_id"],
            channel=r["channel"],
            status=status,
            status_badge_class=STATUS_BADGES.get(status, STATUS_BADGES["DRAFT"]),
            total_amount_formatted=f"NT$ {Decimal(str(r['total_amount'])):,.2f}",
            created_at=str(r["created_at"])[:16],
            warehouse_id=wh,
            customer_name=cust_name,
            do_id=do_id,
            tracking_number=r["tracking_number"],
            invoice_number=inv_num,
            is_reconciled=is_reconciled,
            can_confirm=(status == "DRAFT"),
            can_ship=(status in ("CONFIRMED", "PARTIALLY_SHIPPED")),
            can_invoice=(status in ("CONFIRMED", "PARTIALLY_SHIPPED", "SHIPPED") and inv_num is None),
            has_shipping_label=bool(do_id),
            has_invoice_pdf=bool(inv_num),
            delivery_orders_count=len(delivery_order_ids),
            delivery_order_ids=delivery_order_ids,
        )

    def get_ship_modal_context(self, order_id: str) -> Dict[str, Any]:
        with self.db.transaction() as conn:
            r_order = conn.execute(
                """
                SELECT so.order_id, so.customer_id, so.warehouse_id, so.status,
                       c.company_name as customer_name
                FROM sales_orders so
                LEFT JOIN crm_contacts c ON c.contact_id = so.customer_id
                WHERE so.order_id = ?
                """,
                (order_id,),
            ).fetchone()
            if not r_order:
                raise ValueError(f"查無銷售訂單 {order_id} (Sales order not found)")

            item_rows = conn.execute(
                """
                SELECT oi.item_id, oi.order_id, oi.sku, oi.qty, oi.shipped_quantity, oi.unit_price, oi.subtotal,
                       p.name as product_name
                FROM sales_order_items oi
                LEFT JOIN products p ON p.sku = oi.sku
                WHERE oi.order_id = ?
                ORDER BY oi.rowid ASC
                """,
                (order_id,),
            ).fetchall()

            wh = r_order["warehouse_id"] if ("warehouse_id" in r_order.keys() and r_order["warehouse_id"]) else "WH-MAIN"
            cust_name = r_order["customer_name"] if ("customer_name" in r_order.keys() and r_order["customer_name"]) else None

            modal_items: List[OrderShipModalItemDTO] = []
            for it in item_rows:
                qty = Decimal(str(it["qty"]))
                shipped = Decimal(str(it["shipped_quantity"] or "0.0"))
                rem = max(Decimal("0.0"), qty - shipped)
                pname = it["product_name"] if ("product_name" in it.keys() and it["product_name"]) else it["sku"]
                modal_items.append(
                    OrderShipModalItemDTO(
                        item_id=it["item_id"],
                        order_id=it["order_id"],
                        sku=it["sku"],
                        product_name=pname,
                        qty=qty,
                        remaining_qty=rem,
                        shipped_qty=shipped,
                        unit_price=Decimal(str(it["unit_price"])),
                        subtotal=Decimal(str(it["subtotal"])),
                    )
                )

            modal_order = OrderShipModalDTO(
                order_id=r_order["order_id"],
                customer_id=r_order["customer_id"],
                customer_name=cust_name,
                warehouse_id=wh,
                items=modal_items,
            )

            return {
                "order": modal_order,
                "customer_name": cust_name,
            }

    def get_order_deliveries_view(self, order_id: str) -> List[DeliveryOrderViewDTO]:
        with self.db.transaction() as conn:
            do_rows = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number, shipped_at FROM delivery_orders WHERE order_id = ? ORDER BY rowid ASC",
                (order_id,),
            ).fetchall()
            if not do_rows:
                return []

            alloc_rows = conn.execute(
                """
                SELECT da.allocation_id, da.do_id, da.order_id, da.item_id, da.sku, da.allocated_qty, da.created_at,
                       p.name as product_name
                FROM delivery_allocations da
                LEFT JOIN products p ON p.sku = da.sku
                WHERE da.order_id = ?
                ORDER BY da.rowid ASC
                """,
                (order_id,),
            ).fetchall()

            allocs_by_do: Dict[str, List[DeliveryAllocationViewDTO]] = {}
            for r in alloc_rows:
                pname = r["product_name"] if ("product_name" in r.keys() and r["product_name"]) else r["sku"]
                allocs_by_do.setdefault(r["do_id"], []).append(
                    DeliveryAllocationViewDTO(
                        allocation_id=r["allocation_id"],
                        do_id=r["do_id"],
                        order_id=r["order_id"],
                        item_id=r["item_id"],
                        sku=r["sku"],
                        product_name=pname,
                        allocated_qty=Decimal(str(r["allocated_qty"])),
                        created_at=str(r["created_at"]) if r["created_at"] else None,
                    )
                )

            results: List[DeliveryOrderViewDTO] = []
            for d in do_rows:
                results.append(
                    DeliveryOrderViewDTO(
                        do_id=d["do_id"],
                        order_id=d["order_id"],
                        warehouse_id=d["warehouse_id"],
                        tracking_number=d["tracking_number"],
                        shipped_at=str(d["shipped_at"]) if d["shipped_at"] else None,
                        allocations=allocs_by_do.get(d["do_id"], []),
                    )
                )
            return results

    def list_inventory_stocks(self) -> List[InventoryStockDTO]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT w.warehouse_id, w.name as warehouse_name,
                       p.sku, p.name as product_name,
                       COALESCE(wsl.safety_stock, p.safety_stock, 10) as safety_stock,
                       COALESCE(SUM(l.qty_delta), 0) as physical_balance,
                       COALESCE((
                           SELECT SUM(locked_qty)
                           FROM stock_locks
                           WHERE warehouse_id = w.warehouse_id AND sku = p.sku AND status = 'LOCKED'
                       ), 0) as locked_qty
                FROM warehouses w
                CROSS JOIN products p
                LEFT JOIN warehouse_stock_levels wsl ON wsl.warehouse_id = w.warehouse_id AND wsl.sku = p.sku
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

    def get_inventory_stock_row(self, warehouse_id: str, sku: str) -> Optional[InventoryStockDTO]:
        with self.db.transaction() as conn:
            r = conn.execute(
                """
                SELECT w.warehouse_id, w.name as warehouse_name,
                       p.sku, p.name as product_name,
                       COALESCE(wsl.safety_stock, p.safety_stock, 10) as safety_stock,
                       COALESCE(SUM(l.qty_delta), 0) as physical_balance,
                       COALESCE((
                           SELECT SUM(locked_qty)
                           FROM stock_locks
                           WHERE warehouse_id = w.warehouse_id AND sku = p.sku AND status = 'LOCKED'
                       ), 0) as locked_qty
                FROM warehouses w
                JOIN products p ON p.sku = ?
                LEFT JOIN warehouse_stock_levels wsl ON wsl.warehouse_id = w.warehouse_id AND wsl.sku = p.sku
                LEFT JOIN stock_ledger l ON l.warehouse_id = w.warehouse_id AND l.sku = p.sku
                WHERE w.warehouse_id = ?
                GROUP BY w.warehouse_id, p.sku
                """,
                (sku, warehouse_id),
            ).fetchone()
            if not r:
                return None
            physical = Decimal(str(r["physical_balance"]))
            locked = Decimal(str(r["locked_qty"]))
            available = physical - locked
            safety = int(r["safety_stock"])
            return InventoryStockDTO(
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

    # --- TanGii (探吉) Accounting View Service Methods ---

    def get_accounting_kpis(self) -> AccountingKPIsDTO:
        income = self.accounting_service.get_income_statement()
        ar_aging = self.accounting_service.get_ar_aging()
        ap_aging = self.accounting_service.get_ap_aging()

        return AccountingKPIsDTO(
            revenue_formatted=f"NT$ {income.revenue:,.2f}",
            cogs_formatted=f"NT$ {income.cogs:,.2f}",
            gross_profit_formatted=f"NT$ {income.gross_profit:,.2f}",
            net_profit_formatted=f"NT$ {income.net_profit:,.2f}",
            ar_outstanding_formatted=f"NT$ {ar_aging.total_outstanding:,.2f}",
            ap_outstanding_formatted=f"NT$ {ap_aging.total_outstanding:,.2f}",
        )

    def get_journal_entries_view(self, limit: int = 50) -> List[JournalEntryViewDTO]:
        entries = self.accounting_service.get_journal_entries(limit=limit)
        active_accounts = {a["account_code"]: a["account_name"] for a in self.get_active_accounts()}

        event_badges = {
            "ERP_GOODS_RECEIVED": "bg-amber-100 text-amber-800 border-amber-300",
            "ERP_ORDER_SHIPPED": "bg-indigo-100 text-indigo-800 border-indigo-300",
            "ERP_INVOICE_ISSUED": "bg-emerald-100 text-emerald-800 border-emerald-300",
            "AR_RECEIPT": "bg-teal-100 text-teal-800 border-teal-300",
            "AP_PAYMENT": "bg-purple-100 text-purple-800 border-purple-300",
            "MANUAL": "bg-slate-100 text-slate-700 border-slate-300",
        }

        cust_map: Dict[str, str] = {}
        with self.db.transaction() as conn:
            c_rows = conn.execute("SELECT contact_id, company_name FROM crm_contacts").fetchall()
            cust_map = {r["contact_id"]: (r["company_name"] or "").strip() for r in c_rows if r["company_name"]}

        dtos: List[JournalEntryViewDTO] = []
        for e in entries:
            total_dr = sum((line.debit for line in e.lines), Decimal("0.0"))
            total_cr = sum((line.credit for line in e.lines), Decimal("0.0"))
            is_bal = abs(total_dr - total_cr) < Decimal("0.01")

            line_dtos = [
                JournalLineViewDTO(
                    account_code=l.account_code,
                    account_name=active_accounts.get(l.account_code, l.account_code),
                    debit_formatted=f"{l.debit:,.2f}" if l.debit > 0 else "-",
                    credit_formatted=f"{l.credit:,.2f}" if l.credit > 0 else "-",
                )
                for l in e.lines
            ]

            badge_class = event_badges.get(e.source_event, "bg-gray-100 text-gray-700 border-gray-300")

            desc = e.description
            if "收取客戶 CUST-" in desc:
                for cid, cname in cust_map.items():
                    target_old = f"收取客戶 {cid} 款項"
                    if target_old in desc:
                        desc = desc.replace(target_old, f"收取客戶 {cname} ({cid}) 款項")
                        break

            dtos.append(
                JournalEntryViewDTO(
                    entry_id=e.entry_id,
                    entry_date=e.entry_date.isoformat(),
                    source_event=e.source_event,
                    source_event_badge=badge_class,
                    reference_id=e.reference_id,
                    description=desc,
                    lines=line_dtos,
                    total_debit_formatted=f"NT$ {total_dr:,.2f}",
                    total_credit_formatted=f"NT$ {total_cr:,.2f}",
                    is_balanced=is_bal,
                )
            )
        return dtos

    def get_trial_balance_view(self, as_of_date: Optional[datetime.date] = None) -> TrialBalanceViewDTO:
        tb = self.accounting_service.get_trial_balance(as_of_date=as_of_date)

        type_badges = {
            AccountType.ASSET: "bg-blue-50 text-blue-700 border-blue-200",
            AccountType.LIABILITY: "bg-amber-50 text-amber-700 border-amber-200",
            AccountType.EQUITY: "bg-purple-50 text-purple-700 border-purple-200",
            AccountType.REVENUE: "bg-emerald-50 text-emerald-700 border-emerald-200",
            AccountType.EXPENSE: "bg-rose-50 text-rose-700 border-rose-200",
        }

        type_labels = {
            AccountType.ASSET: "資產",
            AccountType.LIABILITY: "負債",
            AccountType.EQUITY: "權益",
            AccountType.REVENUE: "收入",
            AccountType.EXPENSE: "費用與成本",
        }

        rows: List[TrialBalanceRowDTO] = []
        for item in tb.items:
            # Only display if there was activity or active account
            badge_class = type_badges.get(item.account_type, "bg-slate-50 text-slate-700 border-slate-200")
            type_label = type_labels.get(item.account_type, item.account_type.value)

            rows.append(
                TrialBalanceRowDTO(
                    account_code=item.account_code,
                    account_name=item.account_name,
                    account_type=type_label,
                    account_type_badge=badge_class,
                    debit_total_formatted=f"NT$ {item.debit_total:,.2f}",
                    credit_total_formatted=f"NT$ {item.credit_total:,.2f}",
                    balance_debit_formatted=f"NT$ {item.balance_debit:,.2f}" if item.balance_debit > 0 else "-",
                    balance_credit_formatted=f"NT$ {item.balance_credit:,.2f}" if item.balance_credit > 0 else "-",
                )
            )

        return TrialBalanceViewDTO(
            as_of_date=tb.as_of_date.isoformat(),
            rows=rows,
            total_debit_formatted=f"NT$ {tb.total_debit:,.2f}",
            total_credit_formatted=f"NT$ {tb.total_credit:,.2f}",
            is_balanced=tb.is_balanced,
        )

    def get_income_statement_view(
        self, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None
    ) -> IncomeStatementViewDTO:
        target_end_date = end_date or datetime.date.today()
        stmt = self.accounting_service.get_income_statement(start_date=start_date, end_date=target_end_date)

        rev = stmt.revenue
        gross_pct = (stmt.gross_profit / rev * 100) if rev > 0 else Decimal("0.0")
        net_pct = (stmt.net_profit / rev * 100) if rev > 0 else Decimal("0.0")

        period_text = (
            f"{start_date.isoformat()} 至 {target_end_date.isoformat()}"
            if start_date
            else f"成立至今 至 {target_end_date.isoformat()}"
        )

        return IncomeStatementViewDTO(
            period_str=period_text,
            revenue_formatted=f"NT$ {stmt.revenue:,.2f}",
            cogs_formatted=f"NT$ {stmt.cogs:,.2f}",
            gross_profit_formatted=f"NT$ {stmt.gross_profit:,.2f}",
            gross_margin_pct=f"{gross_pct:.2f}%",
            operating_expenses_formatted=f"NT$ {stmt.operating_expenses:,.2f}",
            net_profit_formatted=f"NT$ {stmt.net_profit:,.2f}",
            net_margin_pct=f"{net_pct:.2f}%",
            is_profitable=(stmt.net_profit >= 0),
        )

    def get_aging_view(self, report_type: str = "RECEIVABLE") -> AgingSummaryViewDTO:
        if report_type == "RECEIVABLE":
            aging = self.accounting_service.get_ar_aging()
            type_title = "應收帳款 (AR)"
        else:
            aging = self.accounting_service.get_ap_aging()
            type_title = "應付帳款 (AP)"

        bucket_badges = {
            AgingBucket.CURRENT: "bg-emerald-50 text-emerald-700 border-emerald-300",
            AgingBucket.DAYS_1_30: "bg-sky-50 text-sky-700 border-sky-300",
            AgingBucket.DAYS_31_60: "bg-amber-50 text-amber-700 border-amber-300",
            AgingBucket.DAYS_60_PLUS: "bg-rose-50 text-rose-700 border-rose-300",
        }

        contact_map: Dict[str, str] = {}
        if report_type == "RECEIVABLE" and aging.items:
            cust_ids = list({it.partner_name for it in aging.items if it.partner_name})
            if cust_ids:
                with self.db.transaction() as conn:
                    placeholders = ",".join("?" for _ in cust_ids)
                    rows = conn.execute(
                        f"SELECT contact_id, company_name FROM crm_contacts WHERE contact_id IN ({placeholders})",
                        cust_ids,
                    ).fetchall()
                    contact_map = {
                        r["contact_id"]: (r["company_name"] or "").strip()
                        for r in rows
                        if r["company_name"] and r["company_name"].strip()
                    }

        items: List[AgingItemViewDTO] = []
        for it in aging.items:
            badge_class = bucket_badges.get(it.bucket, "bg-gray-50 text-gray-700 border-gray-300")
            if it.days_overdue <= 0:
                overdue_color = "text-slate-400"
            elif 1 <= it.days_overdue <= 30:
                overdue_color = "text-sky-600 font-bold"
            elif 31 <= it.days_overdue <= 60:
                overdue_color = "text-amber-600 font-bold"
            else:
                overdue_color = "text-rose-600 font-bold"

            if report_type == "RECEIVABLE":
                raw_id = it.partner_name
                c_name = contact_map.get(raw_id)
                partner_display = c_name if c_name else raw_id
                partner_id = raw_id
            else:
                partner_display = it.partner_name
                partner_id = ""

            items.append(
                AgingItemViewDTO(
                    item_id=it.item_id,
                    reference_id=it.reference_id,
                    partner_name=partner_display,
                    amount_formatted=f"NT$ {it.amount:,.2f}",
                    paid_amount_formatted=f"NT$ {it.paid_amount:,.2f}",
                    outstanding_formatted=f"NT$ {it.outstanding_amount:,.2f}",
                    due_date=it.due_date.isoformat(),
                    days_overdue=it.days_overdue,
                    days_overdue_class=overdue_color,
                    bucket=it.bucket.value,
                    bucket_badge_class=badge_class,
                    status=it.status,
                    can_settle=(it.outstanding_amount > Decimal("0.0")),
                    partner_id=partner_id,
                )
            )

        return AgingSummaryViewDTO(
            report_type=type_title,
            total_outstanding_formatted=f"NT$ {aging.total_outstanding:,.2f}",
            current_amount_formatted=f"NT$ {aging.current_amount:,.2f}",
            days_1_30_formatted=f"NT$ {aging.days_1_30_amount:,.2f}",
            days_31_60_formatted=f"NT$ {aging.days_31_60_amount:,.2f}",
            days_60_plus_formatted=f"NT$ {aging.days_60_plus_amount:,.2f}",
            items=items,
        )

    def get_active_accounts(self) -> List[Dict[str, str]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT account_code, account_name, account_type FROM accounts WHERE is_active = 1 ORDER BY account_code ASC"
            ).fetchall()
            return [
                {
                    "account_code": r["account_code"],
                    "account_name": r["account_name"],
                    "account_type": r["account_type"],
                }
                for r in rows
            ]

    # =========================================================================
    # LiLai (哩來) CRM Web Queries
    # =========================================================================

    def get_crm_summary(self) -> CrmSummaryDTO:
        with self.db.transaction() as conn:
            row_total = conn.execute("SELECT COUNT(*) FROM crm_deals").fetchone()
            total_deals = row_total[0] if row_total else 0

            row_pipe = conn.execute(
                "SELECT COALESCE(SUM(expected_amount), 0), COUNT(*) FROM crm_deals WHERE stage IN ('LEAD', 'DISCOVERY', 'PROPOSAL')"
            ).fetchone()
            pipe_val = Decimal(str(row_pipe[0])) if row_pipe else Decimal("0.0")
            active_deals = row_pipe[1] if row_pipe else 0

            row_won = conn.execute(
                "SELECT COALESCE(SUM(expected_amount), 0), COUNT(*) FROM crm_deals WHERE stage = 'WON'"
            ).fetchone()
            won_val = Decimal(str(row_won[0])) if row_won else Decimal("0.0")
            won_deals = row_won[1] if row_won else 0

            row_cust = conn.execute("SELECT COUNT(*) FROM crm_contacts").fetchone()
            contacts_count = row_cust[0] if row_cust else 0

        return CrmSummaryDTO(
            total_deals_count=total_deals,
            pipeline_value_formatted=f"NT$ {pipe_val:,.2f}",
            active_deals_count=active_deals,
            won_deals_count=won_deals,
            won_revenue_formatted=f"NT$ {won_val:,.2f}",
            contacts_count=contacts_count,
        )

    def get_crm_kanban(self) -> CrmKanbanDTO:
        with self.db.transaction() as conn:
            deals_rows = conn.execute(
                """
                SELECT d.deal_id, d.contact_id, d.title, d.stage, d.expected_amount, d.converted_order_id,
                       c.company_name, c.contact_name
                FROM crm_deals d
                JOIN crm_contacts c ON d.contact_id = c.contact_id
                ORDER BY d.created_at DESC
                """
            ).fetchall()

            # Pre-fetch latest quote for each deal
            quotes_rows = conn.execute(
                """
                SELECT deal_id, quote_id, quote_number
                FROM crm_quotes
                ORDER BY created_at DESC
                """
            ).fetchall()
            latest_quote_map: Dict[str, Tuple[str, str]] = {}
            for qr in quotes_rows:
                did = qr["deal_id"]
                if did not in latest_quote_map:
                    latest_quote_map[did] = (qr["quote_id"], qr["quote_number"])

            # Pre-fetch deal items
            item_rows = conn.execute(
                """
                SELECT di.deal_id, di.sku, di.qty, di.unit_price, di.subtotal, p.name as product_name
                FROM crm_deal_items di
                LEFT JOIN products p ON di.sku = p.sku
                ORDER BY di.rowid ASC
                """
            ).fetchall()
            items_by_deal: Dict[str, List[Dict[str, Any]]] = {}
            for ir in item_rows:
                items_by_deal.setdefault(ir["deal_id"], []).append({
                    "sku": ir["sku"],
                    "product_name": ir["product_name"] or ir["sku"],
                    "qty": float(ir["qty"]),
                    "price": float(ir["unit_price"]),
                })

        lead_deals: List[DealCardDTO] = []
        discovery_deals: List[DealCardDTO] = []
        proposal_deals: List[DealCardDTO] = []
        won_deals: List[DealCardDTO] = []
        lost_deals: List[DealCardDTO] = []

        for r in deals_rows:
            deal_id = r["deal_id"]
            stage = r["stage"]
            converted_order_id = r["converted_order_id"]
            expected_amt = Decimal(str(r["expected_amount"]))
            quote_info = latest_quote_map.get(deal_id)
            quote_id = quote_info[0] if quote_info else None
            quote_num = quote_info[1] if quote_info else None

            deal_items = items_by_deal.get(deal_id, [])
            items_summary = "、".join(f"{it['product_name']} x {int(it['qty'])}" for it in deal_items)
            items_json_str = json.dumps(deal_items, ensure_ascii=False)

            label, badge_class = CRM_STAGE_BADGES.get(
                stage, (stage, "bg-slate-100 text-slate-700")
            )

            card = DealCardDTO(
                deal_id=deal_id,
                contact_id=r["contact_id"],
                company_name=r["company_name"],
                contact_name=r["contact_name"],
                title=r["title"],
                stage=stage,
                stage_label=label,
                stage_badge_class=badge_class,
                expected_amount_formatted=f"NT$ {expected_amt:,.2f}",
                converted_order_id=converted_order_id,
                latest_quote_id=quote_id,
                latest_quote_number=quote_num,
                items_summary=items_summary,
                items_json_str=items_json_str,
                can_advance_discovery=(stage == "LEAD"),
                can_advance_proposal=(stage in ("LEAD", "DISCOVERY")),
                can_convert_order=(stage == "PROPOSAL" and not converted_order_id and quote_id is not None),
                can_mark_lost=(stage in ("LEAD", "DISCOVERY", "PROPOSAL")),
                can_reopen=(stage == "LOST"),
            )

            if stage == "LEAD":
                lead_deals.append(card)
            elif stage == "DISCOVERY":
                discovery_deals.append(card)
            elif stage == "PROPOSAL":
                proposal_deals.append(card)
            elif stage == "WON":
                won_deals.append(card)
            elif stage == "LOST":
                lost_deals.append(card)

        return CrmKanbanDTO(
            lead_deals=lead_deals,
            discovery_deals=discovery_deals,
            proposal_deals=proposal_deals,
            won_deals=won_deals,
            lost_deals=lost_deals,
        )

    def list_contacts_with_stats(self) -> List[ContactRowDTO]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT c.contact_id, c.company_name, c.tax_id, c.contact_name, c.email, c.phone,
                       COUNT(d.deal_id) as deal_count
                FROM crm_contacts c
                LEFT JOIN crm_deals d ON c.contact_id = d.contact_id
                GROUP BY c.contact_id
                ORDER BY c.created_at DESC
                """
            ).fetchall()
            return [
                ContactRowDTO(
                    contact_id=r["contact_id"],
                    company_name=r["company_name"],
                    tax_id=r["tax_id"],
                    contact_name=r["contact_name"],
                    email=r["email"],
                    phone=r["phone"],
                    deal_count=r["deal_count"],
                )
                for r in rows
            ]

    def list_active_products_for_quote(self) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT sku, name, base_unit, selling_price FROM products WHERE is_active = 1 ORDER BY sku ASC"
            ).fetchall()
            return [
                {
                    "sku": r["sku"],
                    "name": r["name"],
                    "unit": r["base_unit"],
                    "price": float(r["selling_price"]),
                }
                for r in rows
            ]

    def list_active_products_for_po(self) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT sku, name, base_unit, cost_price, selling_price FROM products WHERE is_active = 1 ORDER BY sku ASC"
            ).fetchall()
            return [
                {
                    "sku": r["sku"],
                    "name": r["name"],
                    "unit": r["base_unit"],
                    "cost_price": float(r["cost_price"]),
                    "cost_price_formatted": f"NT$ {float(r['cost_price']):,.2f}",
                }
                for r in rows
            ]

    def list_warehouses_for_select(self) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT warehouse_id, name FROM warehouses WHERE is_active = 1 ORDER BY warehouse_id ASC"
            ).fetchall()
            return [
                {
                    "warehouse_id": r["warehouse_id"],
                    "name": r["name"],
                    "warehouse_name": r["name"],
                }
                for r in rows
            ]

    def list_purchase_orders(self, limit: int = 50) -> List[PurchaseOrderRowDTO]:
        with self.db.transaction() as conn:
            po_rows = conn.execute(
                """
                SELECT p.po_id, p.supplier_name, p.warehouse_id, p.status, p.total_amount, p.created_at,
                       g.grn_id
                FROM purchase_orders p
                LEFT JOIN goods_receipt_notes g ON p.po_id = g.po_id
                ORDER BY p.created_at DESC, p.po_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            if not po_rows:
                return []

            prod_rows = conn.execute("SELECT sku, name FROM products").fetchall()
            prod_name_map = {r["sku"]: r["name"] for r in prod_rows}

            results = []
            for r in po_rows:
                po_id = r["po_id"]
                item_rows = conn.execute(
                    """
                    SELECT sku, qty, unit_cost, subtotal
                    FROM purchase_order_items
                    WHERE po_id = ?
                    ORDER BY po_item_id ASC
                    """,
                    (po_id,),
                ).fetchall()

                items: List[PurchaseOrderItemDTO] = []
                summary_parts = []
                for it in item_rows:
                    sku = it["sku"]
                    pname = prod_name_map.get(sku, sku)
                    qty = Decimal(str(it["qty"]))
                    unit_cost = Decimal(str(it["unit_cost"]))
                    subtotal = Decimal(str(it["subtotal"]))
                    items.append(
                        PurchaseOrderItemDTO(
                            sku=sku,
                            product_name=pname,
                            qty=qty,
                            unit_cost=unit_cost,
                            subtotal=subtotal,
                            qty_formatted=f"{qty:,.0f}" if qty % 1 == 0 else f"{qty:,.2f}",
                            unit_cost_formatted=f"NT$ {unit_cost:,.2f}",
                            subtotal_formatted=f"NT$ {subtotal:,.2f}",
                        )
                    )
                    summary_parts.append(f"{pname} ({sku}) x {qty:g}")

                status = r["status"]
                label, badge_class = PO_STATUS_BADGES.get(
                    status, (status, "bg-slate-100 text-slate-700 border-slate-300")
                )
                tot = Decimal(str(r["total_amount"]))
                created_at_raw = r["created_at"]
                created_at_fmt = str(created_at_raw)[:16].replace("T", " ") if created_at_raw else "-"
                wh = r["warehouse_id"] if ("warehouse_id" in r.keys() and r["warehouse_id"]) else "WH-MAIN"

                results.append(
                    PurchaseOrderRowDTO(
                        po_id=po_id,
                        supplier_name=r["supplier_name"],
                        status=status,
                        status_label=label,
                        status_badge_class=badge_class,
                        total_amount_formatted=f"NT$ {tot:,.2f}",
                        created_at_formatted=created_at_fmt,
                        warehouse_id=wh,
                        items=items,
                        items_summary=", ".join(summary_parts) if summary_parts else "無明細",
                        can_submit=(status == "DRAFT"),
                        can_receive=(status == "SUBMITTED"),
                        grn_id=r["grn_id"],
                    )
                )
            return results

    def get_purchase_order_row(self, po_id: str) -> Optional[PurchaseOrderRowDTO]:
        with self.db.transaction() as conn:
            r = conn.execute(
                """
                SELECT p.po_id, p.supplier_name, p.warehouse_id, p.status, p.total_amount, p.created_at,
                       g.grn_id
                FROM purchase_orders p
                LEFT JOIN goods_receipt_notes g ON p.po_id = g.po_id
                WHERE p.po_id = ?
                """,
                (po_id,),
            ).fetchone()
            if not r:
                return None

            prod_rows = conn.execute("SELECT sku, name FROM products").fetchall()
            prod_name_map = {row["sku"]: row["name"] for row in prod_rows}

            item_rows = conn.execute(
                """
                SELECT sku, qty, unit_cost, subtotal
                FROM purchase_order_items
                WHERE po_id = ?
                ORDER BY po_item_id ASC
                """,
                (po_id,),
            ).fetchall()

            wh = r["warehouse_id"] if ("warehouse_id" in r.keys() and r["warehouse_id"]) else "WH-MAIN"

            items: List[PurchaseOrderItemDTO] = []
            summary_parts = []
            for it in item_rows:
                sku = it["sku"]
                pname = prod_name_map.get(sku, sku)
                qty = Decimal(str(it["qty"]))
                unit_cost = Decimal(str(it["unit_cost"]))
                subtotal = Decimal(str(it["subtotal"]))

                lvl = conn.execute(
                    "SELECT safety_stock FROM warehouse_stock_levels WHERE warehouse_id = ? AND sku = ?",
                    (wh, sku),
                ).fetchone()
                is_first = (lvl is None)
                if lvl:
                    current_safe = int(lvl["safety_stock"])
                else:
                    prod_row = conn.execute("SELECT safety_stock FROM products WHERE sku = ?", (sku,)).fetchone()
                    current_safe = int(prod_row["safety_stock"]) if (prod_row and prod_row["safety_stock"] is not None) else 10

                items.append(
                    PurchaseOrderItemDTO(
                        sku=sku,
                        product_name=pname,
                        qty=qty,
                        unit_cost=unit_cost,
                        subtotal=subtotal,
                        qty_formatted=f"{qty:,.0f}" if qty % 1 == 0 else f"{qty:,.2f}",
                        unit_cost_formatted=f"NT$ {unit_cost:,.2f}",
                        subtotal_formatted=f"NT$ {subtotal:,.2f}",
                        is_first_inbound=is_first,
                        current_safety_stock=current_safe,
                    )
                )
                summary_parts.append(f"{pname} ({sku}) x {qty:g}")

            status = r["status"]
            label, badge_class = PO_STATUS_BADGES.get(
                status, (status, "bg-slate-100 text-slate-700 border-slate-300")
            )
            tot = Decimal(str(r["total_amount"]))
            created_at_raw = r["created_at"]
            created_at_fmt = str(created_at_raw)[:16].replace("T", " ") if created_at_raw else "-"

            return PurchaseOrderRowDTO(
                po_id=po_id,
                supplier_name=r["supplier_name"],
                status=status,
                status_label=label,
                status_badge_class=badge_class,
                total_amount_formatted=f"NT$ {tot:,.2f}",
                created_at_formatted=created_at_fmt,
                warehouse_id=wh,
                items=items,
                items_summary=", ".join(summary_parts) if summary_parts else "無明細",
                can_submit=(status == "DRAFT"),
                can_receive=(status == "SUBMITTED"),
                grn_id=r["grn_id"],
            )


