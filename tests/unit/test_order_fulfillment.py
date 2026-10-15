from __future__ import annotations
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import fitz

from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter
from src.core.domain.inventory import InsufficientStockError
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import InMemoryEventBus


class TestOrderFulfillment(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_orders.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = InMemoryEventBus()
        self.inv_service = InventoryService(db=self.db)
        self.printer = PdfPrinterAdapter()
        self.order_service = OrderService(
            db=self.db,
            inventory_service=self.inv_service,
            printer=self.printer,
            event_bus=self.event_bus,
        )

        # Seed warehouse, product, and stock
        self.wh = self.inv_service.create_warehouse("WH-MAIN", "台北總倉")
        self.product = self.inv_service.create_product(
            sku="SKU-PHONE-01",
            name="智慧手機 Pro",
            base_unit="UNIT",
            cost_price=Decimal("15000.0"),
            selling_price=Decimal("24000.0"),
            safety_stock=5,
        )
        self.inv_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-PHONE-01",
            qty_delta=Decimal("20"),
            unit_cost=Decimal("15000.0"),
            reference_id="INIT-PHONES",
        )

        self.shipped_events = []
        self.event_bus.subscribe("ERP_ORDER_SHIPPED", lambda e: self.shipped_events.append(e))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_complete_order_fulfillment_lifecycle(self):
        # 1. Create Sales Order
        order = self.order_service.create_order(
            customer_id="CUST-001",
            channel=OrderChannel.DIRECT,
            items=[("SKU-PHONE-01", Decimal("3"), Decimal("24000.0"))],
        )
        self.assertEqual(order.status, OrderStatus.DRAFT)
        self.assertEqual(order.total_amount, Decimal("72000.0"))

        # 2. Confirm Order -> Locks 3 units in WH-MAIN
        order = self.order_service.confirm_order(order.order_id, "WH-MAIN")
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertEqual(self.inv_service.get_stock_balance("WH-MAIN", "SKU-PHONE-01"), Decimal("20"))
        self.assertEqual(self.inv_service.get_locked_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("3"))
        self.assertEqual(self.inv_service.get_available_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("17"))

        # 3. Ship Order -> Fulfills lock, deducts stock, creates DO, generates PDF
        do, pdf_bytes = self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="王小明",
            recipient_phone="0912345678",
            shipping_address="台北市信義區信義路五段7號",
        )
        self.assertIsNotNone(do.do_id)
        self.assertTrue(do.tracking_number.startswith("TRK-"))

        # Verify stock after shipment: balance=17, locked=0, available=17
        self.assertEqual(self.inv_service.get_stock_balance("WH-MAIN", "SKU-PHONE-01"), Decimal("17"))
        self.assertEqual(self.inv_service.get_locked_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("0"))
        self.assertEqual(self.inv_service.get_available_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("17"))

        # Verify updated order status
        refreshed_order = self.order_service.get_order(order.order_id)
        self.assertEqual(refreshed_order.status, OrderStatus.SHIPPED)

        # Verify PDF label validity with PyMuPDF
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(pdf_doc), 1)
        text_content = pdf_doc[0].get_text()
        self.assertIn("3Dollar EXPRESS LOGISTICS", text_content)
        self.assertIn("王小明", text_content)
        self.assertIn("0912345678", text_content)
        self.assertIn(do.do_id, text_content)
        pdf_doc.close()

        # Verify domain event
        self.assertEqual(len(self.shipped_events), 1)
        self.assertEqual(self.shipped_events[0].payload["order_id"], order.order_id)
        self.assertEqual(self.shipped_events[0].payload["do_id"], do.do_id)

    def test_overselling_lock_rejection(self):
        # Order 25 units when only 20 in stock
        order = self.order_service.create_order(
            customer_id="CUST-002",
            items=[("SKU-PHONE-01", Decimal("25"), Decimal("24000.0"))],
        )
        with self.assertRaises(InsufficientStockError):
            self.order_service.confirm_order(order.order_id, "WH-MAIN")

        # Order remains in DRAFT
        refreshed = self.order_service.get_order(order.order_id)
        self.assertEqual(refreshed.status, OrderStatus.DRAFT)
        self.assertEqual(self.inv_service.get_locked_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("0"))

    def test_order_cancellation_releases_stock(self):
        order = self.order_service.create_order(
            customer_id="CUST-003",
            items=[("SKU-PHONE-01", Decimal("5"), Decimal("24000.0"))],
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")
        self.assertEqual(self.inv_service.get_available_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("15"))

        # Cancel order
        cancelled = self.order_service.cancel_order(order.order_id)
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)

        # Locks freed, available returns to 20
        self.assertEqual(self.inv_service.get_available_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("20"))
        self.assertEqual(self.inv_service.get_locked_stock("WH-MAIN", "SKU-PHONE-01"), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
