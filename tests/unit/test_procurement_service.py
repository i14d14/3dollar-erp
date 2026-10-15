from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.core.domain.procurement import POStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.procurement_service import ProcurementService
from src.shared.base_models import DomainEvent
from src.shared.database import Database
from src.shared.event_bus import InMemoryEventBus


class TestProcurementService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_procurement.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = InMemoryEventBus()
        self.inv_service = InventoryService(db=self.db)
        self.service = ProcurementService(db=self.db, event_bus=self.event_bus)

        # Seed warehouse and product
        self.wh = self.inv_service.create_warehouse("WH-MAIN", "台北總倉")
        self.product = self.inv_service.create_product(
            sku="SKU-BEAN-01",
            name="耶加雪菲生豆",
            base_unit="KG",
            cost_price=Decimal("0.0"),
            selling_price=Decimal("500.0"),
            safety_stock=10,
        )

        self.captured_events = []
        self.event_bus.subscribe("ERP_GOODS_RECEIVED", lambda e: self.captured_events.append(e))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_po_lifecycle_and_moving_average_cost(self):
        # 1. Batch 1: Buy 100 kg @ $100/kg
        po1 = self.service.create_purchase_order(
            supplier_name="衣索比亞進口商",
            items=[("SKU-BEAN-01", Decimal("100"), Decimal("100.0"))],
        )
        self.assertEqual(po1.status, POStatus.DRAFT)
        self.assertEqual(po1.total_amount, Decimal("10000.0"))

        # Cannot receive in DRAFT
        with self.assertRaises(ValueError):
            self.service.receive_goods(po1.po_id, "WH-MAIN")

        # Submit PO
        po1 = self.service.submit_purchase_order(po1.po_id)
        self.assertEqual(po1.status, POStatus.SUBMITTED)

        # Receive Goods (GRN 1)
        grn1 = self.service.receive_goods(po1.po_id, "WH-MAIN")
        self.assertIsNotNone(grn1.grn_id)

        # Verify stock and cost after Batch 1: stock = 100, cost = 100.0
        self.assertEqual(self.inv_service.get_stock_balance("WH-MAIN", "SKU-BEAN-01"), Decimal("100"))
        prod1 = self.inv_service.get_product("SKU-BEAN-01")
        self.assertEqual(prod1.cost_price, Decimal("100.0000"))

        # 2. Batch 2: Buy 50 kg @ $130/kg
        # Expected new cost: (100 * 100 + 50 * 130) / (100 + 50) = (10000 + 6500) / 150 = 110.0
        po2 = self.service.create_purchase_order(
            supplier_name="衣索比亞進口商",
            items=[("SKU-BEAN-01", Decimal("50"), Decimal("130.0"))],
        )
        self.service.submit_purchase_order(po2.po_id)
        self.service.receive_goods(po2.po_id, "WH-MAIN")

        # Verify stock and cost after Batch 2: stock = 150, cost = 110.0
        self.assertEqual(self.inv_service.get_stock_balance("WH-MAIN", "SKU-BEAN-01"), Decimal("150"))
        prod2 = self.inv_service.get_product("SKU-BEAN-01")
        self.assertEqual(prod2.cost_price, Decimal("110.0000"))

        # 3. Verify event published
        self.assertEqual(len(self.captured_events), 2)
        self.assertEqual(self.captured_events[1].payload["po_id"], po2.po_id)
        self.assertEqual(self.captured_events[1].payload["total_amount"], 6500.0)


if __name__ == "__main__":
    unittest.main()
