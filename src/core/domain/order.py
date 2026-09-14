from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from src.shared.base_models import DomainModel

class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
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

class SalesOrder(DomainModel):
    order_id: str
    customer_id: str
    channel: OrderChannel = OrderChannel.DIRECT
    status: OrderStatus = OrderStatus.DRAFT
    total_amount: Decimal = Decimal("0.0")
    items: List[OrderItem] = []

class DeliveryOrder(DomainModel):
    do_id: str
    order_id: str
    warehouse_id: str
    tracking_number: Optional[str] = None
