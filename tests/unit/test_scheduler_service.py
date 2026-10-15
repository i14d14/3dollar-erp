from __future__ import annotations
import datetime
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.core.domain.invoice import ARStatus, TaxType
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.core.services.scheduler_service import SchedulerService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestSchedulerService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_scheduler.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.inv_service = InventoryService(db=self.db)
        self.order_service = OrderService(db=self.db, event_bus=self.event_bus, inventory_service=self.inv_service)
        self.invoice_service = InvoiceService(db=self.db, event_bus=self.event_bus)
        self.scheduler = SchedulerService(db=self.db, inventory_service=self.inv_service)

        # Seed warehouses
        self.wh_main = self.inv_service.create_warehouse("WH-MAIN", "台北總倉")
        self.wh_store = self.inv_service.create_warehouse("WH-STORE", "信義門市倉")

        # Product A: safety stock 10
        self.prod_a = self.inv_service.create_product(
            sku="SKU-ALERT-01",
            name="警告品項A",
            safety_stock=10,
        )
        # Product B: safety stock 5
        self.prod_b = self.inv_service.create_product(
            sku="SKU-OK-02",
            name="正常品項B",
            safety_stock=5,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_low_safety_stock_scan(self):
        # WH-MAIN: Product A has 8 (below safety 10 -> shortage 2)
        self.inv_service.adjust_stock("WH-MAIN", "SKU-ALERT-01", Decimal("8"), Decimal("100"), "INIT-A")
        # WH-MAIN: Product B has 20 (above safety 5)
        self.inv_service.adjust_stock("WH-MAIN", "SKU-OK-02", Decimal("20"), Decimal("100"), "INIT-B")

        alerts = self.scheduler.scan_low_safety_stock("WH-MAIN")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].sku, "SKU-ALERT-01")
        self.assertEqual(alerts[0].available_stock, Decimal("8"))
        self.assertEqual(alerts[0].shortage, Decimal("2"))

    def test_scan_overdue_receivables(self):
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        future_date = today + datetime.timedelta(days=10)

        # Create two orders and invoices
        order1 = self.order_service.create_order("CUST-1", [("SKU-OK-02", Decimal("1"), Decimal("500.0"))])
        order2 = self.order_service.create_order("CUST-2", [("SKU-OK-02", Decimal("1"), Decimal("800.0"))])

        # Issue invoices
        _, ar1, _ = self.invoice_service.issue_invoice_for_order(order1.order_id, due_days=30)
        _, ar2, _ = self.invoice_service.issue_invoice_for_order(order2.order_id, due_days=30)

        # Manually alter AR1 due_date to yesterday in database to simulate passage of time
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE accounts_receivable SET due_date = ? WHERE ar_id = ?",
                (yesterday.isoformat(), ar1.ar_id),
            )
            conn.execute(
                "UPDATE accounts_receivable SET due_date = ? WHERE ar_id = ?",
                (future_date.isoformat(), ar2.ar_id),
            )

        # Run scan
        overdue_list = self.scheduler.scan_overdue_receivables(as_of_date=today)
        self.assertEqual(len(overdue_list), 1)
        self.assertEqual(overdue_list[0].ar_id, ar1.ar_id)
        self.assertEqual(overdue_list[0].status, ARStatus.OVERDUE)

    def test_run_daily_batch(self):
        today = datetime.date.today()
        summary = self.scheduler.run_daily_batch(as_of_date=today)
        self.assertEqual(summary.batch_date, today)
        self.assertIsInstance(summary.low_stock_alerts, list)
        self.assertIsInstance(summary.overdue_receivables, list)


if __name__ == "__main__":
    unittest.main()
