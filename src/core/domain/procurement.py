from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from src.shared.base_models import DomainModel

class POStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"

class PurchaseOrderItem(DomainModel):
    po_item_id: str
    po_id: str
    sku: str
    qty: Decimal
    unit_cost: Decimal
    subtotal: Decimal

class PurchaseOrder(DomainModel):
    po_id: str
    supplier_name: str
    warehouse_id: str = "WH-MAIN"
    status: POStatus = POStatus.DRAFT
    total_amount: Decimal = Decimal("0.0")
    items: List[PurchaseOrderItem] = []
    created_at: Optional[str] = None

class GoodsReceiptNote(DomainModel):
    grn_id: str
    po_id: str
    warehouse_id: str
