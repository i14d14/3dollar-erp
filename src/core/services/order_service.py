from __future__ import annotations
import sqlite3
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter
from src.core.domain.order import DeliveryOrder, OrderChannel, OrderItem, OrderStatus, SalesOrder
from src.core.ports.event_bus_port import EventBusPort
from src.core.ports.printer_port import PrinterPort, ShippingLabelData
from src.core.services.inventory_service import InventoryService
from src.shared.base_models import DomainEvent
from src.shared.database import Database, default_db
from src.shared.event_bus import default_event_bus


class OrderService:
    def __init__(
        self,
        db: Database = default_db,
        inventory_service: Optional[InventoryService] = None,
        printer: Optional[PrinterPort] = None,
        event_bus: EventBusPort = default_event_bus,
    ) -> None:
        self.db = db
        self.inventory_service = inventory_service or InventoryService(db=db)
        self.printer = printer or PdfPrinterAdapter()
        self.event_bus = event_bus

    def create_order(
        self,
        customer_id: str,
        items: List[Tuple[str, Decimal, Decimal]],  # (sku, qty, unit_price)
        channel: OrderChannel = OrderChannel.DIRECT,
    ) -> SalesOrder:
        """Create a sales order in DRAFT status."""
        if not items:
            raise ValueError("Sales order must contain at least one item")

        order_id = f"SO-{uuid.uuid4().hex[:10].upper()}"
        total_amount = Decimal("0.0")
        order_items: List[OrderItem] = []

        with self.db.transaction() as conn:
            # 1. Validate items and calculate total amount
            item_data = []
            for sku, qty, unit_price in items:
                if qty <= Decimal("0.0") or unit_price < Decimal("0.0"):
                    raise ValueError(f"Invalid quantity ({qty}) or unit price ({unit_price}) for SKU {sku}")
                prod = conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
                if not prod:
                    raise ValueError(f"Product SKU {sku} does not exist")
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
                raise ValueError(f"Sales order {order_id} not found")

            item_rows = conn.execute(
                "SELECT item_id, order_id, sku, qty, unit_price, subtotal FROM sales_order_items WHERE order_id = ?",
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
            raise ValueError(f"Cannot confirm order {order_id}: status is '{order.status.value}', expected 'DRAFT'")

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
            raise ValueError(f"Cannot cancel order {order_id}: already {order.status.value}")

        if order.status == OrderStatus.CONFIRMED:
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
    ) -> Tuple[DeliveryOrder, bytes]:
        """One-click fulfillment: fulfill stock locks, deduct physical stock, create DO, and render PDF label."""
        order = self.get_order(order_id)
        if order.status != OrderStatus.CONFIRMED:
            raise ValueError(f"Cannot ship order {order_id}: status is '{order.status.value}', expected 'CONFIRMED'")

        do_id = f"DO-{uuid.uuid4().hex[:10].upper()}"
        tracking = tracking_number or f"TRK-{uuid.uuid4().hex[:10].upper()}"

        # 1. Fulfill stock locks and deduct stock ledger
        for item in order.items:
            prod = self.inventory_service.get_product(item.sku)
            unit_cost = prod.cost_price if prod else Decimal("0.0")
            self.inventory_service.fulfill_stock_lock(
                order_id=order_id,
                warehouse_id=warehouse_id,
                sku=item.sku,
                qty=item.qty,
                unit_cost=unit_cost,
                reference_id=do_id,
            )

        # 2. Record Delivery Order and update Order status
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO delivery_orders (do_id, order_id, warehouse_id, tracking_number)
                VALUES (?, ?, ?, ?)
                """,
                (do_id, order_id, warehouse_id, tracking),
            )
            conn.execute(
                "UPDATE sales_orders SET status = ? WHERE order_id = ?",
                (OrderStatus.SHIPPED.value, order_id),
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
            },
        )
        self.event_bus.publish(event)

        delivery_order = DeliveryOrder(
            do_id=do_id,
            order_id=order_id,
            warehouse_id=warehouse_id,
            tracking_number=tracking,
        )
        return delivery_order, label_pdf
