from __future__ import annotations
import sqlite3
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from src.core.domain.inventory import ReferenceType
from src.core.domain.procurement import GoodsReceiptNote, POStatus, PurchaseOrder, PurchaseOrderItem
from src.core.ports.event_bus_port import EventBusPort
from src.shared.base_models import DomainEvent
from src.shared.database import Database, default_db
from src.shared.event_bus import default_event_bus


class ProcurementService:
    def __init__(self, db: Database = default_db, event_bus: EventBusPort = default_event_bus) -> None:
        self.db = db
        self.event_bus = event_bus

    def create_purchase_order(
        self,
        supplier_name: str,
        items: List[Tuple[str, Decimal, Decimal]],  # (sku, qty, unit_cost)
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
                INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount)
                VALUES (?, ?, ?, ?)
                """,
                (po_id, supplier_name, POStatus.DRAFT.value, float(total_amount)),
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

    def get_purchase_order(self, po_id: str) -> PurchaseOrder:
        """Fetch a purchase order with items."""
        with self.db.transaction() as conn:
            po_row = conn.execute(
                "SELECT po_id, supplier_name, status, total_amount FROM purchase_orders WHERE po_id = ?",
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

            return PurchaseOrder(
                po_id=po_row["po_id"],
                supplier_name=po_row["supplier_name"],
                status=POStatus(po_row["status"]),
                total_amount=Decimal(str(po_row["total_amount"])),
                items=items,
            )

    def receive_goods(self, po_id: str, warehouse_id: str) -> GoodsReceiptNote:
        """Process goods receipt (GRN), calculate moving average cost, and update stock ledger."""
        po = self.get_purchase_order(po_id)
        if po.status != POStatus.SUBMITTED:
            raise ValueError(f"Cannot receive PO {po_id}: status is '{po.status.value}', expected 'SUBMITTED'")

        grn_id = f"GRN-{uuid.uuid4().hex[:10].upper()}"

        with self.db.transaction() as conn:
            # Validate warehouse
            wh = conn.execute("SELECT 1 FROM warehouses WHERE warehouse_id = ?", (warehouse_id,)).fetchone()
            if not wh:
                raise ValueError(f"Warehouse {warehouse_id} not found")

            # 1. Create Goods Receipt Note
            conn.execute(
                "INSERT INTO goods_receipt_notes (grn_id, po_id, warehouse_id) VALUES (?, ?, ?)",
                (grn_id, po_id, warehouse_id),
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
                    (warehouse_id, item.sku),
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
                        warehouse_id,
                        item.sku,
                        float(item.qty),
                        float(new_wh_balance),
                        float(item.unit_cost),
                        ReferenceType.PURCHASE.value,
                        grn_id,
                        f"GRN receipt for PO {po_id}",
                    ),
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
                "warehouse_id": warehouse_id,
                "total_amount": float(po.total_amount),
            },
        )
        self.event_bus.publish(event)

        return GoodsReceiptNote(grn_id=grn_id, po_id=po_id, warehouse_id=warehouse_id)
