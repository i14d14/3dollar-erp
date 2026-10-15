from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestCrossLayerEventE2E(unittest.TestCase):
    """End-to-End integration test verifying that Web UI actions trigger cross-layer

    domain events that seamlessly propagate to TanGii accounting without split-brain issues.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cross_layer_e2e.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.app = create_app(db=self.db, event_bus=self.event_bus)
        self.client = TestClient(self.app)

        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(
            db=self.db,
            event_bus=self.event_bus,
            inventory_service=self.inventory_service,
        )

        # Setup Warehouse and Products
        if not self.inventory_service.get_warehouse("WH-MAIN"):
            self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_product(
            sku="SKU-E2E-01",
            name="E2E 旗艦測試機",
            base_unit="PCS",
            cost_price=Decimal("2000.0"),
            selling_price=Decimal("3500.0"),
            safety_stock=10,
        )
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-E2E-01",
            qty_delta=Decimal("20.0"),
            unit_cost=Decimal("2000.0"),
            reference_id="INIT-E2E",
            notes="期初庫存",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_web_shipping_and_invoicing_creates_accounting_vouchers(self) -> None:
        # 1. Create and confirm an order (2 units @ $3,500 = $7,000 total; cost: 2 @ $2,000 = $4,000)
        order = self.order_service.create_order(
            customer_id="CUST-E2E-TEST",
            items=[("SKU-E2E-01", Decimal("2.0"), Decimal("3500.0"))],
        )
        self.order_service.confirm_order(order_id=order.order_id, warehouse_id="WH-MAIN")

        # Verify initial journal entries count before web shipping
        with self.db.transaction() as conn:
            initial_entries = conn.execute(
                "SELECT COUNT(*) FROM journal_entries WHERE reference_id LIKE ?",
                (f"%{order.order_id}%",),
            ).fetchone()[0]
        self.assertEqual(initial_entries, 0)

        # 2. Trigger Shipping via Web Route POST /orders/{order_id}/ship
        ship_resp = self.client.post(
            f"/orders/{order.order_id}/ship",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(ship_resp.status_code, 200)

        # Verify Accounting Journal Entry for ERP_ORDER_SHIPPED was automatically generated
        from src.extended_core.accounting.services.accounting_service import AccountingService
        acct_service = AccountingService(db=self.db)
        entries = acct_service.get_journal_entries()

        ship_entry = next(
            (e for e in entries if e.source_event == "ERP_ORDER_SHIPPED" and order.order_id in e.description),
            None,
        )
        self.assertIsNotNone(ship_entry, "Shipment journal entry must be created automatically by event listener")
        ship_debit = sum(l.debit for l in ship_entry.lines)
        ship_credit = sum(l.credit for l in ship_entry.lines)
        self.assertEqual(ship_debit, ship_credit)
        self.assertEqual(ship_debit, Decimal("4000.0"))

        # Verify lines: Dr. 5111 (銷貨成本), Cr. 1201 (存貨)
        cogs_line = next(l for l in ship_entry.lines if l.account_code == "5111")
        inv_line = next(l for l in ship_entry.lines if l.account_code == "1201")
        self.assertEqual(cogs_line.debit, Decimal("4000.0"))
        self.assertEqual(inv_line.credit, Decimal("4000.0"))

        # 3. Trigger Invoicing via Web Route POST /orders/{order_id}/invoice
        inv_resp = self.client.post(
            f"/orders/{order.order_id}/invoice",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(inv_resp.status_code, 200)

        # Verify Accounting Journal Entry for ERP_INVOICE_ISSUED was automatically generated
        entries = acct_service.get_journal_entries()
        inv_entry = next(
            (e for e in entries if e.source_event == "ERP_INVOICE_ISSUED" and order.order_id in e.description),
            None,
        )
        self.assertIsNotNone(inv_entry, "Invoice journal entry must be created automatically by event listener")
        inv_debit = sum(l.debit for l in inv_entry.lines)
        inv_credit = sum(l.credit for l in inv_entry.lines)
        self.assertEqual(inv_debit, inv_credit)
        self.assertEqual(inv_debit, Decimal("7000.0"))

        # Verify invoice lines: Dr. 1144 (應收帳款) $7,000, Cr. 4111 (銷貨收入) $6,667, Cr. 2201 (銷項稅額) $333
        ar_line = next(l for l in inv_entry.lines if l.account_code == "1144")
        rev_line = next(l for l in inv_entry.lines if l.account_code == "4111")
        tax_line = next(l for l in inv_entry.lines if l.account_code == "2201")
        self.assertEqual(ar_line.debit, Decimal("7000.0"))
        self.assertEqual(rev_line.credit, Decimal("6667.0"))
        self.assertEqual(tax_line.credit, Decimal("333.0"))


if __name__ == "__main__":
    unittest.main()
