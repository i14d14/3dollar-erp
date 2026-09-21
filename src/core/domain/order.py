from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from src.shared.base_models import DomainModel

class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class OrderChannel(str, Enum):
    DIRECT = "DIRECT"
    LINE = "LINE"
    CRM = "CRM"

class OrderItem(DomainModel):
    item_id: str
    order_id: str
    sku: str
    qty: Decimal
    unit_price: Decimal
    subtotal: Decimal
    shipped_qty: Decimal = Decimal("0.0")

    @property
    def remaining_qty(self) -> Decimal:
        return max(Decimal("0.0"), self.qty - self.shipped_qty)

class SalesOrder(DomainModel):
    order_id: str
    customer_id: str
    channel: OrderChannel = OrderChannel.DIRECT
    status: OrderStatus = OrderStatus.DRAFT
    total_amount: Decimal = Decimal("0.0")
    items: List[OrderItem] = []

    @property
    def is_fully_shipped(self) -> bool:
        return all(item.remaining_qty == Decimal("0.0") for item in self.items) if self.items else False

    @property
    def total_shipped_qty(self) -> Decimal:
        return sum((item.shipped_qty for item in self.items), Decimal("0.0"))

class DeliveryAllocation(DomainModel):
    allocation_id: str
    do_id: str
    order_id: str
    item_id: str
    sku: str
    allocated_qty: Decimal
    created_at: Optional[str] = None

class DeliveryOrder(DomainModel):
    do_id: str
    order_id: str
    warehouse_id: str
    tracking_number: Optional[str] = None
    allocations: List[DeliveryAllocation] = []
    shipped_at: Optional[str] = None


