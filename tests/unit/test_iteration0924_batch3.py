import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from starlette.testclient import TestClient

from src.channel_ui.web.app import create_app
from src.core.domain.order import OrderChannel
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestIteration0924Batch3(unittest.TestCase):
    """Unit and Integration tests for Iteration 0924 Batch 3: High-level name priority in Sales Orders & Fulfillment Modals."""

    def setUp(self):
        self.templates_dir = Path(__file__).resolve().parents[2] / "src" / "channel_ui" / "web" / "templates"

    def test_orders_table_header_prioritizes_customer_name(self):
        orders_path = self.templates_dir / "orders.html"
        self.assertTrue(orders_path.exists())
        content = orders_path.read_text(encoding="utf-8")

        # Table header must be '客戶名稱 / 下單時間'
        self.assertIn('<th class="px-4 py-3">客戶名稱 / 下單時間</th>', content)
        self.assertNotIn('<th class="px-4 py-3">客戶代號 / 下單時間</th>', content)

    def test_ship_confirm_modal_template_prioritizes_names(self):
        ship_modal_path = self.templates_dir / "partials" / "ship_confirm_modal.html"
        self.assertTrue(ship_modal_path.exists())
        content = ship_modal_path.read_text(encoding="utf-8")

        # Header customer name
        self.assertIn('客戶：{% if customer_name %}<span class="font-semibold text-slate-700">{{ customer_name }}</span> ({{ order.customer_id }}){% else %}{{ order.customer_id }}{% endif %}', content)

        # Table header: 商品品名 / SKU
        self.assertIn('商品品名 / SKU', content)
        self.assertNotIn('<div class="col-span-6">品號</div>', content)

        # Item row: product_name before sku
        pname_idx = content.find('{{ item.product_name or item.sku }}</div>')
        sku_idx = content.find('({{ item.sku }})</div>')
        self.assertNotEqual(pname_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(pname_idx, sku_idx, "item.product_name must appear before item.sku in ship_confirm_modal.html")

    def test_partial_ship_modal_template_prioritizes_names(self):
        partial_modal_path = self.templates_dir / "partials" / "partial_ship_modal.html"
        self.assertTrue(partial_modal_path.exists())
        content = partial_modal_path.read_text(encoding="utf-8")

        # Header customer name
        self.assertIn('客戶：{% if customer_name %}<span class="font-semibold text-slate-700">{{ customer_name }}</span> ({{ order.customer_id }}){% else %}{{ order.customer_id }}{% endif %}', content)

        # Table header: 商品品名 / SKU
        self.assertIn('商品品名 / SKU', content)
        self.assertNotIn('<div class="col-span-6">商品 SKU</div>', content)

        # Item row: product_name before sku
        pname_idx = content.find('{{ item.product_name or item.sku }}</div>')
        sku_idx = content.find('({{ item.sku }})</div>')
        self.assertNotEqual(pname_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(pname_idx, sku_idx, "item.product_name must appear before item.sku in partial_ship_modal.html")

    def test_deliveries_modal_template_prioritizes_names(self):
        deliveries_modal_path = self.templates_dir / "partials" / "deliveries_modal.html"
        self.assertTrue(deliveries_modal_path.exists())
        content = deliveries_modal_path.read_text(encoding="utf-8")

        # Table header: 商品品名 (SKU)
        self.assertIn('<th class="pb-1">商品品名 (SKU)</th>', content)
        self.assertNotIn('<th class="pb-1">商品編號 (SKU)</th>', content)

        # Row item: product_name before sku
        pname_idx = content.find('{{ alloc.product_name or alloc.sku }}</span>')
        sku_idx = content.find('({{ alloc.sku }})</span>')
        self.assertNotEqual(pname_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(pname_idx, sku_idx, "alloc.product_name must appear before alloc.sku in deliveries_modal.html")

    def test_live_modal_endpoints_resolve_and_render_human_readable_names(self):
        """End-to-end integration test verifying that all 3 fulfillment modals query and render resolved names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_modals_e2e.db"
            db = Database(db_path)
            db.init_db()

            event_bus = EventBus()
            inv_service = InventoryService(db=db)
            order_service = OrderService(db=db, event_bus=event_bus, inventory_service=inv_service)

            # 1. Create warehouse and product
            inv_service.create_warehouse("WH-MAIN", "台北總倉")
            inv_service.create_product(
                sku="SKU-OOLONG-99",
                name="特選阿里山高山茶",
                base_unit="BOX",
                cost_price=Decimal("400.0"),
                selling_price=Decimal("800.0"),
                safety_stock=10,
            )
            inv_service.adjust_stock(
                warehouse_id="WH-MAIN",
                sku="SKU-OOLONG-99",
                qty_delta=Decimal("50.0"),
                unit_cost=Decimal("400.0"),
                reference_id="PO-INIT-TEA",
            )

            # 2. Create customer contact in CRM
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO crm_contacts (contact_id, company_name, tax_id, contact_name, email, phone)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("CUST-TEA-001", "宏碁電腦股份有限公司", "12345678", "王經理", "wang@acer.com", "02-12345678"),
                )

            # 3. Create and confirm order
            order = order_service.create_order(
                customer_id="CUST-TEA-001",
                channel=OrderChannel.CRM,
                warehouse_id="WH-MAIN",
                items=[("SKU-OOLONG-99", Decimal("5.0"), Decimal("800.0"))],
            )
            order_service.confirm_order(order.order_id, "WH-MAIN")

            app = create_app(db=db, event_bus=event_bus)
            client = TestClient(app)

            # 4. Test ship modal endpoint
            resp_ship_modal = client.get(f"/orders/{order.order_id}/ship-modal")
            self.assertEqual(resp_ship_modal.status_code, 200)
            self.assertIn("宏碁電腦股份有限公司", resp_ship_modal.text)
            self.assertIn("CUST-TEA-001", resp_ship_modal.text)
            self.assertIn("特選阿里山高山茶", resp_ship_modal.text)
            self.assertIn("SKU-OOLONG-99", resp_ship_modal.text)

            # 5. Test partial ship modal endpoint
            resp_partial_modal = client.get(f"/orders/{order.order_id}/partial-ship-modal")
            self.assertEqual(resp_partial_modal.status_code, 200)
            self.assertIn("宏碁電腦股份有限公司", resp_partial_modal.text)
            self.assertIn("CUST-TEA-001", resp_partial_modal.text)
            self.assertIn("特選阿里山高山茶", resp_partial_modal.text)
            self.assertIn("SKU-OOLONG-99", resp_partial_modal.text)

            # 6. Ship partial quantity and test deliveries modal endpoint
            order_service.ship_order(
                order_id=order.order_id,
                warehouse_id="WH-MAIN",
                recipient_name="王經理",
                recipient_phone="02-12345678",
                shipping_address="新北市汐止區新台五路一段88號",
                items_to_ship=[(order.items[0].item_id, Decimal("2.0"))],
            )

            resp_deliv_modal = client.get(f"/orders/{order.order_id}/deliveries-modal")
            self.assertEqual(resp_deliv_modal.status_code, 200)
            self.assertIn("宏碁電腦股份有限公司", resp_deliv_modal.text)
            self.assertIn("特選阿里山高山茶", resp_deliv_modal.text)
            self.assertIn("SKU-OOLONG-99", resp_deliv_modal.text)


if __name__ == "__main__":
    unittest.main()
