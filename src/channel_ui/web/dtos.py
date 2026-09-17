from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional


@dataclass
class LowStockItemDTO:
    sku: str
    product_name: str
    physical_balance: Decimal
    safety_stock: int
    warehouse_name: str


@dataclass
class OrderRowDTO:
    order_id: str
    customer_id: str
    channel: str
    status: str
    status_badge_class: str
    total_amount_formatted: str
    created_at: str
    do_id: Optional[str] = None
    tracking_number: Optional[str] = None
    invoice_number: Optional[str] = None
    is_reconciled: bool = False
    can_confirm: bool = False
    can_ship: bool = False
    can_invoice: bool = False
    has_shipping_label: bool = False
    has_invoice_pdf: bool = False


@dataclass
class DashboardSummaryDTO:
    today_orders_count: int
    pending_shipments_count: int
    low_stock_alerts_count: int
    unpaid_ar_amount_formatted: str
    recent_orders: List[OrderRowDTO] = field(default_factory=list)
    low_stock_items: List[LowStockItemDTO] = field(default_factory=list)


@dataclass
class InventoryStockDTO:
    warehouse_id: str
    warehouse_name: str
    sku: str
    product_name: str
    physical_balance: Decimal
    locked_qty: Decimal
    available_qty: Decimal
    safety_stock: int
    is_low_stock: bool


@dataclass
class StockLedgerRowDTO:
    ledger_id: str
    warehouse_id: str
    warehouse_name: str
    sku: str
    product_name: str
    qty_delta_formatted: str
    qty_delta_class: str
    balance_after: Decimal
    reference_type: str
    reference_id: str
    notes: str
    created_at: str


# TanGii (探吉) Accounting View DTOs
@dataclass
class AccountingKPIsDTO:
    revenue_formatted: str
    cogs_formatted: str
    gross_profit_formatted: str
    net_profit_formatted: str
    ar_outstanding_formatted: str
    ap_outstanding_formatted: str


@dataclass
class JournalLineViewDTO:
    account_code: str
    account_name: str
    debit_formatted: str
    credit_formatted: str


@dataclass
class JournalEntryViewDTO:
    entry_id: str
    entry_date: str
    source_event: str
    source_event_badge: str
    reference_id: str
    description: str
    lines: List[JournalLineViewDTO]
    total_debit_formatted: str
    total_credit_formatted: str
    is_balanced: bool


@dataclass
class TrialBalanceRowDTO:
    account_code: str
    account_name: str
    account_type: str
    account_type_badge: str
    debit_total_formatted: str
    credit_total_formatted: str
    balance_debit_formatted: str
    balance_credit_formatted: str


@dataclass
class TrialBalanceViewDTO:
    as_of_date: str
    rows: List[TrialBalanceRowDTO]
    total_debit_formatted: str
    total_credit_formatted: str
    is_balanced: bool


@dataclass
class IncomeStatementViewDTO:
    period_str: str
    revenue_formatted: str
    cogs_formatted: str
    gross_profit_formatted: str
    gross_margin_pct: str
    operating_expenses_formatted: str
    net_profit_formatted: str
    net_margin_pct: str
    is_profitable: bool


@dataclass
class AgingItemViewDTO:
    item_id: str
    reference_id: str
    partner_name: str
    amount_formatted: str
    paid_amount_formatted: str
    outstanding_formatted: str
    due_date: str
    days_overdue: int
    days_overdue_class: str
    bucket: str
    bucket_badge_class: str
    status: str
    can_settle: bool


@dataclass
class AgingSummaryViewDTO:
    report_type: str  # "應收帳款 (AR)" or "應付帳款 (AP)"
    total_outstanding_formatted: str
    current_amount_formatted: str
    days_1_30_formatted: str
    days_31_60_formatted: str
    days_60_plus_formatted: str
    items: List[AgingItemViewDTO]

