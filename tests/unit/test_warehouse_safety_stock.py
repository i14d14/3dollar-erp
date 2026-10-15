from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.services.inventory_service import InventoryService
from src.core.services.procurement_service import ProcurementService
from src.core.services.scheduler_service import SchedulerService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestWarehouseSafetyStock(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_safety_stock.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inv_service = InventoryService(db=self.db)
        self.proc_service = ProcurementService(db=self.db, event_bus=self.event_bus)
        self.scheduler = SchedulerService(db=self.db, inventory_service=self.inv_service)

        self.app = create_app(db=self.db)
        self.client = TestClient(self.app)

        # Get or create warehouses
        self.wh_main = self.inv_service.get_warehouse("WH-MAIN") or self.inv_service.create_warehouse("WH-MAIN", "台北總倉")
        self.wh_store = self.inv_service.get_warehouse("WH-STORE") or self.inv_service.create_warehouse("WH-STORE", "信義門市倉")

        # Seed products
        self.prod_a = self.inv_service.get_product("SKU-COFFEE") or self.inv_service.create_product(
            sku="SKU-COFFEE",
            name="濾掛咖啡",
            safety_stock=20,
        )
        self.prod_b = self.inv_service.get_product("SKU-TEA") or self.inv_service.create_product(
            sku="SKU-TEA",
            name="高山茶葉",
            safety_stock=5,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_warehouse_safety_stock_isolation(self):
        """Verify safety stock settings on different warehouses are completely isolated."""
        # By default, falls back to product default
        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE"), 20)
        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-STORE", "SKU-COFFEE"), 20)

        # Update WH-MAIN to 50 and WH-STORE to 5
        self.inv_service.upsert_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE", 50)
        self.inv_service.upsert_warehouse_safety_stock("WH-STORE", "SKU-COFFEE", 5)

        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE"), 50)
        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-STORE", "SKU-COFFEE"), 5)

    def test_transfer_with_destination_safety_stock_provisioning(self):
        """Verify transferring stock can initialize or update destination warehouse safety stock."""
        # Initial stock in WH-MAIN
        self.inv_service.adjust_stock("WH-MAIN", "SKU-COFFEE", Decimal("100"), Decimal("50"), "INIT-01")

        # Transfer 15 units to WH-STORE, specifying to_safety_stock=8
        self.inv_service.transfer_stock(
            from_warehouse_id="WH-MAIN",
            to_warehouse_id="WH-STORE",
            sku="SKU-COFFEE",
            qty=Decimal("15"),
            reference_id="TRF-001",
            to_safety_stock=8,
        )

        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-STORE", "SKU-COFFEE"), 8)
        self.assertEqual(self.inv_service.get_stock_balance("WH-STORE", "SKU-COFFEE"), Decimal("15"))

    def test_procurement_receive_with_custom_safety_stock(self):
        """Verify PO receipt records custom warehouse safety stock for first-time inbound items."""
        po = self.proc_service.create_purchase_order(
            supplier_name="精選豆農",
            items=[("SKU-COFFEE", Decimal("30"), Decimal("40"))],
            warehouse_id="WH-STORE",
        )
        self.proc_service.submit_purchase_order(po.po_id)

        # Receive PO into WH-STORE with custom safety stock of 12
        self.proc_service.receive_goods(
            po_id=po.po_id,
            warehouse_id="WH-STORE",
            safety_stocks={"SKU-COFFEE": 12},
        )

        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-STORE", "SKU-COFFEE"), 12)
        self.assertEqual(self.inv_service.get_stock_balance("WH-STORE", "SKU-COFFEE"), Decimal("30"))

    def test_web_safety_stock_inline_edit_and_status_update(self):
        """Test inline editing workflow via HTMX endpoints on /inventory."""
        # Setup: WH-MAIN has 10 units, safety stock is 20 -> is_low_stock is True
        self.inv_service.adjust_stock("WH-MAIN", "SKU-COFFEE", Decimal("10"), Decimal("50"), "INIT-02")
        self.inv_service.upsert_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE", 20)

        # 1. GET /inventory/safety-stock/edit returns form
        edit_resp = self.client.get("/inventory/safety-stock/edit?warehouse_id=WH-MAIN&sku=SKU-COFFEE")
        self.assertEqual(edit_resp.status_code, 200)
        self.assertIn('input-edit-safety-WH-MAIN-SKU-COFFEE', edit_resp.text)
        self.assertIn('value="20"', edit_resp.text)

        # 2. GET /inventory/safety-stock/cancel returns display cell
        cancel_resp = self.client.get("/inventory/safety-stock/cancel?warehouse_id=WH-MAIN&sku=SKU-COFFEE")
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertIn('20', cancel_resp.text)

        # 3. POST /inventory/safety-stock lowers safety stock to 8 -> is_low_stock becomes False!
        post_resp = self.client.post(
            "/inventory/safety-stock",
            data={"warehouse_id": "WH-MAIN", "sku": "SKU-COFFEE", "safety_stock": 8},
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertIn('存量充裕', post_resp.text)
        self.assertIn('已成功將【台北總倉】之商品【SKU-COFFEE】安全存量更新為 8', post_resp.text)
        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE"), 8)

    def test_web_transfer_with_safety_stock_form(self):
        """Test POST /inventory/transfer with to_safety_stock form parameter."""
        self.inv_service.adjust_stock("WH-MAIN", "SKU-TEA", Decimal("50"), Decimal("200"), "INIT-TEA")

        resp = self.client.post(
            "/inventory/transfer",
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-TEA",
                "qty": 10,
                "to_safety_stock": 15,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.inv_service.get_warehouse_safety_stock("WH-STORE", "SKU-TEA"), 15)
        self.assertEqual(self.inv_service.get_stock_balance("WH-STORE", "SKU-TEA"), Decimal("10"))

    def test_scheduler_no_false_alarm_on_untracked_warehouse(self):
        """Verify scheduler only scans tracked warehouse stock levels and does not false-alarm."""
        # 1. Create a brand new branch warehouse that does not maintain SKU-COFFEE
        self.inv_service.create_warehouse("WH-BRAND-NEW", "新成立門市倉")
        new_wh_alerts = self.scheduler.scan_low_safety_stock("WH-BRAND-NEW")
        self.assertEqual(len(new_wh_alerts), 0)

        # 2. WH-MAIN: adjust SKU-COFFEE to 8 (safety stock 10 -> shortage 2)
        self.inv_service.adjust_stock("WH-MAIN", "SKU-COFFEE", Decimal("8"), Decimal("50"), "INIT-03")
        self.inv_service.upsert_warehouse_safety_stock("WH-MAIN", "SKU-COFFEE", 10)

        # WH-STORE does not track SKU-COFFEE
        store_alerts = self.scheduler.scan_low_safety_stock("WH-STORE")
        coffee_alerts_in_store = [a for a in store_alerts if a.sku == "SKU-COFFEE"]
        self.assertEqual(len(coffee_alerts_in_store), 0)

        # Scan WH-MAIN -> includes SKU-COFFEE alert with shortage 2
        main_alerts = self.scheduler.scan_low_safety_stock("WH-MAIN")
        coffee_main = next(a for a in main_alerts if a.sku == "SKU-COFFEE")
        self.assertEqual(coffee_main.sku, "SKU-COFFEE")
        self.assertEqual(coffee_main.shortage, Decimal("2"))
