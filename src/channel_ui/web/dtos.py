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
