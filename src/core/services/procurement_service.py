from __future__ import annotations
import sqlite3
import uuid
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from src.core.domain.inventory import ReferenceType
from src.core.domain.procurement import GoodsReceiptNote, POStatus, PurchaseOrder, PurchaseOrderItem
from src.core.ports.event_bus_port import EventBusPort
from src.shared.base_models import DomainEvent
from src.shared.database import Database, default_db


class ProcurementService:
    def __init__(self, db: Database, event_bus: EventBusPort) -> None:
        self.db = db
        self.event_bus = event_bus

    def create_purchase_order(
        self,
        supplier_name: str,
        items: List[Tuple[str, Decimal, Decimal]],  # (sku, qty, unit_cost)
        warehouse_id: str = "WH-MAIN",
    ) -> PurchaseOrder:
        """Create a new purchase order in DRAFT status."""
        if not items:
            raise ValueError("Purchase order must have at least one item")

        po_id = f"PO-{uuid.uuid4().hex[:10].upper()}"
        total_amount = Decimal("0.0")
        po_items: List[PurchaseOrderItem] = []

        with self.db.transaction() as conn:
            # 1. Validate items and calculate total amount
            item_data = []
            for sku, qty, unit_cost in items:
                if qty <= Decimal("0.0") or unit_cost < Decimal("0.0"):
                    raise ValueError(f"Invalid quantity ({qty}) or unit cost ({unit_cost}) for SKU {sku}")
                prod = conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
                if not prod:
                    raise ValueError(f"Product SKU {sku} does not exist")
                subtotal = qty * unit_cost
                total_amount += subtotal
                item_data.append((sku, qty, unit_cost, subtotal))

            # 2. Insert parent purchase_orders first
            conn.execute(
                """
                INSERT INTO purchase_orders (po_id, supplier_name, warehouse_id, status, total_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (po_id, supplier_name, warehouse_id, POStatus.DRAFT.value, float(total_amount)),
            )

            # 3. Insert child purchase_order_items
            for sku, qty, unit_cost, subtotal in item_data:
                item_id = f"POI-{uuid.uuid4().hex[:10].upper()}"
                conn.execute(
                    """
                    INSERT INTO purchase_order_items (po_item_id, po_id, sku, qty, unit_cost, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, po_id, sku, float(qty), float(unit_cost), float(subtotal)),
                )
                po_items.append(
                    PurchaseOrderItem(
                        po_item_id=item_id,
                        po_id=po_id,
                        sku=sku,
                        qty=qty,
                        unit_cost=unit_cost,
                        subtotal=subtotal,
                    )
                )

        return PurchaseOrder(
            po_id=po_id,
            supplier_name=supplier_name,
            warehouse_id=warehouse_id,
            status=POStatus.DRAFT,
            total_amount=total_amount,
            items=po_items,
        )

    def submit_purchase_order(self, po_id: str) -> PurchaseOrder:
        """Submit purchase order for supplier fulfillment."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
            if not row:
                raise ValueError(f"Purchase order {po_id} not found")
            if row["status"] != POStatus.DRAFT.value:
                raise ValueError(f"Cannot submit PO in status '{row['status']}'")

            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE po_id = ?",
                (POStatus.SUBMITTED.value, po_id),
            )
        return self.get_purchase_order(po_id)

    def cancel_purchase_order(self, po_id: str) -> PurchaseOrder:
        """Cancel a purchase order in DRAFT or SUBMITTED status prior to goods receipt."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
            if not row:
                raise ValueError(f"查無採購單 {po_id} (Purchase order not found)")
            if row["status"] == POStatus.RECEIVED.value:
                raise ValueError(f"無法取消採購單 {po_id}：已完成驗收入庫 (Cannot cancel received PO)")
            if row["status"] == POStatus.CANCELLED.value:
                return self.get_purchase_order(po_id)

            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE po_id = ?",
                (POStatus.CANCELLED.value, po_id),
            )
        return self.get_purchase_order(po_id)

    def revert_submit_purchase_order(self, po_id: str) -> PurchaseOrder:
        """Revert a submitted purchase order back to DRAFT."""
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
            if not row:
                raise ValueError(f"查無採購單 {po_id} (Purchase order not found)")
            if row["status"] != POStatus.SUBMITTED.value:
                raise ValueError(f"無法撤回下訂：採購單 {po_id} 目前狀態為 '{row['status']}'，僅已送出 (SUBMITTED) 狀態可撤回 (Cannot revert PO submit)")

            grn_row = conn.execute("SELECT 1 FROM goods_receipt_notes WHERE po_id = ?", (po_id,)).fetchone()
            if grn_row:
                raise ValueError(f"無法撤回下訂：採購單 {po_id} 已產生驗收入庫紀錄 (GRN already exists)")

            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE po_id = ?",
                (POStatus.DRAFT.value, po_id),
            )
        return self.get_purchase_order(po_id)


    def get_purchase_order(self, po_id: str) -> PurchaseOrder:
        """Fetch a purchase order with items."""
        with self.db.transaction() as conn:
            po_row = conn.execute(
                "SELECT po_id, supplier_name, warehouse_id, status, total_amount, created_at FROM purchase_orders WHERE po_id = ?",
                (po_id,),
            ).fetchone()
            if not po_row:
                raise ValueError(f"Purchase order {po_id} not found")

            items_rows = conn.execute(
                "SELECT po_item_id, po_id, sku, qty, unit_cost, subtotal FROM purchase_order_items WHERE po_id = ?",
                (po_id,),
            ).fetchall()

            items = [
                PurchaseOrderItem(
                    po_item_id=r["po_item_id"],
                    po_id=r["po_id"],
                    sku=r["sku"],
                    qty=Decimal(str(r["qty"])),
                    unit_cost=Decimal(str(r["unit_cost"])),
                    subtotal=Decimal(str(r["subtotal"])),
                )
                for r in items_rows
            ]

            wh = po_row["warehouse_id"] if ("warehouse_id" in po_row.keys() and po_row["warehouse_id"]) else "WH-MAIN"

            return PurchaseOrder(
                po_id=po_row["po_id"],
                supplier_name=po_row["supplier_name"],
                warehouse_id=wh,
                status=POStatus(po_row["status"]),
                total_amount=Decimal(str(po_row["total_amount"])),
                items=items,
                created_at=str(po_row["created_at"]) if po_row["created_at"] else None,
            )

    def list_purchase_orders(self, limit: int = 50) -> List[PurchaseOrder]:
        """Fetch recent purchase orders with items."""
        with self.db.transaction() as conn:
            po_rows = conn.execute(
                """
                SELECT po_id, supplier_name, warehouse_id, status, total_amount, created_at
                FROM purchase_orders
                ORDER BY created_at DESC, po_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            if not po_rows:
                return []

            result = []
            for po_row in po_rows:
                items_rows = conn.execute(
                    "SELECT po_item_id, po_id, sku, qty, unit_cost, subtotal FROM purchase_order_items WHERE po_id = ?",
                    (po_row["po_id"],),
                ).fetchall()

                items = [
                    PurchaseOrderItem(
                        po_item_id=r["po_item_id"],
                        po_id=r["po_id"],
                        sku=r["sku"],
                        qty=Decimal(str(r["qty"])),
                        unit_cost=Decimal(str(r["unit_cost"])),
                        subtotal=Decimal(str(r["subtotal"])),
                    )
                    for r in items_rows
                ]

                wh = po_row["warehouse_id"] if ("warehouse_id" in po_row.keys() and po_row["warehouse_id"]) else "WH-MAIN"

                result.append(
                    PurchaseOrder(
                        po_id=po_row["po_id"],
                        supplier_name=po_row["supplier_name"],
                        warehouse_id=wh,
                        status=POStatus(po_row["status"]),
                        total_amount=Decimal(str(po_row["total_amount"])),
                        items=items,
                        created_at=str(po_row["created_at"]) if po_row["created_at"] else None,
                    )
                )

            return result

    def receive_goods(
        self,
        po_id: str,
        warehouse_id: Optional[str] = None,
        safety_stocks: Optional[Dict[str, int]] = None,
    ) -> GoodsReceiptNote:
        """Process goods receipt (GRN), calculate moving average cost, and update stock ledger."""
        po = self.get_purchase_order(po_id)
        if po.status != POStatus.SUBMITTED:
            raise ValueError(f"Cannot receive PO {po_id}: status is '{po.status.value}', expected 'SUBMITTED'")

        target_wh = warehouse_id or po.warehouse_id or "WH-MAIN"
        grn_id = f"GRN-{uuid.uuid4().hex[:10].upper()}"

        with self.db.transaction() as conn:
            # Validate warehouse
            wh = conn.execute("SELECT 1 FROM warehouses WHERE warehouse_id = ?", (target_wh,)).fetchone()
            if not wh:
                raise ValueError(f"Warehouse {target_wh} not found")

            # 1. Create Goods Receipt Note
            conn.execute(
                "INSERT INTO goods_receipt_notes (grn_id, po_id, warehouse_id) VALUES (?, ?, ?)",
                (grn_id, po_id, target_wh),
            )

            # 2. Process each incoming item: calculate Moving Average Cost & write Stock Ledger
            for item in po.items:
                # Get current product details
                prod_row = conn.execute(
                    "SELECT cost_price FROM products WHERE sku = ?",
                    (item.sku,),
                ).fetchone()
                current_cost = Decimal(str(prod_row["cost_price"]))

                # Get total existing physical stock across all warehouses
                total_stock_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(balance_after), 0) AS total_stock
                    FROM (
                        SELECT balance_after FROM stock_ledger
                        WHERE sku = ?
                        GROUP BY warehouse_id
                        HAVING rowid = MAX(rowid)
                    )
                    """,
                    (item.sku,),
                ).fetchone()
                total_existing_stock = Decimal(str(total_stock_row["total_stock"])) if total_stock_row else Decimal("0.0")

                # Calculate Moving Average Cost:
                # New Cost = (Total Existing Stock * Current Cost + Incoming Qty * Incoming Cost) / (Total Existing Stock + Incoming Qty)
                if total_existing_stock > Decimal("0.0"):
                    new_cost = (
                        (total_existing_stock * current_cost) + (item.qty * item.unit_cost)
                    ) / (total_existing_stock + item.qty)
                else:
                    new_cost = item.unit_cost

                rounded_new_cost = new_cost.quantize(Decimal("0.0001"))

                # Update product cost price
                conn.execute(
                    "UPDATE products SET cost_price = ? WHERE sku = ?",
                    (float(rounded_new_cost), item.sku),
                )

                # Get warehouse-specific balance for stock ledger
                wh_stock_row = conn.execute(
                    """
                    SELECT balance_after FROM stock_ledger
                    WHERE warehouse_id = ? AND sku = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (target_wh, item.sku),
                ).fetchone()
                current_wh_balance = Decimal(str(wh_stock_row["balance_after"])) if wh_stock_row else Decimal("0.0")
                new_wh_balance = current_wh_balance + item.qty

                ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
                conn.execute(
                    """
                    INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ledger_id,
                        target_wh,
                        item.sku,
                        float(item.qty),
                        float(new_wh_balance),
                        float(item.unit_cost),
                        ReferenceType.PURCHASE.value,
                        grn_id,
                        f"GRN receipt for PO {po_id}",
                    ),
                )

                # Update / initialize warehouse_stock_levels
                custom_safety = safety_stocks.get(item.sku) if safety_stocks else None
                if custom_safety is not None:
                    conn.execute(
                        """
                        INSERT INTO warehouse_stock_levels (warehouse_id, sku, safety_stock, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(warehouse_id, sku) DO UPDATE SET
                            safety_stock = excluded.safety_stock,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (target_wh, item.sku, int(custom_safety)),
                    )
                else:
                    level_row = conn.execute(
                        "SELECT 1 FROM warehouse_stock_levels WHERE warehouse_id = ? AND sku = ?",
                        (target_wh, item.sku),
                    ).fetchone()
                    if not level_row:
                        p_row = conn.execute("SELECT safety_stock FROM products WHERE sku = ?", (item.sku,)).fetchone()
                        def_safety = int(p_row["safety_stock"]) if (p_row and p_row["safety_stock"] is not None) else 10
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO warehouse_stock_levels (warehouse_id, sku, safety_stock)
                            VALUES (?, ?, ?)
                            """,
                            (target_wh, item.sku, def_safety),
                        )

            # 3. Update PO status to RECEIVED
            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE po_id = ?",
                (POStatus.RECEIVED.value, po_id),
            )

        # 4. Emit domain event for accounting integration
        event = DomainEvent(
            event_name="ERP_GOODS_RECEIVED",
            payload={
                "grn_id": grn_id,
                "po_id": po_id,
                "warehouse_id": target_wh,
                "total_amount": float(po.total_amount),
            },
        )
        self.event_bus.publish(event)

        return GoodsReceiptNote(grn_id=grn_id, po_id=po_id, warehouse_id=target_wh)

    def revert_goods_receipt(self, po_id: str) -> PurchaseOrder:
        """Revert a received purchase order back to SUBMITTED via red-ink stock reversal."""
        po = self.get_purchase_order(po_id)
        if po.status != POStatus.RECEIVED:
            raise ValueError(f"無法撤回入庫：採購單 {po_id} 目前狀態為 '{po.status.value}'，僅已入庫 (RECEIVED) 狀態可撤回 (Cannot revert non-received PO)")

        with self.db.transaction() as conn:
            # 1. Fetch GRN record
            grn_row = conn.execute(
                "SELECT grn_id, warehouse_id FROM goods_receipt_notes WHERE po_id = ? ORDER BY received_at DESC, rowid DESC LIMIT 1",
                (po_id,),
            ).fetchone()
            if not grn_row:
                raise ValueError(f"無法撤回入庫：查無採購單 {po_id} 之驗收單 (GRN)")

            grn_id = grn_row["grn_id"]
            target_wh = grn_row["warehouse_id"]

            # 2. Check if Accounts Payable has any payments
            ap_row = conn.execute(
                "SELECT ap_id, paid_amount FROM accounts_payable WHERE po_id = ? AND paid_amount > 0",
                (po_id,),
            ).fetchone()
            if ap_row:
                raise ValueError(f"無法撤回入庫：採購單 {po_id} 關聯之應付帳款已有付款紀錄 ({ap_row['paid_amount']})，請先沖銷付款")

            # 3. Check physical stock availability in target warehouse to prevent negative inventory
            for item in po.items:
                wh_stock_row = conn.execute(
                    """
                    SELECT balance_after FROM stock_ledger
                    WHERE warehouse_id = ? AND sku = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (target_wh, item.sku),
                ).fetchone()
                current_wh_balance = Decimal(str(wh_stock_row["balance_after"])) if wh_stock_row else Decimal("0.0")
                if current_wh_balance < item.qty:
                    raise ValueError(
                        f"無法撤回入庫：倉庫 {target_wh} 之商品 {item.sku} 現有庫存 ({current_wh_balance}) 小於入庫量 ({item.qty})，已有部分庫存出庫或調撥"
                    )

            # 4. Insert red-ink reversal stock ledger entries and restore moving average cost
            for item in po.items:
                # Warehouse balance
                wh_stock_row = conn.execute(
                    """
                    SELECT balance_after FROM stock_ledger
                    WHERE warehouse_id = ? AND sku = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT 1
                    """,
                    (target_wh, item.sku),
                ).fetchone()
                current_wh_balance = Decimal(str(wh_stock_row["balance_after"])) if wh_stock_row else Decimal("0.0")
                new_wh_balance = current_wh_balance - item.qty

                ledger_id = f"LEDGER-{uuid.uuid4().hex[:12].upper()}"
                conn.execute(
                    """
                    INSERT INTO stock_ledger (ledger_id, warehouse_id, sku, qty_delta, balance_after, unit_cost, reference_type, reference_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ledger_id,
                        target_wh,
                        item.sku,
                        float(-item.qty),
                        float(new_wh_balance),
                        float(item.unit_cost),
                        ReferenceType.PURCHASE.value,
                        grn_id,
                        f"Reversal of GRN receipt {grn_id} for PO {po_id}",
                    ),
                )

                # Total stock across all warehouses before this reversal deduction
                total_stock_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(balance_after), 0) AS total_stock
                    FROM (
                        SELECT balance_after FROM stock_ledger
                        WHERE sku = ?
                        GROUP BY warehouse_id
                        HAVING rowid = MAX(rowid)
                    )
                    """,
                    (item.sku,),
                ).fetchone()
                remaining_stock = Decimal(str(total_stock_row["total_stock"])) if total_stock_row else Decimal("0.0")

                prod_row = conn.execute("SELECT cost_price FROM products WHERE sku = ?", (item.sku,)).fetchone()
                current_cost = Decimal(str(prod_row["cost_price"])) if prod_row else Decimal("0.0")

                # Restore moving average cost
                if remaining_stock > Decimal("0.0"):
                    pre_stock = remaining_stock + item.qty
                    remaining_value = (pre_stock * current_cost) - (item.qty * item.unit_cost)
                    if remaining_value > Decimal("0.0"):
                        restored_cost = (remaining_value / remaining_stock).quantize(Decimal("0.0001"))
                        conn.execute("UPDATE products SET cost_price = ? WHERE sku = ?", (float(restored_cost), item.sku))

            # 5. Clean accounts_payable linked to this grn/po to satisfy foreign key constraint
            conn.execute("DELETE FROM accounts_payable WHERE grn_id = ? OR (po_id = ? AND paid_amount = 0)", (grn_id, po_id))

            # 6. Delete goods_receipt_notes record
            conn.execute("DELETE FROM goods_receipt_notes WHERE grn_id = ?", (grn_id,))

            # 7. Revert PO status to SUBMITTED
            conn.execute(
                "UPDATE purchase_orders SET status = ? WHERE po_id = ?",
                (POStatus.SUBMITTED.value, po_id),
            )

        # 8. Emit domain event for accounting integration
        event = DomainEvent(
            event_name="ERP_GOODS_RECEIPT_REVERTED",
            payload={
                "grn_id": grn_id,
                "po_id": po_id,
                "warehouse_id": target_wh,
                "total_amount": float(po.total_amount),
            },
        )
        self.event_bus.publish(event)

        return self.get_purchase_order(po_id)

