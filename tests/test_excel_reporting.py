from __future__ import annotations
import io
import unittest
from decimal import Decimal
import openpyxl

from src.ai_wrapper.bom.models import BomComparisonItem, BomComparisonSummary, SupplierPriceQuote
from src.ai_wrapper.reporting.excel_generator import AdvancedReportGenerator
from src.channel_ui.web.demo_seed import seed_demo_data
import tempfile
from pathlib import Path
from src.shared.database import Database
from src.shared.event_bus import EventBus


class TestExcelReporting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_erp.db"
        self.db = Database(db_path=self.db_path)
        self.db.init_db()
        self.bus = EventBus()
        seed_demo_data(self.db, event_bus=self.bus)
        self.generator = AdvancedReportGenerator(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_sample_bom_excel(self):
        content = self.generator.generate_sample_bom_excel()
        self.assertIsInstance(content, bytes)
        self.assertGreater(len(content), 1000)

        # Inspect generated workbook with openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content))
        self.assertIn("物料清單(BOM)", wb.sheetnames)
        ws = wb["物料清單(BOM)"]
        self.assertEqual(ws.cell(1, 1).value, "階層")
        self.assertEqual(ws.cell(1, 2).value, "料號")

    def test_generate_bom_comparison_excel(self):
        summary = BomComparisonSummary(
            total_skus=2,
            total_qty=Decimal("30"),
            total_cost_lowest=Decimal("25000"),
            total_cost_highest=Decimal("30000"),
            total_cost_standard=Decimal("28000"),
            total_potential_savings=Decimal("5000"),
            items=[
                BomComparisonItem(
                    sku="SKU-PRO-01",
                    name="智慧旗艦終端機",
                    spec="鋁合金",
                    qty=Decimal("10"),
                    unit="PCS",
                    standard_cost=Decimal("1500"),
                    lowest_quote=SupplierPriceQuote(supplier_name="供應商A", unit_cost=Decimal("1400")),
                    highest_quote=SupplierPriceQuote(supplier_name="供應商B", unit_cost=Decimal("1600")),
                    estimated_subtotal_lowest=Decimal("14000"),
                    estimated_subtotal_highest=Decimal("16000"),
                    potential_savings=Decimal("2000"),
                    has_history=True,
                )
            ],
            unquoted_skus=[],
        )

        content = self.generator.generate_bom_comparison_excel(summary)
        self.assertIsInstance(content, bytes)
        self.assertGreater(len(content), 1000)

        wb = openpyxl.load_workbook(io.BytesIO(content))
        self.assertIn("BOM 採購比價分析", wb.sheetnames)

    def test_generate_comprehensive_financial_report(self):
        content = self.generator.generate_comprehensive_financial_report()
        self.assertIsInstance(content, bytes)
        self.assertGreater(len(content), 2000)

        wb = openpyxl.load_workbook(io.BytesIO(content))
        expected_sheets = [
            "損益表 (Income Statement)",
            "試算表 (Trial Balance)",
            "帳齡分析 (Aging Matrix)",
            "庫存盤點底冊 (Stock Valuation)",
        ]
        for s in expected_sheets:
            self.assertIn(s, wb.sheetnames, f"Expected sheet '{s}' missing from financial workbook")


if __name__ == "__main__":
    unittest.main()
