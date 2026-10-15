import unittest
from pathlib import Path


class TestIteration0924Batch1(unittest.TestCase):
    """Unit tests for Iteration 0924 Batch 1: High-level name priority in Dashboard & Inventory."""

    def setUp(self):
        self.templates_dir = Path(__file__).resolve().parents[2] / "src" / "channel_ui" / "web" / "templates"

    def test_dashboard_low_stock_cards_prioritize_product_name(self):
        dashboard_path = self.templates_dir / "dashboard.html"
        self.assertTrue(dashboard_path.exists())
        content = dashboard_path.read_text(encoding="utf-8")

        # Product name must be rendered as the prominent font-bold title
        self.assertIn('<div class="font-bold text-slate-900 text-sm leading-snug">{{ item.product_name }}</div>', content)
        # SKU must be rendered as secondary monospace badge
        self.assertIn('{{ item.sku }}</span>', content)
        # Table header updated
        self.assertIn('<th class="px-4 py-3">客戶名稱 / 下單時間</th>', content)

    def test_stock_table_column_order_product_name_first(self):
        stock_table_path = self.templates_dir / "partials" / "stock_table.html"
        self.assertTrue(stock_table_path.exists())
        content = stock_table_path.read_text(encoding="utf-8")

        # Table header: 商品名稱 must precede 品號 (SKU)
        name_idx = content.find('<th class="px-4 py-3">商品名稱</th>')
        sku_idx = content.find('<th class="px-4 py-3">品號 (SKU)</th>')
        self.assertNotEqual(name_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(name_idx, sku_idx, "商品名稱 header must come before 品號 (SKU) header")

        # Row data: item.product_name must precede item.sku
        pname_row_idx = content.find('{{ item.product_name }}</td>')
        sku_row_idx = content.find('{{ item.sku }}</td>')
        self.assertNotEqual(pname_row_idx, -1)
        self.assertNotEqual(sku_row_idx, -1)
        self.assertLess(pname_row_idx, sku_row_idx, "item.product_name cell must come before item.sku cell")

    def test_stock_row_column_order_product_name_first(self):
        stock_row_path = self.templates_dir / "partials" / "stock_row.html"
        self.assertTrue(stock_row_path.exists())
        content = stock_row_path.read_text(encoding="utf-8")

        # Row data: item.product_name must precede item.sku
        pname_row_idx = content.find('{{ item.product_name }}</td>')
        sku_row_idx = content.find('{{ item.sku }}</td>')
        self.assertNotEqual(pname_row_idx, -1)
        self.assertNotEqual(sku_row_idx, -1)
        self.assertLess(pname_row_idx, sku_row_idx, "item.product_name cell must come before item.sku cell")


if __name__ == "__main__":
    unittest.main()
