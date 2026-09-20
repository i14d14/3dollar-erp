from __future__ import annotations
from decimal import Decimal
import pytest
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.ports.event_bus_port import EventBusPort
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.shared.base_models import DomainEvent
from src.shared.database import Database


class CapturingEventBus(EventBusPort):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)

    def subscribe(self, event_name: str, handler) -> None:
        pass


@pytest.fixture
def env(tmp_path):
    db_file = tmp_path / "test_partial_shipment.db"
    db = Database(db_file)
    db.init_db()

    with db.transaction() as conn:
        conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('WH-MAIN', '主倉庫')")
        conn.execute("INSERT INTO products (sku, name, cost_price, selling_price, safety_stock) VALUES ('SKU-A', '商品A', 50, 100, 5)")
        conn.execute("INSERT INTO products (sku, name, cost_price, selling_price, safety_stock) VALUES ('SKU-B', '商品B', 100, 200, 5)")

    event_bus = CapturingEventBus()
    inv_service = InventoryService(db=db)
    inv_service.adjust_stock("WH-MAIN", "SKU-A", Decimal("50"), Decimal("50"), "INIT", "Initial stock A")
    inv_service.adjust_stock("WH-MAIN", "SKU-B", Decimal("50"), Decimal("100"), "INIT", "Initial stock B")

    order_service = OrderService(db=db, event_bus=event_bus, inventory_service=inv_service)
    invoice_service = InvoiceService(db=db, event_bus=event_bus)

    return {
        "db": db,
        "event_bus": event_bus,
        "inv_service": inv_service,
        "order_service": order_service,
        "invoice_service": invoice_service,
    }


def test_1_to_n_split_fulfillment_flow(env):
    order_service: OrderService = env["order_service"]
    inv_service: InventoryService = env["inv_service"]
    invoice_service: InvoiceService = env["invoice_service"]

    # 1. Create order: SKU-A x 10, SKU-B x 5
    order = order_service.create_order(
        customer_id="CUST-ALPHA",
        items=[
            ("SKU-A", Decimal("10.0"), Decimal("100.0")),
            ("SKU-B", Decimal("5.0"), Decimal("200.0")),
        ],
        channel=OrderChannel.DIRECT,
    )
    assert order.status == OrderStatus.DRAFT

    # 2. Confirm order -> locks 10 of A, 5 of B
    order = order_service.confirm_order(order.order_id, "WH-MAIN")
    assert order.status == OrderStatus.CONFIRMED
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-A") == Decimal("10.0")
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-B") == Decimal("5.0")
    assert inv_service.get_available_stock("WH-MAIN", "SKU-A") == Decimal("40.0")

    # 3. Partial shipment 1: Ship 6 of SKU-A only
    do1, label_pdf1 = order_service.ship_order(
        order_id=order.order_id,
        warehouse_id="WH-MAIN",
        recipient_name="張三",
        recipient_phone="0911-111-222",
        shipping_address="台北市忠孝東路一段",
        items_to_ship=[("SKU-A", Decimal("6.0"))],
    )
    assert do1.do_id.startswith("DO-")
    assert len(do1.allocations) == 1
    assert do1.allocations[0].sku == "SKU-A"
    assert do1.allocations[0].allocated_qty == Decimal("6.0")

    # Verify inventory & locks after batch 1
    # Physical balance reduced by 6 (50 - 6 = 44)
    assert inv_service.get_stock_balance("WH-MAIN", "SKU-A") == Decimal("44.0")
    # Remaining locked qty is 4 (10 - 6 = 4)
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-A") == Decimal("4.0")
    assert inv_service.get_available_stock("WH-MAIN", "SKU-A") == Decimal("40.0")

    # Verify order state is PARTIALLY_SHIPPED
    order_after_p1 = order_service.get_order(order.order_id)
    assert order_after_p1.status == OrderStatus.PARTIALLY_SHIPPED
    items_by_sku = {item.sku: item for item in order_after_p1.items}
    assert items_by_sku["SKU-A"].shipped_qty == Decimal("6.0")
    assert items_by_sku["SKU-A"].remaining_qty == Decimal("4.0")
    assert items_by_sku["SKU-B"].shipped_qty == Decimal("0.0")
    assert items_by_sku["SKU-B"].remaining_qty == Decimal("5.0")

    # 4. Overshipment rejection check: attempt to ship 5 of SKU-A (remaining is only 4)
    with pytest.raises(ValueError, match="超過剩餘未出量"):
        order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="張三",
            recipient_phone="0911-111-222",
            shipping_address="台北市忠孝東路一段",
            items_to_ship=[("SKU-A", Decimal("5.0"))],
        )

    # 5. Partial shipment 2: Ship remaining 4 of SKU-A and all 5 of SKU-B
    do2, label_pdf2 = order_service.ship_order(
        order_id=order.order_id,
        warehouse_id="WH-MAIN",
        recipient_name="張三",
        recipient_phone="0911-111-222",
        shipping_address="台北市忠孝東路一段",
        items_to_ship=[
            ("SKU-A", Decimal("4.0")),
            ("SKU-B", Decimal("5.0")),
        ],
    )
    assert do2.do_id.startswith("DO-")
    assert len(do2.allocations) == 2

    # Verify order is now fully SHIPPED
    order_after_p2 = order_service.get_order(order.order_id)
    assert order_after_p2.status == OrderStatus.SHIPPED
    assert order_after_p2.is_fully_shipped is True
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-A") == Decimal("0.0")
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-B") == Decimal("0.0")

    # 6. Check get_order_deliveries returns both shipments
    deliveries = order_service.get_order_deliveries(order.order_id)
    assert len(deliveries) == 2
    assert deliveries[0].do_id == do1.do_id
    assert deliveries[1].do_id == do2.do_id
    assert len(deliveries[0].allocations) == 1
    assert len(deliveries[1].allocations) == 2

    # 7. Issue invoice -> transitions fully shipped order to COMPLETED
    invoice, ar, inv_pdf = invoice_service.issue_invoice_for_order(order.order_id)
    order_final = order_service.get_order(order.order_id)
    assert order_final.status == OrderStatus.COMPLETED


def test_backward_compatible_full_shipment(env):
    order_service: OrderService = env["order_service"]

    # Calling ship_order without items_to_ship performs 100% full shipment in 1 DO
    order = order_service.create_order(
        customer_id="CUST-BETA",
        items=[("SKU-A", Decimal("3.0"), Decimal("100.0"))],
    )
    order_service.confirm_order(order.order_id, "WH-MAIN")

    do, pdf = order_service.ship_order(
        order_id=order.order_id,
        warehouse_id="WH-MAIN",
        recipient_name="李四",
        recipient_phone="0922-222-333",
        shipping_address="台中市台灣大道一段",
    )
    assert do.do_id.startswith("DO-")
    assert len(do.allocations) == 1
    assert do.allocations[0].allocated_qty == Decimal("3.0")

    order_shipped = order_service.get_order(order.order_id)
    assert order_shipped.status == OrderStatus.SHIPPED
    assert order_shipped.is_fully_shipped is True
