from __future__ import annotations
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import fitz

from src.core.adapters.mock_invoice_adapter import MockInvoiceProvider
from src.core.domain.invoice import ARStatus, InvoiceStatus, TaxType
from src.core.domain.order import OrderChannel
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import InMemoryEventBus


class TestInvoiceAndReconciliation(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_invoice.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.event_bus = InMemoryEventBus()
        self.inv_provider = MockInvoiceProvider(seller_tax_id="88888888", seller_name="3Dollar ERP Corp.")
        self.invoice_service = InvoiceService(db=self.db, invoice_provider=self.inv_provider, event_bus=self.event_bus)
        self.inv_service = InventoryService(db=self.db)
        self.order_service = OrderService(db=self.db, inventory_service=self.inv_service, event_bus=self.event_bus)

        # Seed warehouse and product
        self.wh = self.inv_service.create_warehouse("WH-MAIN", "台北總倉")
        self.product = self.inv_service.create_product(
            sku="SKU-CHAIR-01",
            name="人體工學辦公椅",
            base_unit="UNIT",
            cost_price=Decimal("2000.0"),
            selling_price=Decimal("4200.0"),
            safety_stock=2,
        )
        self.inv_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-CHAIR-01",
            qty_delta=Decimal("10"),
            unit_cost=Decimal("2000.0"),
            reference_id="INIT-CHAIRS",
        )

        self.inv_events = []
        self.event_bus.subscribe("ERP_INVOICE_ISSUED", lambda e: self.inv_events.append(e))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_issue_mig_321_invoice_and_render_receipt(self):
        # 1. Create and confirm order
        order = self.order_service.create_order(
            customer_id="CUST-B2B-1",
            channel=OrderChannel.DIRECT,
            items=[("SKU-CHAIR-01", Decimal("2"), Decimal("4200.0"))],  # Total = 8400
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")

        # 2. Issue invoice
        invoice, ar, pdf_bytes = self.invoice_service.issue_invoice_for_order(
            order_id=order.order_id,
            tax_type=TaxType.TAXABLE,
            buyer_tax_id="12345678",
            buyer_name="星耀科技有限公司",
            due_days=30,
        )

        # Verify MIG 3.2.1 Invoice attributes
        self.assertEqual(invoice.order_id, order.order_id)
        self.assertEqual(invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(invoice.total_amount, Decimal("8400.0"))
        # 8400 / 1.05 = 8000 sales, 400 tax
        self.assertEqual(invoice.tax_amount, Decimal("400.0"))
        # Validate invoice number: 2 uppercase letters + hyphen + 8 digits
        self.assertTrue(re.match(r"^[A-Z]{2}-\d{8}$", invoice.invoice_number))
        self.assertTrue(re.match(r"^\d{4}$", invoice.random_code))
        self.assertTrue(invoice.qrcode_l.endswith(":**"))
        self.assertIn("3Dollar ERP Corp.", invoice.qrcode_r)

        # Verify 1:1 Accounts Receivable (AR)
        self.assertEqual(ar.order_id, order.order_id)
        self.assertEqual(ar.invoice_id, invoice.invoice_id)
        self.assertEqual(ar.amount, Decimal("8400.0"))
        self.assertEqual(ar.status, ARStatus.UNPAID)

        # Verify 5.7cm wide PDF layout
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(len(doc), 1)
        rect = doc[0].rect
        self.assertAlmostEqual(rect.width, 161.57, delta=1.0)  # 5.7cm width
        text = doc[0].get_text()
        self.assertIn("電子發票證明聯", text)
        self.assertIn(invoice.invoice_number, text)
        self.assertIn(invoice.random_code, text)
        self.assertIn("8400", text)
        doc.close()

        # Verify domain event
        self.assertEqual(len(self.inv_events), 1)
        self.assertEqual(self.inv_events[0].payload["invoice_id"], invoice.invoice_id)

    def test_four_way_reconciliation_rigid_check(self):
        # 1. Setup order and ship
        order = self.order_service.create_order(
            customer_id="CUST-REC-01",
            channel=OrderChannel.DIRECT,
            items=[("SKU-CHAIR-01", Decimal("1"), Decimal("4200.0"))],
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")

        # At this point, neither DO, INV, nor AR exist -> Unreconciled
        report_before = self.invoice_service.verify_four_way_reconciliation(order.order_id)
        self.assertFalse(report_before.is_reconciled)
        self.assertIn(f"Delivery Order missing for SO '{order.order_id}'.", report_before.discrepancies)
        self.assertIn(f"Invoice missing for SO '{order.order_id}'.", report_before.discrepancies)

        # Ship order -> DO created
        self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="李經理",
            recipient_phone="0988776655",
            shipping_address="新北市板橋區縣民大道二段",
        )

        # Still missing INV & AR
        report_after_ship = self.invoice_service.verify_four_way_reconciliation(order.order_id)
        self.assertFalse(report_after_ship.is_reconciled)
        self.assertTrue(report_after_ship.do_exists)
        self.assertFalse(report_after_ship.inv_exists)

        # Issue Invoice -> INV and AR created
        self.invoice_service.issue_invoice_for_order(order.order_id)

        # Now all 4 documents exist and match in amount: SO == DO == INV == AR
        report_complete = self.invoice_service.verify_four_way_reconciliation(order.order_id)
        self.assertTrue(report_complete.is_reconciled)
        self.assertTrue(report_complete.so_exists)
        self.assertTrue(report_complete.do_exists)
        self.assertTrue(report_complete.inv_exists)
        self.assertTrue(report_complete.ar_exists)
        self.assertEqual(report_complete.so_amount, Decimal("4200.0"))
        self.assertEqual(report_complete.inv_amount, Decimal("4200.0"))
        self.assertEqual(report_complete.ar_amount, Decimal("4200.0"))
        self.assertEqual(len(report_complete.discrepancies), 0)


if __name__ == "__main__":
    unittest.main()
