from decimal import Decimal
import fitz
import pytest
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService, InsufficientStockError
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


@pytest.fixture
def batch2_fixture(tmp_path):
    """Setup clean database and services for batch 2 split shipping tests."""
    db_file = tmp_path / "test_batch2.db"
    db = Database(db_file)
    event_bus = EventBus()
    app = create_app(db=db, event_bus=event_bus)
    client = TestClient(app, raise_server_exceptions=False)

    inv_service = InventoryService(db=db)
    order_service = OrderService(db=db, inventory_service=inv_service, event_bus=event_bus)

    yield client, db, inv_service, order_service

    if db_file.exists():
        try:
            db_file.unlink()
        except Exception:
            pass


def test_cross_warehouse_split_shipping_and_lock_fulfillment(batch2_fixture):
    """Bug 4: Split-shipping from a different warehouse deducts physical stock from target warehouse

    and fulfills/reduces the original warehouse lock.
    """
    client, db, inv_service, order_service = batch2_fixture

    # 1. Prepare isolated product & inventory:
    inv_service.create_product(
        sku="SKU-SPLIT-TEST",
        name="拆批測試物料",
        base_unit="PCS",
        cost_price=Decimal("1500.00"),
        selling_price=Decimal("2500.00"),
    )
    # WH-MAIN: 10 units of SKU-SPLIT-TEST
    # WH-STORE: 20 units of SKU-SPLIT-TEST
    inv_service.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-SPLIT-TEST",
        qty_delta=Decimal("10.0"),
        unit_cost=Decimal("1500.00"),
        reference_id="PO-INIT-MAIN",
    )
    inv_service.adjust_stock(
        warehouse_id="WH-STORE",
        sku="SKU-SPLIT-TEST",
        qty_delta=Decimal("20.0"),
        unit_cost=Decimal("1500.00"),
        reference_id="PO-INIT-STORE",
    )

    # 2. Create order assigned to WH-MAIN with 10 units
    order = order_service.create_order(
        customer_id="CUST-001",
        channel=OrderChannel.DIRECT,
        items=[("SKU-SPLIT-TEST", Decimal("10.0"), Decimal("2500.00"))],
        warehouse_id="WH-MAIN",
    )
    # Confirm order -> acquires 10 units lock in WH-MAIN
    order = order_service.confirm_order(order.order_id)
    assert order.status == OrderStatus.CONFIRMED

    # Check initial stock & locks
    assert inv_service.get_stock_balance("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("10.0")
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("10.0")
    assert inv_service.get_available_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("0.0")

    assert inv_service.get_stock_balance("WH-STORE", "SKU-SPLIT-TEST") == Decimal("20.0")
    assert inv_service.get_locked_stock("WH-STORE", "SKU-SPLIT-TEST") == Decimal("0.0")
    assert inv_service.get_available_stock("WH-STORE", "SKU-SPLIT-TEST") == Decimal("20.0")

    # 3. Batch 1: Split-ship 4 units from WH-STORE
    item_id = order.items[0].item_id
    do_1, _ = order_service.ship_order(
        order_id=order.order_id,
        warehouse_id="WH-STORE",
        items_to_ship=[(item_id, Decimal("4.0"))],
    )
    assert do_1.warehouse_id == "WH-STORE"

    # Verify order state: PARTIALLY_SHIPPED, remaining_qty = 6
    order_after_b1 = order_service.get_order(order.order_id)
    assert order_after_b1.status == OrderStatus.PARTIALLY_SHIPPED
    assert order_after_b1.items[0].remaining_qty == Decimal("6.0")

    # Verify inventory state after Batch 1:
    # WH-STORE: physical stock deducted by 4 (20 -> 16)
    assert inv_service.get_stock_balance("WH-STORE", "SKU-SPLIT-TEST") == Decimal("16.0")
    assert inv_service.get_available_stock("WH-STORE", "SKU-SPLIT-TEST") == Decimal("16.0")

    # WH-MAIN: physical stock remains 10, but lock was reduced by 4 (10 -> 6), so available = 4!
    assert inv_service.get_stock_balance("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("10.0")
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("6.0")
    assert inv_service.get_available_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("4.0")

    # 4. Verify negative balance protection when shipping warehouse lacks stock
    with pytest.raises(InsufficientStockError):
        # WH-STORE only has 16 units, attempting to ship 100 units throws error
        inv_service.fulfill_stock_lock(
            order_id=order.order_id,
            warehouse_id="WH-STORE",
            sku="SKU-SPLIT-TEST",
            qty=Decimal("100.0"),
            unit_cost=Decimal("1500.00"),
            reference_id="DO-OVERFLOW",
        )

    # 5. Batch 2: Ship remaining 6 units from WH-MAIN
    do_2, _ = order_service.ship_order(
        order_id=order.order_id,
        warehouse_id="WH-MAIN",
        items_to_ship=[(item_id, Decimal("6.0"))],
    )
    assert do_2.warehouse_id == "WH-MAIN"

    # Verify order is fully shipped (SHIPPED)
    order_after_b2 = order_service.get_order(order.order_id)
    assert order_after_b2.status == OrderStatus.SHIPPED
    assert order_after_b2.items[0].remaining_qty == Decimal("0.0")

    # WH-MAIN: physical stock was 10, now 10 - 6 = 4. Lock is FULFILLED (0).
    assert inv_service.get_stock_balance("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("4.0")
    assert inv_service.get_locked_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("0.0")
    assert inv_service.get_available_stock("WH-MAIN", "SKU-SPLIT-TEST") == Decimal("4.0")


def test_split_shipping_multi_page_label_pdf(batch2_fixture):
    """Bug 5: Normal 100x150 shipping label prints 2 pages when order has 2 split delivery orders."""
    client, db, inv_service, order_service = batch2_fixture

    # Setup inventory and order
    inv_service.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("20.0"), Decimal("1500.00"), "PO-MAIN")
    inv_service.adjust_stock("WH-STORE", "SKU-PRO-01", Decimal("20.0"), Decimal("1500.00"), "PO-STORE")

    order = order_service.create_order(
        customer_id="CUST-002",
        channel=OrderChannel.DIRECT,
        items=[("SKU-PRO-01", Decimal("8.0"), Decimal("2500.00"))],
        warehouse_id="WH-MAIN",
    )
    order_service.confirm_order(order.order_id)
    item_id = order.items[0].item_id

    # Split into 2 delivery orders: 3 from WH-STORE, 5 from WH-MAIN
    do_1, _ = order_service.ship_order(order.order_id, warehouse_id="WH-STORE", items_to_ship=[(item_id, Decimal("3.0"))])
    do_2, _ = order_service.ship_order(order.order_id, warehouse_id="WH-MAIN", items_to_ship=[(item_id, Decimal("5.0"))])

    # 1. Test GET /orders/{order_id}/label.pdf (without do_id) -> MUST return multi-page PDF with 2 pages!
    resp = client.get(f"/orders/{order.order_id}/label.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

    pdf_doc = fitz.open(stream=resp.content, filetype="pdf")
    assert pdf_doc.page_count == 2, f"Expected 2 pages for 2 DOs, got {pdf_doc.page_count}"

    # Verify page dimensions: 100x150mm (283.46 x 425.20 pt)
    p1 = pdf_doc.load_page(0)
    assert round(p1.rect.width, 1) == 283.5
    assert round(p1.rect.height, 1) == 425.2
    p1_text = p1.get_text()
    assert do_1.do_id in p1_text
    assert order.order_id in p1_text

    p2 = pdf_doc.load_page(1)
    p2_text = p2.get_text()
    assert do_2.do_id in p2_text
    assert order.order_id in p2_text
    pdf_doc.close()

    # 2. Test GET with specific do_id -> MUST return single page
    resp_single = client.get(f"/orders/{order.order_id}/label.pdf?do_id={do_1.do_id}")
    assert resp_single.status_code == 200
    pdf_single = fitz.open(stream=resp_single.content, filetype="pdf")
    assert pdf_single.page_count == 1
    assert do_1.do_id in pdf_single.load_page(0).get_text()
    pdf_single.close()


def test_partial_ship_ui_modal_and_endpoint(batch2_fixture):
    """Bug 4 UI Slice: Verify modal contains warehouse selector and form submission handles warehouse selection."""
    client, db, inv_service, order_service = batch2_fixture

    inv_service.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("10.0"), Decimal("1500.00"), "PO-MAIN")
    inv_service.adjust_stock("WH-STORE", "SKU-PRO-01", Decimal("10.0"), Decimal("1500.00"), "PO-STORE")

    order = order_service.create_order(
        customer_id="CUST-003",
        channel=OrderChannel.DIRECT,
        items=[("SKU-PRO-01", Decimal("6.0"), Decimal("2500.00"))],
        warehouse_id="WH-MAIN",
    )
    order_service.confirm_order(order.order_id)
    item_id = order.items[0].item_id

    # 1. Fetch modal HTML
    modal_resp = client.get(f"/orders/{order.order_id}/partial-ship-modal")
    assert modal_resp.status_code == 200
    modal_html = modal_resp.text
    assert 'name="warehouse_id"' in modal_html
    assert 'value="WH-MAIN"' in modal_html
    assert 'value="WH-STORE"' in modal_html
    assert "本次出貨來源倉庫" in modal_html

    # 2. Post partial ship from WH-STORE
    ship_resp = client.post(
        f"/orders/{order.order_id}/ship-partial",
        data={
            "warehouse_id": "WH-STORE",
            f"qty_{item_id}": "2",
        },
        headers={"HX-Request": "true"},
    )
    assert ship_resp.status_code == 200
    ship_html = ship_resp.text
    assert "拆批出貨成功" in ship_html
    assert "出貨倉：WH-STORE" in ship_html

    # Check delivery records in DB
    deliveries = order_service.get_order_deliveries(order.order_id)
    assert len(deliveries) == 1
    assert deliveries[0].warehouse_id == "WH-STORE"
