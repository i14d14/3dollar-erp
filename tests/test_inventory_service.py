from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.core.domain.inventory import InsufficientStockError, LockStatus, ReferenceType
from src.core.services.inventory_service import InventoryService
from src.shared.database import Database


class TestInventoryService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_inventory.db"
        self.db = Database(self.db_path)
        self.db.init_db()
        self.service = InventoryService(db=self.db)

        # Seed initial warehouses and products
        self.wh_main = self.service.create_warehouse("WH-MAIN", "台北總倉")
        self.wh_store = self.service.create_warehouse("WH-STORE", "信義門市倉")
        self.product = self.service.create_product(
            sku="SKU-COFFEE-01",
            name="精品濾掛咖啡",
            base_unit="BOX",
            cost_price=Decimal("150.0"),
            selling_price=Decimal("300.0"),
            safety_stock=20,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_stock_adjustment_and_balance(self):
        # 1. Initial stock in WH-MAIN
        entry = self.service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty_delta=Decimal("100"),
            unit_cost=Decimal("150.0"),
            reference_id="INIT-001",
            notes="Initial stock take",
        )
        self.assertEqual(entry.balance_after, Decimal("100"))
        self.assertEqual(self.service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("100"))
        self.assertEqual(self.service.get_available_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("100"))

    def test_prevent_negative_stock(self):
        # Initial stock: 10
        self.service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty_delta=Decimal("10"),
            unit_cost=Decimal("150.0"),
            reference_id="INIT-002",
        )
        # Attempt to adjust by -15 -> Should raise InsufficientStockError
        with self.assertRaises(InsufficientStockError):
            self.service.adjust_stock(
                warehouse_id="WH-MAIN",
                sku="SKU-COFFEE-01",
                qty_delta=Decimal("-15"),
                unit_cost=Decimal("150.0"),
                reference_id="ADJ-FAIL",
            )
        # Balance must remain 10
        self.assertEqual(self.service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("10"))

    def test_warehouse_transfer_conservation_of_stock(self):
        # Setup: 100 in WH-MAIN, 0 in WH-STORE
        self.service.adjust_stock("WH-MAIN", "SKU-COFFEE-01", Decimal("100"), Decimal("150.0"), "INIT-003")

        # Transfer 35 units from WH-MAIN to WH-STORE
        out_entry, in_entry = self.service.transfer_stock(
            from_warehouse_id="WH-MAIN",
            to_warehouse_id="WH-STORE",
            sku="SKU-COFFEE-01",
            qty=Decimal("35"),
            reference_id="TRF-001",
        )

        self.assertEqual(out_entry.qty_delta, Decimal("-35"))
        self.assertEqual(out_entry.balance_after, Decimal("65"))
        self.assertEqual(in_entry.qty_delta, Decimal("35"))
        self.assertEqual(in_entry.balance_after, Decimal("35"))

        # Invariant: Conservation of stock (65 + 35 = 100)
        bal_main = self.service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01")
        bal_store = self.service.get_stock_balance("WH-STORE", "SKU-COFFEE-01")
        self.assertEqual(bal_main, Decimal("65"))
        self.assertEqual(bal_store, Decimal("35"))
        self.assertEqual(bal_main + bal_store, Decimal("100"))

    def test_transfer_insufficient_stock_fails(self):
        self.service.adjust_stock("WH-MAIN", "SKU-COFFEE-01", Decimal("20"), Decimal("150.0"), "INIT-004")

        # Attempt to transfer 25 units when only 20 exist
        with self.assertRaises(InsufficientStockError):
            self.service.transfer_stock(
                from_warehouse_id="WH-MAIN",
                to_warehouse_id="WH-STORE",
                sku="SKU-COFFEE-01",
                qty=Decimal("25"),
                reference_id="TRF-FAIL",
            )

    def test_virtual_stock_lock_and_release(self):
        self.service.adjust_stock("WH-MAIN", "SKU-COFFEE-01", Decimal("50"), Decimal("150.0"), "INIT-005")

        # Lock 20 units for order SO-101
        lock = self.service.acquire_stock_lock(
            order_id="SO-101",
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty=Decimal("20"),
        )
        self.assertEqual(lock.status, LockStatus.LOCKED)

        # Physical balance remains 50, but available drops to 30
        self.assertEqual(self.service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("50"))
        self.assertEqual(self.service.get_locked_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("20"))
        self.assertEqual(self.service.get_available_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("30"))

        # Cannot transfer 35 units because only 30 are available! (Anti-overselling)
        with self.assertRaises(InsufficientStockError):
            self.service.transfer_stock(
                from_warehouse_id="WH-MAIN",
                to_warehouse_id="WH-STORE",
                sku="SKU-COFFEE-01",
                qty=Decimal("35"),
                reference_id="TRF-LOCKED",
            )

        # Release lock (e.g. order cancelled)
        released_count = self.service.release_stock_lock(order_id="SO-101")
        self.assertEqual(released_count, 1)
        self.assertEqual(self.service.get_available_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("50"))

    def test_fulfill_stock_lock(self):
        self.service.adjust_stock("WH-MAIN", "SKU-COFFEE-01", Decimal("50"), Decimal("150.0"), "INIT-006")
        self.service.acquire_stock_lock("SO-102", "WH-MAIN", "SKU-COFFEE-01", Decimal("15"))

        # Fulfill lock (Shipment)
        entry = self.service.fulfill_stock_lock(
            order_id="SO-102",
            warehouse_id="WH-MAIN",
            sku="SKU-COFFEE-01",
            qty=Decimal("15"),
            unit_cost=Decimal("150.0"),
            reference_id="DO-102",
        )
        self.assertEqual(entry.qty_delta, Decimal("-15"))
        self.assertEqual(entry.balance_after, Decimal("35"))
        self.assertEqual(entry.reference_type, ReferenceType.SALE)

        # Locked stock is now 0, physical balance is 35, available is 35
        self.assertEqual(self.service.get_locked_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("0"))
        self.assertEqual(self.service.get_stock_balance("WH-MAIN", "SKU-COFFEE-01"), Decimal("35"))
        self.assertEqual(self.service.get_available_stock("WH-MAIN", "SKU-COFFEE-01"), Decimal("35"))


if __name__ == "__main__":
    unittest.main()
