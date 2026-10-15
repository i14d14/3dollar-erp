from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestOrderUndoWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_order_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(db=self.db, event_bus=self.event_bus)

        # Seed warehouse, product & initial inventory
        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_product(
            sku="SKU-COFFEE-01",
            name="精品濾掛咖啡",
            base_unit="BOX",
            cost_price=Decimal("150.0"),
            selling_price=Decimal("300.0"),
            safety_stock=20,
        )
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty_delta=Decimal("50.0"),
            unit_cost=Decimal("150.0"),
            reference_id="INIT-TEST",
        )

        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_confirm_order_locks_stock_and_undo_restores_draft_and_releases_lock(self) -> None:
        # Create draft order
        order = self.order_service.create_order(
            customer_id="CUST-001",
            channel=OrderChannel.DIRECT,
            items=[("SKU-COFFEE-01", Decimal("15"), Decimal("300.00"))],
        )
        self.assertEqual(order.status, OrderStatus.DRAFT)

        # Confirm order (lock stock)
        resp = self.client.post(
            f"/orders/{order.order_id}/confirm",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn("鎖庫確認成功", resp.text)
        self.assertIn("撤回鎖庫", resp.text)
        self.assertIn(f"/orders/{order.order_id}/confirm/undo", resp.text)

        # Verify DB is CONFIRMED and stock lock acquired
        self.assertEqual(self.order_service.get_order(order.order_id).status, OrderStatus.CONFIRMED)
        with self.db.transaction() as conn:
            lock_row = conn.execute(
                "SELECT locked_qty FROM stock_locks WHERE order_id = ? AND sku = ? AND status = 'LOCKED'",
                (order.order_id, "SKU-COFFEE-01"),
            ).fetchone()
            self.assertIsNotNone(lock_row)
            self.assertEqual(Decimal(str(lock_row["locked_qty"])), Decimal("15"))

        # Click Undo Confirm
        undo_resp = self.client.post(
            f"/orders/{order.order_id}/confirm/undo",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(undo_resp.status_code, 200)
        self.assertIn("已成功撤回訂單", undo_resp.text)
        self.assertIn("庫存已原路釋放", undo_resp.text)

        # Verify DB is restored to DRAFT and stock lock is released (no active locked row)
        self.assertEqual(self.order_service.get_order(order.order_id).status, OrderStatus.DRAFT)
        with self.db.transaction() as conn:
            lock_row_after = conn.execute(
                "SELECT locked_qty FROM stock_locks WHERE order_id = ? AND sku = ? AND status = 'LOCKED'",
                (order.order_id, "SKU-COFFEE-01"),
            ).fetchone()
            self.assertIsNone(lock_row_after)

    def test_ship_confirm_modal_and_ship_returns_standardized_toast_with_no_undo(self) -> None:
        order = self.order_service.create_order(
            customer_id="CUST-001",
            channel=OrderChannel.DIRECT,
            items=[("SKU-COFFEE-01", Decimal("10"), Decimal("300.00"))],
        )
        self.order_service.confirm_order(order.order_id, warehouse_id="WH-MAIN")

        # Open Ship Modal
        modal_resp = self.client.get(f"/orders/{order.order_id}/ship-modal")
        self.assertEqual(modal_resp.status_code, 200)
        self.assertIn("一鍵出貨確認 (Order Shipment Confirmation)", modal_resp.text)

        # Submit Full Shipment
        ship_resp = self.client.post(
            f"/orders/{order.order_id}/ship",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(ship_resp.status_code, 200)
        self.assertIn('id="toast-container"', ship_resp.text)
        self.assertIn("出貨成功", ship_resp.text)
        self.assertIn("實體庫存已扣減", ship_resp.text)
        # Verify no undo button on physical stock deduction
        self.assertNotIn('<span>撤回</span>', ship_resp.text)

        # Verify DB is SHIPPED
        updated = self.order_service.get_order(order.order_id)
        self.assertEqual(updated.status, OrderStatus.SHIPPED)

    def test_issue_invoice_returns_standardized_toast_with_no_undo(self) -> None:
        order = self.order_service.create_order(
            customer_id="CUST-001",
            channel=OrderChannel.DIRECT,
            items=[("SKU-COFFEE-01", Decimal("5"), Decimal("300.00"))],
        )
        self.order_service.confirm_order(order.order_id, warehouse_id="WH-MAIN")
        self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="收件客戶",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區信義路五段7號",
        )

        inv_resp = self.client.post(
            f"/orders/{order.order_id}/invoice",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(inv_resp.status_code, 200)
        self.assertIn('id="toast-container"', inv_resp.text)
        self.assertIn("電子發票開立成功", inv_resp.text)
        self.assertNotIn('<span>撤回</span>', inv_resp.text)
