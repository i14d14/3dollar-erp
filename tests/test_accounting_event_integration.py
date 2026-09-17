import datetime
import unittest
from decimal import Decimal
import tempfile
from pathlib import Path

from src.core.domain.order import OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.extended_core.accounting.services.event_handlers import register_accounting_event_handlers
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestAccountingEventIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.db.init_db()

        self.event_bus = EventBus()
        self.accounting_service = AccountingService(db=self.db)
        self.event_handler = register_accounting_event_handlers(
            event_bus=self.event_bus,
            accounting_service=self.accounting_service,
            db=self.db,
        )

        self.inventory_service = InventoryService(db=self.db)
        self.procurement_service = ProcurementService(db=self.db, event_bus=self.event_bus)
        self.order_service = OrderService(db=self.db, inventory_service=self.inventory_service, event_bus=self.event_bus)
        self.invoice_service = InvoiceService(db=self.db, event_bus=self.event_bus)

        # Setup standard warehouse and product
        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_product(
            sku="SKU-PRO-01",
            name="智慧旗艦終端機",
            cost_price=Decimal("1000.0"),
            selling_price=Decimal("2000.0"),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_event_driven_accounting_pipeline(self):
        # 1. Procurement: PO -> GRN (receives 10 pcs @ 1000)
        po = self.procurement_service.create_purchase_order(
            supplier_name="精準供應商",
            items=[("SKU-PRO-01", Decimal("10.0"), Decimal("1000.0"))],
        )
        self.procurement_service.submit_purchase_order(po.po_id)
        grn = self.procurement_service.receive_goods(po.po_id, "WH-MAIN")

        # Verify AP created
        ap_aging = self.accounting_service.get_ap_aging()
        self.assertEqual(ap_aging.total_outstanding, Decimal("10000.0"))

        # Verify Journal entry for GRN: Dr 1201 存貨 10000, Cr 2144 應付帳款 10000
        entries = self.accounting_service.get_journal_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].source_event, "ERP_GOODS_RECEIVED")
        self.assertEqual(entries[0].reference_id, grn.grn_id)

        # 2. Sales: Order -> Confirm -> Ship (sell 2 pcs @ 2000)
        order = self.order_service.create_order(
            customer_id="買方大同企業",
            items=[("SKU-PRO-01", Decimal("2.0"), Decimal("2000.0"))],
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")
        do, _ = self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="張經理",
            recipient_phone="0911-222-333",
            shipping_address="台北市大安區忠孝東路1號",
        )

        # Verify Journal entry for Shipping: Dr 5111 銷貨成本 2000, Cr 1201 存貨 2000
        entries = self.accounting_service.get_journal_entries()
        self.assertEqual(len(entries), 2)
        shipped_entry = next(e for e in entries if e.source_event == "ERP_ORDER_SHIPPED")
        self.assertEqual(shipped_entry.reference_id, do.do_id)
        cogs_line = next(l for l in shipped_entry.lines if l.account_code == "5111")
        self.assertEqual(cogs_line.debit, Decimal("2000.0"))

        # 3. Invoicing: Issue Invoice (4000 total, with 5% tax = 200)
        inv, ar, _ = self.invoice_service.issue_invoice_for_order(order.order_id)

        # Verify Journal entry for Invoicing: Dr 1144 應收帳款 4000, Cr 4111 銷貨收入 3800, Cr 2201 銷項稅額 200
        entries = self.accounting_service.get_journal_entries()
        self.assertEqual(len(entries), 3)
        inv_entry = next(e for e in entries if e.source_event == "ERP_INVOICE_ISSUED")
        self.assertEqual(inv_entry.reference_id, inv.invoice_id)
        ar_line = next(l for l in inv_entry.lines if l.account_code == "1144")
        self.assertEqual(ar_line.debit, Decimal("4000.0"))

        # 4. Verify Trial Balance is balanced across all events
        tb = self.accounting_service.get_trial_balance()
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)

        # 5. Verify Income Statement
        income = self.accounting_service.get_income_statement()
        # In Taiwan MIG 3.2.1: 4000 / 1.05 = 3810 sales amount, 190 tax amount
        self.assertEqual(income.revenue, Decimal("3810.0"))
        self.assertEqual(income.cogs, Decimal("2000.0"))
        self.assertEqual(income.gross_profit, Decimal("1810.0"))


if __name__ == "__main__":
    unittest.main()
