from __future__ import annotations
import sqlite3
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter
from src.core.domain.order import (
    DeliveryAllocation,
    DeliveryOrder,
    OrderChannel,
    OrderItem,
    OrderStatus,
    SalesOrder,
)
from src.core.ports.event_bus_port import EventBusPort
from src.core.ports.printer_port import PrinterPort, ShippingLabelData
from src.core.services.inventory_service import InventoryService
from src.shared.base_models import DomainEvent
from src.shared.database import Database, default_db


class OrderService:
    def __init__(
        self,
        db: Database,
        event_bus: EventBusPort,
        inventory_service: Optional[InventoryService] = None,
        printer: Optional[PrinterPort] = None,
    ) -> None:
        self.db = db
        self.event_bus = event_bus
        self.inventory_service = inventory_service or InventoryService(db=db)
        self.printer = printer or PdfPrinterAdapter()

    def create_order(
        self,
        customer_id: str,
        items: List[Tuple[str, Decimal, Decimal]],  # (sku, qty, unit_price)
        channel: OrderChannel = OrderChannel.DIRECT,
    ) -> SalesOrder:
        """Create a sales order in DRAFT status."""
        if not items:
            raise ValueError("銷售訂單必須包含至少一項商品明細 (Sales order must contain at least one item)")

        order_id = f"SO-{uuid.uuid4().hex[:10].upper()}"
        total_amount = Decimal("0.0")
        order_items: List[OrderItem] = []

        with self.db.transaction() as conn:
            # 1. Validate items and calculate total amount
            item_data = []
            for sku, qty, unit_price in items:
                if qty <= Decimal("0.0") or unit_price < Decimal("0.0"):
                    raise ValueError(f"品號 {sku} 購買數量 ({qty}) 或銷售單價 ({unit_price}) 無效 (Invalid quantity or unit price)")
                prod = conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
                if not prod:
                    raise ValueError(f"商品品號 {sku} 不存在 (Product SKU does not exist)")
                subtotal = qty * unit_price
                total_amount += subtotal
                item_data.append((sku, qty, unit_price, subtotal))

            # 2. Insert parent sales_orders first
            conn.execute(
                """
                INSERT INTO sales_orders (order_id, customer_id, channel, status, total_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, customer_id, channel.value, OrderStatus.DRAFT.value, float(total_amount)),
            )

            # 3. Insert child sales_order_items
            for sku, qty, unit_price, subtotal in item_data:
                item_id = f"SOI-{uuid.uuid4().hex[:10].upper()}"
                conn.execute(
                    """
                    INSERT INTO sales_order_items (item_id, order_id, sku, qty, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, order_id, sku, float(qty), float(unit_price), float(subtotal)),
                )
                order_items.append(
                    OrderItem(
                        item_id=item_id,
                        order_id=order_id,
                        sku=sku,
                        qty=qty,
                        unit_price=unit_price,
                        subtotal=subtotal,
                    )
                )

        return SalesOrder(
            order_id=order_id,
            customer_id=customer_id,
            channel=channel,
            status=OrderStatus.DRAFT,
            total_amount=total_amount,
            items=order_items,
        )

    def get_order(self, order_id: str) -> SalesOrder:
        """Retrieve a sales order with its items."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT order_id, customer_id, channel, status, total_amount FROM sales_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"查無銷售訂單 {order_id} (Sales order not found)")

            item_rows = conn.execute(
                """
                SELECT item_id, order_id, sku, qty, unit_price, subtotal,
                       COALESCE(shipped_quantity, 0) AS shipped_quantity
                FROM sales_order_items WHERE order_id = ?
                """,
                (order_id,),
            ).fetchall()

            items = [
                OrderItem(
                    item_id=r["item_id"],
                    order_id=r["order_id"],
                    sku=r["sku"],
                    qty=Decimal(str(r["qty"])),
                    unit_price=Decimal(str(r["unit_price"])),
                    subtotal=Decimal(str(r["subtotal"])),
                    shipped_qty=Decimal(str(r["shipped_quantity"])),
                )
                for r in item_rows
            ]

            return SalesOrder(
                order_id=row["order_id"],
                customer_id=row["customer_id"],
                channel=OrderChannel(row["channel"]),
                status=OrderStatus(row["status"]),
                total_amount=Decimal(str(row["total_amount"])),
                items=items,
            )

    def confirm_order(self, order_id: str, warehouse_id: str) -> SalesOrder:
        """Confirm order and acquire virtual stock locks for all items in the designated warehouse."""
        order = self.get_order(order_id)
        if order.status != OrderStatus.DRAFT:
            raise ValueError(f"無法確認訂單 {order_id}：目前狀態為 '{order.status.value}'，僅草稿 (DRAFT) 狀態可執行鎖庫確認 (Cannot confirm order)")

        # Lock inventory for each item
        for item in order.items:
            self.inventory_service.acquire_stock_lock(
                order_id=order_id,
                warehouse_id=warehouse_id,
                sku=item.sku,
                qty=item.qty,
            )

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE sales_orders SET status = ? WHERE order_id = ?",
                (OrderStatus.CONFIRMED.value, order_id),
            )

        return self.get_order(order_id)

    def cancel_order(self, order_id: str) -> SalesOrder:
        """Cancel an order and release any reserved virtual stock locks."""
        order = self.get_order(order_id)
        if order.status in (OrderStatus.SHIPPED, OrderStatus.COMPLETED):
            raise ValueError(f"無法取消訂單 {order_id}：單據目前為 '{order.status.value}' 狀態，不可取消 (Cannot cancel order)")

        if order.status in (OrderStatus.CONFIRMED, OrderStatus.PARTIALLY_SHIPPED):
            self.inventory_service.release_stock_lock(order_id)

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE sales_orders SET status = ? WHERE order_id = ?",
                (OrderStatus.CANCELLED.value, order_id),
            )

        return self.get_order(order_id)

    def ship_order(
        self,
        order_id: str,
        warehouse_id: str,
        recipient_name: str,
        recipient_phone: str,
        shipping_address: str,
        tracking_number: Optional[str] = None,
        items_to_ship: Optional[List[Tuple[str, Decimal]]] = None,
    ) -> Tuple[DeliveryOrder, bytes]:
        """One-click fulfillment / Partial fulfillment: fulfill stock locks, deduct physical stock, record allocations, and create DO."""
        order = self.get_order(order_id)
        if order.status not in (OrderStatus.CONFIRMED, OrderStatus.PARTIALLY_SHIPPED):
            raise ValueError(
                f"無法出貨訂單 {order_id}：目前狀態為 '{order.status.value}'，僅已確認 (CONFIRMED) 或部分出貨 (PARTIALLY_SHIPPED) 狀態可執行出貨扣庫 (Cannot ship order)"
            )

        items_map = {item.sku: item for item in order.items}
        items_by_id = {item.item_id: item for item in order.items}

        allocations_to_make: List[Tuple[OrderItem, Decimal]] = []
        if items_to_ship is None:
            # Full shipment of all remaining unshipped quantities
            for item in order.items:
                rem = item.remaining_qty
                if rem > Decimal("0.0"):
                    allocations_to_make.append((item, rem))
        else:
            if not items_to_ship:
                raise ValueError("拆批出貨清單不得為空 (Items to ship list cannot be empty)")
            for key, req_qty in items_to_ship:
                alloc_q = Decimal(str(req_qty))
                if alloc_q <= Decimal("0.0"):
                    continue
                item = items_map.get(key) or items_by_id.get(key)
                if not item:
                    raise ValueError(f"訂單中查無商品品號或明細 ID '{key}' (Item not found in order)")
                if alloc_q > item.remaining_qty:
                    raise ValueError(
                        f"品號 {item.sku} 指定出貨數量 ({alloc_q}) 超過剩餘未出量 ({item.remaining_qty}) (Quantity exceeds remaining unshipped)"
                    )
                allocations_to_make.append((item, alloc_q))

        if not allocations_to_make:
            raise ValueError(f"訂單 {order_id} 查無可出貨品項或剩餘出貨數量為 0 (No remaining items to ship)")

        do_id = f"DO-{uuid.uuid4().hex[:10].upper()}"
        tracking = tracking_number or f"TRK-{uuid.uuid4().hex[:10].upper()}"

        # 1. Fulfill stock locks and deduct stock ledger
        for item, alloc_qty in allocations_to_make:
            prod = self.inventory_service.get_product(item.sku)
            unit_cost = prod.cost_price if prod else Decimal("0.0")
            self.inventory_service.fulfill_stock_lock(
                order_id=order_id,
                warehouse_id=warehouse_id,
                sku=item.sku,
                qty=alloc_qty,
                unit_cost=unit_cost,
                reference_id=do_id,
            )

        # 2. Record Delivery Order and Allocations in DB transaction
        created_allocations: List[DeliveryAllocation] = []
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO delivery_orders (do_id, order_id, warehouse_id, tracking_number)
                VALUES (?, ?, ?, ?)
                """,
                (do_id, order_id, warehouse_id, tracking),
            )

            for item, alloc_qty in allocations_to_make:
                alloc_id = f"ALLOC-{uuid.uuid4().hex[:10].upper()}"
                conn.execute(
                    """
                    INSERT INTO delivery_allocations (allocation_id, do_id, order_id, item_id, sku, allocated_qty)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (alloc_id, do_id, order_id, item.item_id, item.sku, float(alloc_qty)),
                )
                conn.execute(
                    """
                    UPDATE sales_order_items
                    SET shipped_quantity = shipped_quantity + ?
                    WHERE item_id = ?
                    """,
                    (float(alloc_qty), item.item_id),
                )
                created_allocations.append(
                    DeliveryAllocation(
                        allocation_id=alloc_id,
                        do_id=do_id,
                        order_id=order_id,
                        item_id=item.item_id,
                        sku=item.sku,
                        allocated_qty=alloc_qty,
                    )
                )

            # Check if order is fully shipped
            rem_check = conn.execute(
                """
                SELECT SUM(qty - shipped_quantity) as remaining
                FROM sales_order_items
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
            remaining_total = (
                Decimal(str(rem_check["remaining"]))
                if rem_check and rem_check["remaining"] is not None
                else Decimal("0.0")
            )

            if remaining_total <= Decimal("0.0"):
                inv_row = conn.execute("SELECT 1 FROM invoices WHERE order_id = ?", (order_id,)).fetchone()
                target_status = OrderStatus.COMPLETED.value if inv_row else OrderStatus.SHIPPED.value
            else:
                target_status = OrderStatus.PARTIALLY_SHIPPED.value

            conn.execute(
                "UPDATE sales_orders SET status = ? WHERE order_id = ?",
                (target_status, order_id),
            )

        # 3. Generate logistics shipping label PDF via PrinterPort
        label_data = ShippingLabelData(
            do_id=do_id,
            order_id=order_id,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            shipping_address=shipping_address,
            tracking_number=tracking,
        )
        label_pdf = self.printer.generate_shipping_label_pdf(label_data)

        # 4. Emit domain event for downstream accounting and tracking
        event = DomainEvent(
            event_name="ERP_ORDER_SHIPPED",
            payload={
                "order_id": order_id,
                "do_id": do_id,
                "warehouse_id": warehouse_id,
                "total_amount": float(order.total_amount),
                "tracking_number": tracking,
                "status": target_status,
                "allocations": [
                    {"sku": a.sku, "qty": float(a.allocated_qty)}
                    for a in created_allocations
                ],
            },
        )
        self.event_bus.publish(event)

        delivery_order = DeliveryOrder(
            do_id=do_id,
            order_id=order_id,
            warehouse_id=warehouse_id,
            tracking_number=tracking,
            allocations=created_allocations,
        )
        return delivery_order, label_pdf

    def get_order_deliveries(self, order_id: str) -> List[DeliveryOrder]:
        """Query all delivery orders and their allocations for a sales order."""
        with self.db.transaction() as conn:
            do_rows = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number, shipped_at FROM delivery_orders WHERE order_id = ? ORDER BY rowid ASC",
                (order_id,),
            ).fetchall()

            deliveries: List[DeliveryOrder] = []
            for r in do_rows:
                alloc_rows = conn.execute(
                    "SELECT allocation_id, do_id, order_id, item_id, sku, allocated_qty, created_at FROM delivery_allocations WHERE do_id = ?",
                    (r["do_id"],),
                ).fetchall()
                allocs = [
                    DeliveryAllocation(
                        allocation_id=ar["allocation_id"],
                        do_id=ar["do_id"],
                        order_id=ar["order_id"],
                        item_id=ar["item_id"],
                        sku=ar["sku"],
                        allocated_qty=Decimal(str(ar["allocated_qty"])),
                        created_at=str(ar["created_at"]) if ar["created_at"] else None,
                    )
                    for ar in alloc_rows
                ]
                deliveries.append(
                    DeliveryOrder(
                        do_id=r["do_id"],
                        order_id=r["order_id"],
                        warehouse_id=r["warehouse_id"],
                        tracking_number=r["tracking_number"],
                        allocations=allocs,
                    )
                )
            return deliveries
