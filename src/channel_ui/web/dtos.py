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
    warehouse_id: str = "WH-MAIN"
    suggested_qty: int = 1
    suggested_supplier: str = ""


@dataclass
class OrderRowDTO:
    order_id: str
    customer_id: str
    channel: str
    status: str
    status_badge_class: str
    total_amount_formatted: str
    created_at: str
    warehouse_id: str = "WH-MAIN"
    customer_name: Optional[str] = None
    do_id: Optional[str] = None
    tracking_number: Optional[str] = None
    invoice_number: Optional[str] = None
    is_reconciled: bool = False
    can_confirm: bool = False
    can_ship: bool = False
    can_invoice: bool = False
    has_shipping_label: bool = False
    has_invoice_pdf: bool = False
    delivery_orders_count: int = 0
    delivery_order_ids: List[str] = field(default_factory=list)


@dataclass
class OrderShipModalItemDTO:
    item_id: str
    order_id: str
    sku: str
    product_name: str
    qty: Decimal
    remaining_qty: Decimal
    shipped_qty: Decimal = Decimal("0.0")
    unit_price: Decimal = Decimal("0.0")
    subtotal: Decimal = Decimal("0.0")


@dataclass
class OrderShipModalDTO:
    order_id: str
    customer_id: str
    customer_name: Optional[str]
    warehouse_id: str
    items: List[OrderShipModalItemDTO]


@dataclass
class DeliveryAllocationViewDTO:
    allocation_id: str
    do_id: str
    order_id: str
    item_id: str
    sku: str
    product_name: str
    allocated_qty: Decimal
    created_at: Optional[str] = None


@dataclass
class DeliveryOrderViewDTO:
    do_id: str
    order_id: str
    warehouse_id: str
    tracking_number: str
    shipped_at: Optional[str] = None
    allocations: List[DeliveryAllocationViewDTO] = field(default_factory=list)


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
    partner_id: str = ""


@dataclass
class AgingSummaryViewDTO:
    report_type: str  # "應收帳款 (AR)" or "應付帳款 (AP)"
    total_outstanding_formatted: str
    current_amount_formatted: str
    days_1_30_formatted: str
    days_31_60_formatted: str
    days_60_plus_formatted: str
    items: List[AgingItemViewDTO]


# LiLai (哩來) CRM View DTOs
@dataclass
class CrmSummaryDTO:
    total_deals_count: int
    pipeline_value_formatted: str
    active_deals_count: int
    won_deals_count: int
    won_revenue_formatted: str
    contacts_count: int


@dataclass
class DealCardDTO:
    deal_id: str
    contact_id: str
    company_name: str
    contact_name: str
    title: str
    stage: str
    stage_label: str
    stage_badge_class: str
    expected_amount_formatted: str
    converted_order_id: Optional[str] = None
    latest_quote_id: Optional[str] = None
    latest_quote_number: Optional[str] = None
    items_summary: str = ""
    items_json_str: str = "[]"
    can_advance_discovery: bool = False
    can_advance_proposal: bool = False
    can_convert_order: bool = False
    can_mark_lost: bool = False
    can_reopen: bool = False


@dataclass
class ContactRowDTO:
    contact_id: str
    company_name: str
    tax_id: Optional[str]
    contact_name: str
    email: Optional[str]
    phone: Optional[str]
    deal_count: int


@dataclass
class CrmKanbanDTO:
    lead_deals: List[DealCardDTO]
    discovery_deals: List[DealCardDTO]
    proposal_deals: List[DealCardDTO]
    won_deals: List[DealCardDTO]
    lost_deals: List[DealCardDTO]


@dataclass
class PurchaseOrderItemDTO:
    sku: str
    product_name: str
    qty: Decimal
    unit_cost: Decimal
    subtotal: Decimal
    qty_formatted: str
    unit_cost_formatted: str
    subtotal_formatted: str
    is_first_inbound: bool = False
    current_safety_stock: int = 10


@dataclass
class PurchaseOrderRowDTO:
    po_id: str
    supplier_name: str
    status: str
    status_label: str
    status_badge_class: str
    total_amount_formatted: str
    created_at_formatted: str
    warehouse_id: str = "WH-MAIN"
    items: List[PurchaseOrderItemDTO] = field(default_factory=list)
    items_summary: str = ""
    can_submit: bool = False
    can_receive: bool = False
    grn_id: Optional[str] = None


