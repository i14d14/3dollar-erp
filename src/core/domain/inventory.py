from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import Optional
from src.shared.base_models import DomainModel

class ReferenceType(str, Enum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"

class LockStatus(str, Enum):
    LOCKED = "LOCKED"
    RELEASED = "RELEASED"
    FULFILLED = "FULFILLED"

class Warehouse(DomainModel):
    warehouse_id: str
    name: str
    is_active: bool = True

class Product(DomainModel):
    sku: str
    name: str
    base_unit: str = "PCS"
    cost_price: Decimal = Decimal("0.0")
    selling_price: Decimal = Decimal("0.0")
    safety_stock: int = 0
    is_active: bool = True

class StockLedgerEntry(DomainModel):
    ledger_id: str
    warehouse_id: str
    sku: str
    qty_delta: Decimal
    balance_after: Decimal
    unit_cost: Decimal
    reference_type: ReferenceType
    reference_id: str
    notes: Optional[str] = None

class StockLock(DomainModel):
    lock_id: str
    order_id: str
    warehouse_id: str
    sku: str
    locked_qty: Decimal
    status: LockStatus = LockStatus.LOCKED


class InventoryError(Exception):
    """Base exception for inventory domain."""
    pass


class InsufficientStockError(InventoryError):
    """Raised when stock balance or available stock is insufficient for operation."""
    pass


class WarehouseNotFoundError(InventoryError):
    """Raised when a warehouse ID does not exist."""
    pass


class ProductNotFoundError(InventoryError):
    """Raised when a SKU does not exist."""
    pass


class StockLockNotFoundError(InventoryError):
    """Raised when a stock lock cannot be found."""
    pass


class InvalidLockStatusError(InventoryError):
    """Raised when an invalid operation is attempted on a stock lock."""
    pass

