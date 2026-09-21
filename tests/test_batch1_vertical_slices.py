from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import fitz
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.channel_ui.web.view_service import WebViewService
from src.core.domain.order import OrderChannel
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestBatch1VerticalSlices(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_batch1_slices.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(
            db=self.db,
            event_bus=self.event_bus,
            inventory_service=self.inventory_service,
        )

        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_product(
            sku="SKU-ITEM-1",
            name="測試商品一",
            base_unit="PCS",
            cost_price=Decimal("100.0"),
            selling_price=Decimal("200.0"),
            safety_stock=5,
        )
        self.inventory_service.create_product(
            sku="SKU-ITEM-2",
            name="測試商品二",
            base_unit="PCS",
            cost_price=Decimal("50.0"),
            selling_price=Decimal("100.0"),
            safety_stock=5,
        )

        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-ITEM-1",
            qty_delta=Decimal("50.0"),
            unit_cost=Decimal("100.0"),
            reference_id="INIT-1",
            notes="期初庫存",
        )
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-ITEM-2",
            qty_delta=Decimal("50.0"),
            unit_cost=Decimal("50.0"),
            reference_id="INIT-2",
            notes="期初庫存",
        )

        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_deliveries_modal_empty_and_multiple_batches(self):
        # 1. Create order
        order = self.order_service.create_order(
            customer_id="CUST-MODAL-TEST",
            items=[
                ("SKU-ITEM-1", Decimal("5.0"), Decimal("200.0")),
                ("SKU-ITEM-2", Decimal("3.0"), Decimal("100.0")),
            ],
            channel=OrderChannel.DIRECT,
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")

        # 2. Before shipment: deliveries modal should show empty message
        resp_empty = self.client.get(f"/orders/{order.order_id}/deliveries-modal")
        self.assertEqual(resp_empty.status_code, 200)
        self.assertIn("出貨單紀錄與歷程", resp_empty.text)
        self.assertIn("此訂單尚未有任何出貨單據記錄", resp_empty.text)

        # 3. First partial shipment: 2 units of SKU-ITEM-1
        do1, _ = self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="測試客",
            recipient_phone="0911-111-111",
            shipping_address="台北市",
            items_to_ship=[(order.items[0].item_id, Decimal("2.0"))],
        )

        # 4. Second partial shipment: 3 units of SKU-ITEM-1, 3 units of SKU-ITEM-2
        do2, _ = self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="測試客",
            recipient_phone="0911-111-111",
            shipping_address="台北市",
            items_to_ship=[
                (order.items[0].item_id, Decimal("3.0")),
                (order.items[1].item_id, Decimal("3.0")),
            ],
        )

        # 5. Check deliveries modal now lists both DOs
        resp_filled = self.client.get(f"/orders/{order.order_id}/deliveries-modal")
        self.assertEqual(resp_filled.status_code, 200)
        self.assertIn(do1.do_id, resp_filled.text)
        self.assertIn(do2.do_id, resp_filled.text)
        self.assertIn("累計出貨批次：<span class=\"font-bold text-indigo-600\">2</span> 批", resp_filled.text)
        self.assertIn("SKU-ITEM-1", resp_filled.text)
        self.assertIn("SKU-ITEM-2", resp_filled.text)
        self.assertIn("📄 A4 貼紙 (選格位)", resp_filled.text)

        # 6. Check View DTO reflection
        view_service = WebViewService(db=self.db)
        row_dto = view_service.get_order_row(order.order_id)
        self.assertIsNotNone(row_dto)
        self.assertEqual(row_dto.delivery_orders_count, 2)
        self.assertEqual(row_dto.delivery_order_ids, [do1.do_id, do2.do_id])

    def test_a4_label_modal_and_starting_positions(self):
        # Create order and ship
        order = self.order_service.create_order(
            customer_id="CUST-A4-TEST",
            items=[("SKU-ITEM-1", Decimal("2.0"), Decimal("200.0"))],
            channel=OrderChannel.DIRECT,
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")
        do, _ = self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="張三",
            recipient_phone="0922-222-222",
            shipping_address="新北市新店區北新路",
        )

        # 1. Open A4 label modal
        resp_modal = self.client.get(f"/orders/{order.order_id}/a4-label-modal")
        self.assertEqual(resp_modal.status_code, 200)
        self.assertIn("A4 標籤紙起印設定 (2x2 多格貼紙)", resp_modal.text)
        self.assertIn("第 1 格", resp_modal.text)
        self.assertIn("第 2 格", resp_modal.text)
        self.assertIn("第 3 格", resp_modal.text)
        self.assertIn("第 4 格", resp_modal.text)

        # 2. Download A4 label with valid starting position = 3
        resp_pdf = self.client.get(f"/orders/{order.order_id}/label_a4.pdf?start_pos=3")
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf.headers["content-type"], "application/pdf")
        doc = fitz.open(stream=resp_pdf.content, filetype="pdf")
        self.assertEqual(len(doc), 1)
        rect = doc[0].rect
        self.assertEqual(round(rect.width, 1), 595.3)
        self.assertEqual(round(rect.height, 1), 841.9)
        text = doc[0].get_text()
        self.assertIn(do.do_id, text)
        self.assertIn("收件客戶", text)
        doc.close()

        # 3. Invalid starting position validation
        resp_invalid = self.client.get(f"/orders/{order.order_id}/label_a4.pdf?start_pos=5")
        self.assertEqual(resp_invalid.status_code, 400)
        self.assertIn("起印格位 (start_pos) 必須在 1 到 4 之間", resp_invalid.text)

        # 4. Specific DO label print
        resp_do_pdf = self.client.get(f"/orders/{order.order_id}/label.pdf?do_id={do.do_id}")
        self.assertEqual(resp_do_pdf.status_code, 200)
        self.assertEqual(resp_do_pdf.headers["content-type"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
