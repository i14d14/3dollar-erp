from __future__ import annotations
from decimal import Decimal
import pytest
from src.core.adapters.internal_carrier_adapter import InternalShippingCarrierProvider
from src.core.domain.order import OrderChannel
from src.core.ports.event_bus_port import EventBusPort
from src.core.ports.shipping_carrier_port import WaybillRequest
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database


class DummyEventBus(EventBusPort):
    def __init__(self) -> None:
        self.published = []

    def publish(self, event) -> None:
        self.published.append(event)

    def subscribe(self, event_type, handler) -> None:
        pass


def test_internal_carrier_provider_dispatch():
    provider = InternalShippingCarrierProvider(carrier_name="三圓測試物流")
    req = WaybillRequest(
        order_id="SO-TEST001",
        recipient_name="王大明",
        recipient_phone="0912345678",
        shipping_address="台北市信義區信義路五段7號",
    )
    res = provider.dispatch_waybill(req)

    assert res.waybill_id.startswith("WB-")
    assert res.tracking_number.startswith("TRK-")
    assert res.carrier_name == "三圓測試物流"
    assert res.barcode_payload == res.tracking_number
    assert "SO-TEST001" in res.qrcode_payload
    assert "王大明" in res.qrcode_payload


def test_order_service_uses_carrier_port(tmp_path):
    db_path = tmp_path / "test_carrier.db"
    db = Database(db_path)
    db.init_db()

    with db.transaction() as conn:
        conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('WH-01', '測試倉')")
        conn.execute(
            "INSERT INTO products (sku, name, cost_price, selling_price, safety_stock) VALUES ('SKU-01', '測試品', 100, 200, 5)"
        )

    inv_service = InventoryService(db=db)
    inv_service.adjust_stock("WH-01", "SKU-01", Decimal("50"), Decimal("100"), "INIT")

    bus = DummyEventBus()
    carrier = InternalShippingCarrierProvider()
    order_service = OrderService(db=db, event_bus=bus, inventory_service=inv_service, carrier_port=carrier)

    so = order_service.create_order(
        customer_id="CUST-01",
        items=[("SKU-01", Decimal("5"), Decimal("200"))],
        channel=OrderChannel.DIRECT,
    )
    order_service.confirm_order(so.order_id, warehouse_id="WH-01")

    # Ship order without explicit tracking number
    do, _ = order_service.ship_order(
        order_id=so.order_id,
        warehouse_id="WH-01",
        recipient_name="李四",
        recipient_phone="0988123456",
        shipping_address="新北市板橋區縣民大道二段7號",
    )

    assert do.tracking_number.startswith("TRK-")
