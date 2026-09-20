from __future__ import annotations
import sqlite3
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from src.core.domain.inventory import (
    InsufficientStockError,
    InvalidLockStatusError,
    LockStatus,
    Product,
    ProductNotFoundError,
    ReferenceType,
    StockLedgerEntry,
    StockLock,
    StockLockNotFoundError,
    Warehouse,
    WarehouseNotFoundError,
)
from src.shared.database import Database, default_db


class InventoryService:
    def __init__(self, db: Database = default_db) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Warehouse & Product Catalog Management
    # -------------------------------------------------------------------------

    def create_warehouse(self, warehouse_id: str, name: str) -> Warehouse:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO warehouses (warehouse_id, name, is_active) VALUES (?, ?, 1)",
                (warehouse_id, name),
            )
        return Warehouse(warehouse_id=warehouse_id, name=name, is_active=True)

    def get_warehouse(self, warehouse_id: str) -> Optional[Warehouse]:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT warehouse_id, name, is_active FROM warehouses WHERE warehouse_id = ?",
                (warehouse_id,),
            ).fetchone()
        if not row:
            return None
        return Warehouse(warehouse_id=row["warehouse_id"], name=row["name"], is_active=bool(row["is_active"]))

    def list_warehouses(self) -> List[Warehouse]:
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT warehouse_id, name, is_active FROM warehouses WHERE is_active = 1").fetchall()
        return [Warehouse(warehouse_id=r["warehouse_id"], name=r["name"], is_active=bool(r["is_active"])) for r in rows]

    def create_product(
        self,
        sku: str,
        name: str,
        base_unit: str = "PCS",
        cost_price: Decimal = Decimal("0.0"),
        selling_price: Decimal = Decimal("0.0"),
        safety_stock: int = 0,
    ) -> Product:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO products (sku, name, base_unit, cost_price, selling_price, safety_stock, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (sku, name, base_unit, float(cost_price), float(selling_price), safety_stock),
            )
        return Product(
            sku=sku,
            name=name,
            base_unit=base_unit,
            cost_price=cost_price,
            selling_price=selling_price,
            safety_stock=safety_stock,
            is_active=True,
        )

    def get_product(self, sku: str) -> Optional[Product]:
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT sku, name, base_unit, cost_price, selling_price, safety_stock, is_active
                FROM products WHERE sku = ?
                """,
                (sku,),
            ).fetchone()
        if not row:
            return None
        return Product(
            sku=row["sku"],
            name=row["name"],
            base_unit=row["base_unit"],
            cost_price=Decimal(str(row["cost_price"])),
            selling_price=Decimal(str(row["selling_price"])),
            safety_stock=row["safety_stock"],
            is_active=bool(row["is_active"]),
        )

    def list_products(self) -> List[Product]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT sku, name, base_unit, cost_price, selling_price, safety_stock, is_active
                FROM products WHERE is_active = 1
                """
            ).fetchall()
        return [
            Product(
                sku=r["sku"],
                name=r["name"],
                base_unit=r["base_unit"],
                cost_price=Decimal(str(r["cost_price"])),
                selling_price=Decimal(str(r["selling_price"])),
                safety_stock=r["safety_stock"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    # -------------------------------------------------------------------------
    # Stock Ledger & Balance Calculation (Append-Only)
    # -------------------------------------------------------------------------

    def get_stock_balance(self, warehouse_id: str, sku: str) -> Decimal:
        """Calculate physical stock balance directly from the latest stock ledger entry."""
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT balance_after FROM stock_ledger
                WHERE warehouse_id = ? AND sku = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (warehouse_id, sku),
            ).fetchone()
            if row:
                return Decimal(str(row["balance_after"]))
            return Decimal("0.0")

    def get_locked_stock(self, warehouse_id: str, sku: str) -> Decimal:
        """Get sum of actively reserved stock locks for this warehouse and SKU."""
        with self.db.transaction() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(locked_qty), 0) AS total_locked
                FROM stock_locks
                WHERE warehouse_id = ? AND sku = ? AND status = 'LOCKED'
                """,
                (warehouse_id, sku),
            ).fetchone()
            return Decimal(str(row["total_locked"])) if row else Decimal("0.0")

    def get_available_stock(self, warehouse_id: str, sku: str) -> Decimal:
        """Available stock = Physical balance - Active virtual locks."""
        balance = self.get_stock_balance(warehouse_id, sku)
        locked = self.get_locked_stock(warehouse_id, sku)
        return balance - locked

    def adjust_stock(
        self,
        warehouse_id: str,
        sku: str,
        qty_delta: Decimal,
        unit_cost: Decimal,
        reference_id: str,
        notes: Optional[str] = None,
    ) -> StockLedgerEntry:
        """Append an inventory adjustment or initial balance into the stock ledger."""
        with self.db.transaction() as conn:
            self._ensure_warehouse_and_product(conn, warehouse_id, sku)
            current_balance = self._get_balance_internal(conn, warehouse_id, sku)
            new_balance = current_balance + qty_delta

            if new_balance < Decimal("0.0"):
                raise InsufficientStockError(
                    f"庫存調整失敗：商品 {sku} 在倉庫 {warehouse_id} 調整後期末餘額 ({new_balance}) 不得為負數 (Insufficient stock balance)"
                )

            ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
            conn.execute(
                """
                INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    warehouse_id,
                    sku,
                    float(qty_delta),
                    float(new_balance),
                    float(unit_cost),
                    ReferenceType.ADJUSTMENT.value,
                    reference_id,
                    notes,
                ),
            )
            return StockLedgerEntry(
                ledger_id=ledger_id,
                warehouse_id=warehouse_id,
                sku=sku,
                qty_delta=qty_delta,
                balance_after=new_balance,
                unit_cost=unit_cost,
                reference_type=ReferenceType.ADJUSTMENT,
                reference_id=reference_id,
                notes=notes,
            )

    def transfer_stock(
        self,
        from_warehouse_id: str,
        to_warehouse_id: str,
        sku: str,
        qty: Decimal,
        reference_id: str,
        notes: Optional[str] = None,
    ) -> Tuple[StockLedgerEntry, StockLedgerEntry]:
        """Atomically transfer stock between two warehouses with strict available balance checks."""
        if qty <= Decimal("0.0"):
            raise ValueError("調撥數量必須大於 0 (Transfer quantity must be strictly positive)")
        if from_warehouse_id == to_warehouse_id:
            raise ValueError("無法調撥至同一倉庫 (Cannot transfer stock to the same warehouse)")

        with self.db.transaction() as conn:
            self._ensure_warehouse_and_product(conn, from_warehouse_id, sku)
            self._ensure_warehouse_and_product(conn, to_warehouse_id, sku)

            # Check available stock in source warehouse
            from_balance = self._get_balance_internal(conn, from_warehouse_id, sku)
            from_locked = self._get_locked_internal(conn, from_warehouse_id, sku)
            available = from_balance - from_locked

            if available < qty:
                raise InsufficientStockError(
                    f"調撥失敗：來源倉庫 {from_warehouse_id} 之商品 {sku} 可用庫存不足（可用量：{available}，需求量：{qty}） (Insufficient available stock)"
                )

            product = self._get_product_internal(conn, sku)
            unit_cost = product.cost_price

            # 1. Deduct from source warehouse
            from_ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
            new_from_balance = from_balance - qty
            conn.execute(
                """
                INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_ledger_id,
                    from_warehouse_id,
                    sku,
                    float(-qty),
                    float(new_from_balance),
                    float(unit_cost),
                    ReferenceType.TRANSFER.value,
                    reference_id,
                    f"Outward transfer to {to_warehouse_id}. {notes or ''}".strip(),
                ),
            )

            # 2. Add to destination warehouse
            to_balance = self._get_balance_internal(conn, to_warehouse_id, sku)
            to_ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
            new_to_balance = to_balance + qty
            conn.execute(
                """
                INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    to_ledger_id,
                    to_warehouse_id,
                    sku,
                    float(qty),
                    float(new_to_balance),
                    float(unit_cost),
                    ReferenceType.TRANSFER.value,
                    reference_id,
                    f"Inward transfer from {from_warehouse_id}. {notes or ''}".strip(),
                ),
            )

            out_entry = StockLedgerEntry(
                ledger_id=from_ledger_id,
                warehouse_id=from_warehouse_id,
                sku=sku,
                qty_delta=-qty,
                balance_after=new_from_balance,
                unit_cost=unit_cost,
                reference_type=ReferenceType.TRANSFER,
                reference_id=reference_id,
                notes=f"Outward transfer to {to_warehouse_id}",
            )
            in_entry = StockLedgerEntry(
                ledger_id=to_ledger_id,
                warehouse_id=to_warehouse_id,
                sku=sku,
                qty_delta=qty,
                balance_after=new_to_balance,
                unit_cost=unit_cost,
                reference_type=ReferenceType.TRANSFER,
                reference_id=reference_id,
                notes=f"Inward transfer from {from_warehouse_id}",
            )
            return out_entry, in_entry

    # -------------------------------------------------------------------------
    # Virtual Stock Locks (Anti-Overselling Guard)
    # -------------------------------------------------------------------------

    def acquire_stock_lock(self, order_id: str, warehouse_id: str, sku: str, qty: Decimal) -> StockLock:
        """Lock virtual stock for an order before fulfillment."""
        if qty <= Decimal("0.0"):
            raise ValueError("鎖庫數量必須大於 0 (Lock quantity must be strictly positive)")

        with self.db.transaction() as conn:
            self._ensure_warehouse_and_product(conn, warehouse_id, sku)
            balance = self._get_balance_internal(conn, warehouse_id, sku)
            locked = self._get_locked_internal(conn, warehouse_id, sku)
            available = balance - locked

            if available < qty:
                raise InsufficientStockError(
                    f"無法鎖定訂單 {order_id} 庫存：倉庫 {warehouse_id} 之商品 {sku} 可用庫存不足（可用量：{available}，需求量：{qty}） (Insufficient available stock)"
                )

            lock_id = f"LOCK-{uuid.uuid4().hex[:12].upper()}"
            conn.execute(
                """
                INSERT INTO stock_locks (lock_id, order_id, warehouse_id, sku, locked_qty, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lock_id, order_id, warehouse_id, sku, float(qty), LockStatus.LOCKED.value),
            )
            return StockLock(
                lock_id=lock_id,
                order_id=order_id,
                warehouse_id=warehouse_id,
                sku=sku,
                locked_qty=qty,
                status=LockStatus.LOCKED,
            )

    def release_stock_lock(self, order_id: str, sku: Optional[str] = None) -> int:
        """Release active stock lock(s) back to available pool (e.g. upon order cancellation)."""
        with self.db.transaction() as conn:
            if sku:
                cursor = conn.execute(
                    "UPDATE stock_locks SET status = 'RELEASED' WHERE order_id = ? AND sku = ? AND status = 'LOCKED'",
                    (order_id, sku),
                )
            else:
                cursor = conn.execute(
                    "UPDATE stock_locks SET status = 'RELEASED' WHERE order_id = ? AND status = 'LOCKED'",
                    (order_id,),
                )
            return cursor.rowcount

    def fulfill_stock_lock(
        self,
        order_id: str,
        warehouse_id: str,
        sku: str,
        qty: Decimal,
        unit_cost: Decimal,
        reference_id: str,
    ) -> StockLedgerEntry:
        """Fulfill a stock lock: update lock to FULFILLED and append deduction to stock ledger."""
        with self.db.transaction() as conn:
            # Check lock
            lock_row = conn.execute(
                """
                SELECT lock_id, locked_qty, status FROM stock_locks
                WHERE order_id = ? AND warehouse_id = ? AND sku = ? AND status = 'LOCKED'
                LIMIT 1
                """,
                (order_id, warehouse_id, sku),
            ).fetchone()

            if not lock_row:
                raise StockLockNotFoundError(
                    f"查無訂單 {order_id} 於倉庫 {warehouse_id} 針對品號 {sku} 之有效鎖庫記錄 (Stock lock not found)"
                )

            # Update lock status: if partial fulfillment, reduce locked quantity; if complete, mark FULFILLED
            locked_amount = Decimal(str(lock_row["locked_qty"]))
            if qty < locked_amount:
                conn.execute(
                    "UPDATE stock_locks SET locked_qty = ? WHERE lock_id = ?",
                    (float(locked_amount - qty), lock_row["lock_id"]),
                )
            else:
                conn.execute(
                    "UPDATE stock_locks SET status = 'FULFILLED' WHERE lock_id = ?",
                    (lock_row["lock_id"],),
                )

            # Deduct physical stock
            current_balance = self._get_balance_internal(conn, warehouse_id, sku)
            new_balance = current_balance - qty
            if new_balance < Decimal("0.0"):
                raise InsufficientStockError(
                    f"扣庫失敗：商品 {sku} 在倉庫 {warehouse_id} 出庫後實體庫存將不足 ({new_balance}) (Physical stock underflow)"
                )

            ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
            conn.execute(
                """
                INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    warehouse_id,
                    sku,
                    float(-qty),
                    float(new_balance),
                    float(unit_cost),
                    ReferenceType.SALE.value,
                    reference_id,
                    f"Order fulfillment: {order_id}",
                ),
            )
            return StockLedgerEntry(
                ledger_id=ledger_id,
                warehouse_id=warehouse_id,
                sku=sku,
                qty_delta=-qty,
                balance_after=new_balance,
                unit_cost=unit_cost,
                reference_type=ReferenceType.SALE,
                reference_id=reference_id,
                notes=f"Order fulfillment: {order_id}",
            )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _ensure_warehouse_and_product(self, conn: sqlite3.Connection, warehouse_id: str, sku: str) -> None:
        wh = conn.execute("SELECT 1 FROM warehouses WHERE warehouse_id = ?", (warehouse_id,)).fetchone()
        if not wh:
            raise WarehouseNotFoundError(f"倉庫 '{warehouse_id}' 不存在 (Warehouse does not exist)")
        prod = conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
        if not prod:
            raise ProductNotFoundError(f"商品品號 '{sku}' 不存在 (Product does not exist)")

    def _get_balance_internal(self, conn: sqlite3.Connection, warehouse_id: str, sku: str) -> Decimal:
        row = conn.execute(
            """
            SELECT balance_after FROM stock_ledger
            WHERE warehouse_id = ? AND sku = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (warehouse_id, sku),
        ).fetchone()
        return Decimal(str(row["balance_after"])) if row else Decimal("0.0")

    def _get_locked_internal(self, conn: sqlite3.Connection, warehouse_id: str, sku: str) -> Decimal:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(locked_qty), 0) AS total_locked
            FROM stock_locks
            WHERE warehouse_id = ? AND sku = ? AND status = 'LOCKED'
            """,
            (warehouse_id, sku),
        ).fetchone()
        return Decimal(str(row["total_locked"])) if row else Decimal("0.0")

    def _get_product_internal(self, conn: sqlite3.Connection, sku: str) -> Product:
        row = conn.execute(
            "SELECT sku, name, base_unit, cost_price, selling_price, safety_stock, is_active FROM products WHERE sku = ?",
            (sku,),
        ).fetchone()
        if not row:
            raise ProductNotFoundError(f"Product SKU {sku} not found")
        return Product(
            sku=row["sku"],
            name=row["name"],
            base_unit=row["base_unit"],
            cost_price=Decimal(str(row["cost_price"])),
            selling_price=Decimal(str(row["selling_price"])),
            safety_stock=row["safety_stock"],
            is_active=bool(row["is_active"]),
        )
