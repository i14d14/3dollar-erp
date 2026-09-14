from __future__ import annotations
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.inventory import ReferenceType
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database


class TestWebGUI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp_web.db"
        self.db = Database(self.db_path)
        self.db.init_db()

        self.inventory_service = InventoryService(db=self.db)
        self.order_service = OrderService(db=self.db, inventory_service=self.inventory_service)

        # Seed initial warehouses and product
        self.inventory_service.create_warehouse("WH-MAIN", "台北總倉")
        self.inventory_service.create_warehouse("WH-STORE", "信義旗艦店")
        self.inventory_service.create_product(
            sku="SKU-PRO-1",
            name="智慧旗艦終端",
            base_unit="PCS",
            cost_price=Decimal("1500.0"),
            selling_price=Decimal("2500.0"),
            safety_stock=20,
        )

        # Inward initial stock to WH-MAIN (50 units)
        self.inventory_service.adjust_stock(
            warehouse_id="WH-MAIN",
            sku="SKU-PRO-1",
            qty_delta=Decimal("50.0"),
            unit_cost=Decimal("1500.0"),
            reference_id="INIT-001",
            notes="期初庫存入庫",
        )

        # Create test client
        self.app = create_app(db=self.db)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("營運即時儀表板", content)
        self.assertIn("今日新增訂單", content)
        self.assertIn("待出貨訂單", content)
        self.assertIn("安全存量警報", content)
        self.assertIn("智慧旗艦終端", content)

    def test_orders_page_and_htmx_fulfillment_flow(self) -> None:
        # 1. Create order
        order = self.order_service.create_order(
            customer_id="CUST-VIP-001",
            items=[("SKU-PRO-1", Decimal("2.0"), Decimal("2500.0"))],
        )

        # 2. View orders page
        resp_list = self.client.get("/orders")
        self.assertEqual(resp_list.status_code, 200)
        self.assertIn(order.order_id, resp_list.text)
        self.assertIn("DRAFT", resp_list.text)
        self.assertIn("鎖庫確認", resp_list.text)

        # 3. HTMX Confirm order
        resp_confirm = self.client.post(f"/orders/{order.order_id}/confirm")
        self.assertEqual(resp_confirm.status_code, 200)
        self.assertIn("CONFIRMED", resp_confirm.text)
        self.assertIn("一鍵出貨 (扣庫)", resp_confirm.text)

        # Verify stock locked
        physical = self.inventory_service.get_stock_balance("WH-MAIN", "SKU-PRO-1")
        locked = self.inventory_service.get_locked_stock("WH-MAIN", "SKU-PRO-1")
        available = self.inventory_service.get_available_stock("WH-MAIN", "SKU-PRO-1")
        self.assertEqual(physical, Decimal("50.0"))
        self.assertEqual(locked, Decimal("2.0"))
        self.assertEqual(available, Decimal("48.0"))

        # 4. HTMX Ship order
        resp_ship = self.client.post(f"/orders/{order.order_id}/ship")
        self.assertEqual(resp_ship.status_code, 200)
        self.assertIn("SHIPPED", resp_ship.text)
        self.assertIn("開立發票", resp_ship.text)
        self.assertIn("🏷️ 標籤", resp_ship.text)

        # Verify physical stock deducted
        physical_after = self.inventory_service.get_stock_balance("WH-MAIN", "SKU-PRO-1")
        locked_after = self.inventory_service.get_locked_stock("WH-MAIN", "SKU-PRO-1")
        available_after = self.inventory_service.get_available_stock("WH-MAIN", "SKU-PRO-1")
        self.assertEqual(physical_after, Decimal("48.0"))
        self.assertEqual(locked_after, Decimal("0.0"))
        self.assertEqual(available_after, Decimal("48.0"))

        # 5. HTMX Issue invoice
        resp_inv = self.client.post(f"/orders/{order.order_id}/invoice")
        self.assertEqual(resp_inv.status_code, 200)
        self.assertIn("🧾 發票", resp_inv.text)
        self.assertIn("AB-", resp_inv.text)

    def test_pdf_streaming_downloads(self) -> None:
        order = self.order_service.create_order(
            customer_id="CUST-VIP-002",
            items=[("SKU-PRO-1", Decimal("1.0"), Decimal("2500.0"))],
        )
        self.order_service.confirm_order(order.order_id, "WH-MAIN")
        self.order_service.ship_order(
            order_id=order.order_id,
            warehouse_id="WH-MAIN",
            recipient_name="王小明",
            recipient_phone="0911-222-333",
            shipping_address="台北市信義區忠孝東路五段100號",
        )
        invoice_service = self.order_service.inventory_service.db
        from src.core.services.invoice_service import InvoiceService
        inv_svc = InvoiceService(db=invoice_service)
        inv_svc.issue_invoice_for_order(order.order_id)

        # 1. Download Shipping Label PDF
        label_resp = self.client.get(f"/orders/{order.order_id}/label.pdf")
        self.assertEqual(label_resp.status_code, 200)
        self.assertEqual(label_resp.headers["content-type"], "application/pdf")
        self.assertTrue(label_resp.content.startswith(b"%PDF-"))

        # 2. Download Invoice Receipt PDF
        invoice_resp = self.client.get(f"/orders/{order.order_id}/invoice.pdf")
        self.assertEqual(invoice_resp.status_code, 200)
        self.assertEqual(invoice_resp.headers["content-type"], "application/pdf")
        self.assertTrue(invoice_resp.content.startswith(b"%PDF-"))

    def test_inventory_page_and_transfer_htmx(self) -> None:
        # View inventory page
        inv_resp = self.client.get("/inventory")
        self.assertEqual(inv_resp.status_code, 200)
        self.assertIn("台北總倉", inv_resp.text)
        self.assertIn("信義旗艦店", inv_resp.text)
        self.assertIn("50", inv_resp.text)  # WH-MAIN has 50

        # Transfer 15 units from WH-MAIN to WH-STORE via HTMX POST
        transfer_resp = self.client.post(
            "/inventory/transfer",
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-PRO-1",
                "qty": 15,
            },
        )
        self.assertEqual(transfer_resp.status_code, 200)
        # Check returned partial
        self.assertIn("35", transfer_resp.text)  # WH-MAIN has 35 remaining
        self.assertIn("15", transfer_resp.text)  # WH-STORE has 15

        # Verify DB balances
        main_bal = self.inventory_service.get_stock_balance("WH-MAIN", "SKU-PRO-1")
        store_bal = self.inventory_service.get_stock_balance("WH-STORE", "SKU-PRO-1")
        self.assertEqual(main_bal, Decimal("35.0"))
        self.assertEqual(store_bal, Decimal("15.0"))

    def test_insufficient_stock_transfer_htmx_error(self) -> None:
        # Transfer exceeds available stock
        err_resp = self.client.post(
            "/inventory/transfer",
            headers={"HX-Request": "true"},
            data={
                "from_warehouse_id": "WH-MAIN",
                "to_warehouse_id": "WH-STORE",
                "sku": "SKU-PRO-1",
                "qty": 99999,
            },
        )
        self.assertEqual(err_resp.status_code, 400)
        self.assertIn("執行失敗", err_resp.text)


if __name__ == "__main__":
    unittest.main()
