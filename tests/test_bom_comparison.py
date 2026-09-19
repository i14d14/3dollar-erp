from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
import openpyxl

from src.ai_wrapper.bom.models import BomItem, BomParseResult
from src.ai_wrapper.bom.parser import BomExcelParser
from src.ai_wrapper.bom.service import BomComparisonService
from src.shared.database import Database


class TestBomComparison(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.db.init_db()

        with self.db.transaction() as conn:
            # Seed warehouses and products
            conn.execute("INSERT INTO warehouses (warehouse_id, name) VALUES ('WH-01', '測試倉')")
            conn.execute(
                """
                INSERT INTO products (sku, name, base_unit, cost_price, selling_price, safety_stock)
                VALUES 
                ('SKU-A', '測試主機', 'PCS', 1000.0, 1500.0, 10),
                ('SKU-B', '擴充模組', 'PCS', 200.0, 350.0, 5)
                """
            )

            # Seed purchase orders from multiple suppliers with varying prices
            conn.execute(
                "INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount) VALUES ('PO-01', '甲廠商', 'RECEIVED', 5000.0)"
            )
            conn.execute(
                "INSERT INTO purchase_order_items (po_item_id, po_id, sku, qty, unit_cost, subtotal) VALUES ('POI-01', 'PO-01', 'SKU-A', 5.0, 950.0, 4750.0)"
            )

            conn.execute(
                "INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount) VALUES ('PO-02', '乙廠商', 'RECEIVED', 6000.0)"
            )
            conn.execute(
                "INSERT INTO purchase_order_items (po_item_id, po_id, sku, qty, unit_cost, subtotal) VALUES ('POI-02', 'PO-02', 'SKU-A', 5.0, 1100.0, 5500.0)"
            )
            conn.execute(
                "INSERT INTO purchase_order_items (po_item_id, po_id, sku, qty, unit_cost, subtotal) VALUES ('POI-03', 'PO-02', 'SKU-B', 10.0, 180.0, 1800.0)"
            )

            conn.execute(
                "INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount) VALUES ('PO-03', '丙廠商', 'RECEIVED', 3000.0)"
            )
            conn.execute(
                "INSERT INTO purchase_order_items (po_item_id, po_id, sku, qty, unit_cost, subtotal) VALUES ('POI-04', 'PO-03', 'SKU-B', 10.0, 220.0, 2200.0)"
            )

        self.parser = BomExcelParser()
        self.service = BomComparisonService(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_sample_excel(self) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["階層", "料號", "品名", "規格", "需求數量", "單位"])
        ws.append([1, "SKU-A", "測試主機", "規格A", 10, "PCS"])
        ws.append([1, "SKU-B", "擴充模組", "規格B", 20, "PCS"])
        ws.append([1, "SKU-UNKNOWN", "無歷史新物料", "規格C", 5, "PCS"])

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        return bio.getvalue()

    def test_bom_parser_successful(self):
        excel_bytes = self._create_sample_excel()
        res = self.parser.parse(excel_bytes)

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.items), 3)

        item_a = res.items[0]
        self.assertEqual(item_a.sku, "SKU-A")
        self.assertEqual(item_a.name, "測試主機")
        self.assertEqual(item_a.qty, Decimal("10"))
        self.assertEqual(item_a.unit, "PCS")

    def test_bom_parser_invalid_header(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["姓名", "電話", "備註"])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        res = self.parser.parse(bio.getvalue())
        self.assertTrue(any("無法自動辨識 BOM 欄位表頭" in e for e in res.errors))

    def test_bom_comparison_calculation(self):
        excel_bytes = self._create_sample_excel()
        parse_result = self.parser.parse(excel_bytes)
        summary = self.service.compare_bom(parse_result)

        self.assertEqual(summary.total_skus, 3)
        self.assertEqual(summary.total_qty, Decimal("35"))

        # Check SKU-A:
        # Quotes: 甲廠商 950, 乙廠商 1100
        # Qty: 10
        # Lowest: 950 * 10 = 9500
        # Highest: 1100 * 10 = 11000
        # Savings: 1500
        item_a = next(i for i in summary.items if i.sku == "SKU-A")
        self.assertTrue(item_a.has_history)
        self.assertIsNotNone(item_a.lowest_quote)
        self.assertEqual(item_a.lowest_quote.supplier_name, "甲廠商")
        self.assertEqual(item_a.lowest_quote.unit_cost, Decimal("950.0"))
        self.assertEqual(item_a.highest_quote.unit_cost, Decimal("1100.0"))
        self.assertEqual(item_a.estimated_subtotal_lowest, Decimal("9500.0"))
        self.assertEqual(item_a.estimated_subtotal_highest, Decimal("11000.0"))
        self.assertEqual(item_a.potential_savings, Decimal("1500.0"))

        # Check SKU-B:
        # Quotes: 乙廠商 180, 丙廠商 220
        # Qty: 20
        # Lowest: 180 * 20 = 3600
        # Highest: 220 * 20 = 4400
        # Savings: 800
        item_b = next(i for i in summary.items if i.sku == "SKU-B")
        self.assertEqual(item_b.lowest_quote.supplier_name, "乙廠商")
        self.assertEqual(item_b.lowest_quote.unit_cost, Decimal("180.0"))
        self.assertEqual(item_b.potential_savings, Decimal("800.0"))

        # Check SKU-UNKNOWN: No quotes
        item_unk = next(i for i in summary.items if i.sku == "SKU-UNKNOWN")
        self.assertFalse(item_unk.has_history)
        self.assertIsNone(item_unk.lowest_quote)
        self.assertEqual(item_unk.potential_savings, Decimal("0.0"))
        self.assertIn("SKU-UNKNOWN", summary.unquoted_skus)

        # Total savings = 1500 + 800 = 2300
        self.assertEqual(summary.total_potential_savings, Decimal("2300.0"))


if __name__ == "__main__":
    unittest.main()
