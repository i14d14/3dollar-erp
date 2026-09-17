from __future__ import annotations
import datetime
from decimal import Decimal
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
    IncomeStatementViewDTO,
    InventoryStockDTO,
    JournalEntryViewDTO,
    JournalLineViewDTO,
    LowStockItemDTO,
    OrderRowDTO,
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
    "SHIPPED": "bg-amber-100 text-amber-700 border border-amber-300",
    "COMPLETED": "bg-emerald-100 text-emerald-700 border border-emerald-300",
    "CANCELLED": "bg-rose-100 text-rose-700 border border-rose-300",
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

            dtos.append(
                JournalEntryViewDTO(
                    entry_id=e.entry_id,
                    entry_date=e.entry_date.isoformat(),
                    source_event=e.source_event,
                    source_event_badge=badge_class,
                    reference_id=e.reference_id,
                    description=e.description,
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

            items.append(
                AgingItemViewDTO(
                    item_id=it.item_id,
                    reference_id=it.reference_id,
                    partner_name=it.partner_name,
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


