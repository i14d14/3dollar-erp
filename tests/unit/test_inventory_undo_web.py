from __future__ import annotations
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.inventory import ReferenceType
from src.core.services.inventory_service import InventoryService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestInventoryUndoWeb(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_inventory_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inventory_service = InventoryService(db=self.db)

        # Seed initial warehouses and product
        self.wh_main = self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.wh_store = self.inventory_service.create_warehouse("WH-STORE", "信義門市倉")
        self.product = self.inventory_service.create_product(
            sku="SKU-COFFEE-01",
            name="精品濾掛咖啡",
            base_unit="BOX",
            cost_price=Decimal("150.0"),
            selling_price=Decimal("300.0"),
            safety_stock=20,
        )

        # 50 units in WH-MAIN
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

    def test_transfer_returns_stock_table_ledger_and_undo_toast(self) -> None:
        resp = self.client.post(
            "/inventory/transfer",
            headers={"HX-Request": "true"},
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-COFFEE-01",
                "qty": 15,
            },
        )
        self.assertEqual(resp.status_code, 200)

        # 1. Primary target swap: stock table
        self.assertIn('id="stock-table-container"', resp.text)
        self.assertIn("35", resp.text)
        self.assertIn("15", resp.text)

        # 2. OOB target swap: ledger table
        self.assertIn('id="ledger-table-container"', resp.text)
        self.assertIn('hx-swap-oob="outerHTML:#ledger-table-container"', resp.text)
        self.assertIn("TRANSFER", resp.text)

        # 3. OOB target swap: toast container with 6s TTL & undo button
        self.assertIn('id="toast-container"', resp.text)
        self.assertIn('hx-swap-oob="innerHTML:#toast-container"', resp.text)
        self.assertIn('data-ttl="6000"', resp.text)
        self.assertIn('style="--toast-ttl: 6s;"', resp.text)
        self.assertIn('hx-post="/inventory/transfer/undo"', resp.text)
        self.assertIn('hx-target="#stock-table-container"', resp.text)
        self.assertIn("撤回調撥", resp.text)
        self.assertIn("調撥成功！已由 台北總倉 調撥 15 件 SKU-COFFEE-01 至 信義門市倉", resp.text)

        # Verify DB balances
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("35"))
        self.assertEqual(self.inventory_service.get_stock_balance("WH-STORE", "SKU-COFFEE-01"), Decimal("15"))

    def test_undo_transfer_restores_balances_and_adds_reversal_entry(self) -> None:
        # Perform initial transfer
        resp1 = self.client.post(
            "/inventory/transfer",
            headers={"HX-Request": "true"},
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-COFFEE-01",
                "qty": 20,
            },
        )
        self.assertEqual(resp1.status_code, 200)

        # Extract ref_id from hx-vals
        m = re.search(r'hx-vals=[\'"]\{"ref_id":\s*"([^"]+)"\}[\'"]', resp1.text)
        self.assertIsNotNone(m, "Failed to extract ref_id from transfer response")
        ref_id = m.group(1)

        # Execute undo
        resp_undo = self.client.post(
            "/inventory/transfer/undo",
            headers={"HX-Request": "true"},
            data={"ref_id": ref_id},
        )
        self.assertEqual(resp_undo.status_code, 200)

        # 1. Balances restored to initial (50 in WH-MAIN, 0 in WH-STORE)
        self.assertIn('id="stock-table-container"', resp_undo.text)
        self.assertEqual(self.inventory_service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("50"))
        self.assertEqual(self.inventory_service.get_stock_balance("WH-STORE", "SKU-COFFEE-01"), Decimal("0"))

        # 2. Ledger updated with reversal entries
        self.assertIn('id="ledger-table-container"', resp_undo.text)
        self.assertIn("調撥撤回", resp_undo.text)
        self.assertIn(f"REV-{ref_id}", resp_undo.text)

        # 3. Toast displays successful undo message
        self.assertIn('id="toast-container"', resp_undo.text)
        self.assertIn(f"已成功撤回調撥 ({ref_id})，庫存已原路歸還。", resp_undo.text)
        self.assertNotIn("hx-post=", resp_undo.text)  # No further undo on an undo

    def test_undo_transfer_twice_fails_with_traditional_chinese_error(self) -> None:
        # Perform transfer
        resp1 = self.client.post(
            "/inventory/transfer",
            headers={"HX-Request": "true"},
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-COFFEE-01",
                "qty": 10,
            },
        )
        m = re.search(r'hx-vals=[\'"]\{"ref_id":\s*"([^"]+)"\}[\'"]', resp1.text)
        ref_id = m.group(1)

        # First undo succeeds
        resp_undo1 = self.client.post(
            "/inventory/transfer/undo",
            headers={"HX-Request": "true"},
            data={"ref_id": ref_id},
        )
        self.assertEqual(resp_undo1.status_code, 200)

        # Second undo fails
        resp_undo2 = self.client.post(
            "/inventory/transfer/undo",
            headers={"HX-Request": "true"},
            data={"ref_id": ref_id},
        )
        self.assertEqual(resp_undo2.status_code, 400)
        self.assertEqual(resp_undo2.headers.get("HX-Reswap"), "none")
        self.assertIn('id="toast-container"', resp_undo2.text)
        self.assertIn("已經撤回過，無法重複撤回", resp_undo2.text)

    def test_undo_transfer_insufficient_stock_fails(self) -> None:
        # Transfer 20 units
        resp1 = self.client.post(
            "/inventory/transfer",
            headers={"HX-Request": "true"},
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-COFFEE-01",
                "qty": 20,
            },
        )
        m = re.search(r'hx-vals=[\'"]\{"ref_id":\s*"([^"]+)"\}[\'"]', resp1.text)
        ref_id = m.group(1)

        # Lock 10 units in WH-STORE (available drops to 10 < 20)
        self.inventory_service.acquire_stock_lock("SO-LOCK-99", "WH-STORE", "SKU-COFFEE-01", Decimal("10"))

        # Attempt undo
        resp_undo = self.client.post(
            "/inventory/transfer/undo",
            headers={"HX-Request": "true"},
            data={"ref_id": ref_id},
        )
        self.assertEqual(resp_undo.status_code, 400)
        self.assertEqual(resp_undo.headers.get("HX-Reswap"), "none")
        self.assertIn('id="toast-container"', resp_undo.text)
        self.assertIn("可用存量不足", resp_undo.text)


if __name__ == "__main__":
    unittest.main()
