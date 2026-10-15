import unittest
from pathlib import Path


class TestIteration0924Batch2(unittest.TestCase):
    """Unit tests for Iteration 0924 Batch 2: High-level name priority in Procurement Center."""

    def setUp(self):
        self.templates_dir = Path(__file__).resolve().parents[2] / "src" / "channel_ui" / "web" / "templates"

    def test_procurement_form_prioritizes_product_name(self):
        procurement_path = self.templates_dir / "procurement.html"
        self.assertTrue(procurement_path.exists())
        content = procurement_path.read_text(encoding="utf-8")

        # Table header must be '採購物料 (品名 / SKU)'
        self.assertIn('<th class="px-3 py-2 w-5/12">採購物料 (品名 / SKU)</th>', content)
        self.assertNotIn('<th class="px-3 py-2 w-5/12">採購物料 (SKU / 品名)</th>', content)

        # Dropdown options must format as '{{ p.name }} ({{ p.sku }}) - 目前成本: {{ p.cost_price_formatted }}'
        self.assertIn('{{ p.name }} ({{ p.sku }}) - 目前成本: {{ p.cost_price_formatted }}', content)

    def test_po_row_prioritizes_product_name_over_sku(self):
        po_row_path = self.templates_dir / "partials" / "po_row.html"
        self.assertTrue(po_row_path.exists())
        content = po_row_path.read_text(encoding="utf-8")

        # Product name must be rendered in bold font-semibold text
        self.assertIn('<span class="font-semibold text-slate-800">{{ item.product_name }}</span>', content)
        # SKU must be rendered in muted monospace text in parentheses
        self.assertIn('<span class="font-mono text-xs text-slate-400">({{ item.sku }})</span>', content)

        # Product name must precede SKU in item display
        pname_idx = content.find('{{ item.product_name }}</span>')
        sku_idx = content.find('({{ item.sku }})</span>')
        self.assertNotEqual(pname_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(pname_idx, sku_idx, "item.product_name must appear before item.sku in po_row.html")

    def test_receive_po_modal_prioritizes_names(self):
        receive_modal_path = self.templates_dir / "partials" / "receive_po_modal.html"
        self.assertTrue(receive_modal_path.exists())
        content = receive_modal_path.read_text(encoding="utf-8")

        # Destination warehouse: Name (ID)
        self.assertIn('{{ wh.name }} ({{ wh.warehouse_id }})', content)

        # Header: 品名 / 品號
        self.assertIn('品名 / 品號 (SKU)', content)

        # Item row: product_name before sku
        pname_idx = content.find('{{ item.product_name }}</div>')
        sku_idx = content.find('{{ item.sku }}</div>')
        self.assertNotEqual(pname_idx, -1)
        self.assertNotEqual(sku_idx, -1)
        self.assertLess(pname_idx, sku_idx, "item.product_name must appear before item.sku in receive_po_modal.html")

    def test_procurement_bom_result_prioritizes_product_name(self):
        bom_result_path = self.templates_dir / "partials" / "procurement_bom_result.html"
        self.assertTrue(bom_result_path.exists())
        content = bom_result_path.read_text(encoding="utf-8")

        # Table header: 物料名稱 / 規格 must precede 料號 (SKU)
        name_hdr_idx = content.find('<th class="py-2.5 px-3">物料名稱 / 規格</th>')
        sku_hdr_idx = content.find('<th class="py-2.5 px-3">料號 (SKU)</th>')
        self.assertNotEqual(name_hdr_idx, -1)
        self.assertNotEqual(sku_hdr_idx, -1)
        self.assertLess(name_hdr_idx, sku_hdr_idx, "物料名稱 / 規格 header must appear before 料號 (SKU)")


if __name__ == "__main__":
    unittest.main()
