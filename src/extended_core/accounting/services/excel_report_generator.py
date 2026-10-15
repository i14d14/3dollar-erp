from __future__ import annotations
import datetime
import io
from decimal import Decimal
from typing import Optional
import xlsxwriter

from src.core.domain.bom import BomComparisonSummary
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database, default_db


class AdvancedReportGenerator:
    """Enterprise report streaming generator using xlsxwriter for high performance and styling."""

    def __init__(self, db: Database = default_db) -> None:
        self.db = db
        self.accounting_service = AccountingService(db=db)

    def generate_sample_bom_excel(self) -> bytes:
        """Generate a realistic sample BOM Excel workbook with columns for testing."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("物料清單(BOM)")

        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1E293B",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 11,
        })
        data_fmt = workbook.add_format({
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
        })
        num_fmt = workbook.add_format({
            "valign": "vcenter",
            "align": "right",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
            "num_format": "#,##0",
        })

        headers = ["階層", "料號", "品名", "規格描述", "需求數量", "單位"]
        for col_idx, h in enumerate(headers):
            worksheet.write(0, col_idx, h, header_fmt)

        sample_rows = [
            (1, "SKU-PRO-01", "智慧旗艦終端機", "標準黑色鋁合金外殼款", 10, "PCS"),
            (1, "SKU-ACC-02", "高速傳輸擴充底座", "雙埠 USB-C / HDMI 4K", 25, "PCS"),
            (1, "SKU-IOT-03", "無線溫濕度傳感節點", "超低功耗 Zigbee 模組", 15, "PCS"),
            (2, "SKU-SENSOR-RAW", "微型溫濕度晶片模組", "SMD 封裝 0.1C 精度", 50, "PCS"),
            (2, "SKU-CABLE-05", "加固型編織傳輸線", "1.5m 尼龍編織 100W", 30, "PCS"),
        ]

        for row_idx, row in enumerate(sample_rows, start=1):
            worksheet.write(row_idx, 0, row[0], num_fmt)
            worksheet.write(row_idx, 1, row[1], data_fmt)
            worksheet.write(row_idx, 2, row[2], data_fmt)
            worksheet.write(row_idx, 3, row[3], data_fmt)
            worksheet.write(row_idx, 4, row[4], num_fmt)
            worksheet.write(row_idx, 5, row[5], data_fmt)

        worksheet.set_column(0, 0, 8)
        worksheet.set_column(1, 1, 18)
        worksheet.set_column(2, 2, 24)
        worksheet.set_column(3, 3, 26)
        worksheet.set_column(4, 4, 12)
        worksheet.set_column(5, 5, 8)

        workbook.close()
        output.seek(0)
        return output.getvalue()

    def generate_bom_comparison_excel(self, summary: BomComparisonSummary) -> bytes:
        """Generate formatted Excel report of BOM price comparison."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("BOM 採購比價分析")

        title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "font_color": "#0F172A",
            "font_name": "Microsoft JhengHei",
        })
        subtitle_fmt = workbook.add_format({
            "font_size": 10,
            "font_color": "#64748B",
            "font_name": "Microsoft JhengHei",
        })
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#3B82F6",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
        })
        best_supplier_fmt = workbook.add_format({
            "bg_color": "#DCFCE7",
            "font_color": "#166534",
            "bold": True,
            "border": 1,
            "font_name": "Microsoft JhengHei",
        })
        currency_fmt = workbook.add_format({
            "border": 1,
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        currency_best_fmt = workbook.add_format({
            "bg_color": "#DCFCE7",
            "font_color": "#166534",
            "bold": True,
            "border": 1,
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        savings_fmt = workbook.add_format({
            "bg_color": "#FEF3C7",
            "font_color": "#92400E",
            "bold": True,
            "border": 1,
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        regular_fmt = workbook.add_format({
            "border": 1,
            "font_name": "Microsoft JhengHei",
        })
        num_fmt = workbook.add_format({
            "border": 1,
            "num_format": "#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        total_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#F1F5F9",
            "border": 1,
            "top": 2,
            "bottom": 6,  # Double bottom accounting border
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        total_lbl_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#F1F5F9",
            "border": 1,
            "top": 2,
            "bottom": 6,
            "font_name": "Microsoft JhengHei",
        })

        # Header titles
        worksheet.write(0, 0, "3Dollar ERP - BOM 物料需求與多供應商比價分析報告", title_fmt)
        worksheet.write(1, 0, f"產生時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | 總項數: {summary.total_skus} 項 | 總節省潛力: ${int(summary.total_potential_savings):,}", subtitle_fmt)

        headers = [
            "料號 (SKU)", "物料名稱", "規格", "需求數量", "單位",
            "現行標準成本", "最低歷史單價", "推薦供應商", "最高歷史單價",
            "最低採購預估", "最高採購預估", "潛在節省金額",
        ]
        start_row = 3
        for c, h in enumerate(headers):
            worksheet.write(start_row, c, h, header_fmt)

        current_row = start_row + 1
        for item in summary.items:
            worksheet.write(current_row, 0, item.sku, regular_fmt)
            worksheet.write(current_row, 1, item.name, regular_fmt)
            worksheet.write(current_row, 2, item.spec or "-", regular_fmt)
            worksheet.write(current_row, 3, float(item.qty), num_fmt)
            worksheet.write(current_row, 4, item.unit, regular_fmt)
            worksheet.write(current_row, 5, float(item.standard_cost), currency_fmt)

            if item.lowest_quote:
                worksheet.write(current_row, 6, float(item.lowest_quote.unit_cost), currency_best_fmt)
                worksheet.write(current_row, 7, item.lowest_quote.supplier_name, best_supplier_fmt)
                worksheet.write(current_row, 8, float(item.highest_quote.unit_cost) if item.highest_quote else float(item.lowest_quote.unit_cost), currency_fmt)
            else:
                worksheet.write(current_row, 6, float(item.standard_cost), currency_fmt)
                worksheet.write(current_row, 7, "暫無歷史採購紀錄", regular_fmt)
                worksheet.write(current_row, 8, float(item.standard_cost), currency_fmt)

            worksheet.write(current_row, 9, float(item.estimated_subtotal_lowest), currency_best_fmt)
            worksheet.write(current_row, 10, float(item.estimated_subtotal_highest), currency_fmt)
            worksheet.write(current_row, 11, float(item.potential_savings), savings_fmt)
            current_row += 1

        # Total Summary Row
        worksheet.write(current_row, 0, "合計 (TOTAL)", total_lbl_fmt)
        worksheet.write(current_row, 1, "", total_lbl_fmt)
        worksheet.write(current_row, 2, "", total_lbl_fmt)
        worksheet.write(current_row, 3, float(summary.total_qty), total_fmt)
        worksheet.write(current_row, 4, "", total_lbl_fmt)
        worksheet.write(current_row, 5, "", total_lbl_fmt)
        worksheet.write(current_row, 6, "", total_lbl_fmt)
        worksheet.write(current_row, 7, "", total_lbl_fmt)
        worksheet.write(current_row, 8, "", total_lbl_fmt)
        worksheet.write(current_row, 9, float(summary.total_cost_lowest), total_fmt)
        worksheet.write(current_row, 10, float(summary.total_cost_highest), total_fmt)
        worksheet.write(current_row, 11, float(summary.total_potential_savings), total_fmt)

        worksheet.set_column(0, 0, 16)
        worksheet.set_column(1, 1, 20)
        worksheet.set_column(2, 2, 22)
        worksheet.set_column(3, 3, 10)
        worksheet.set_column(4, 4, 8)
        worksheet.set_column(5, 5, 14)
        worksheet.set_column(6, 6, 14)
        worksheet.set_column(7, 7, 20)
        worksheet.set_column(8, 8, 14)
        worksheet.set_column(9, 9, 16)
        worksheet.set_column(10, 10, 16)
        worksheet.set_column(11, 11, 16)

        workbook.close()
        output.seek(0)
        return output.getvalue()

    def generate_comprehensive_financial_report(self) -> bytes:
        """Generate multi-tab executive financial workbook (Income Statement, Trial Balance, Aging, Inventory)."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        # Formats
        title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 15,
            "font_color": "#1E293B",
            "font_name": "Microsoft JhengHei",
        })
        subtitle_fmt = workbook.add_format({
            "font_size": 9,
            "font_color": "#64748B",
            "font_name": "Microsoft JhengHei",
        })
        th_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1E293B",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
        })
        td_fmt = workbook.add_format({
            "border": 1,
            "font_name": "Microsoft JhengHei",
        })
        curr_fmt = workbook.add_format({
            "border": 1,
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        pct_fmt = workbook.add_format({
            "border": 1,
            "num_format": "0.0%",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        num_fmt = workbook.add_format({
            "border": 1,
            "num_format": "#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        subtotal_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#F8FAFC",
            "border": 1,
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        grand_total_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#E2E8F0",
            "border": 1,
            "top": 2,
            "bottom": 6,  # Double bottom border
            "num_format": "$#,##0",
            "align": "right",
            "font_name": "Microsoft JhengHei",
        })
        grand_total_lbl = workbook.add_format({
            "bold": True,
            "bg_color": "#E2E8F0",
            "border": 1,
            "top": 2,
            "bottom": 6,
            "font_name": "Microsoft JhengHei",
        })

        # --- Sheet 1: 損益表 (Income Statement) ---
        ws_is = workbook.add_worksheet("損益表 (Income Statement)")
        is_data = self.accounting_service.get_income_statement()

        ws_is.write(0, 0, "3Dollar ERP - 探吉會計損益表", title_fmt)
        ws_is.write(1, 0, f"報表日期: {datetime.date.today().isoformat()} | 幣別: 新台幣 (TWD)", subtitle_fmt)

        ws_is.write(3, 0, "項目名稱", th_fmt)
        ws_is.write(3, 1, "金額 (NTD)", th_fmt)
        ws_is.write(3, 2, "佔營收比例", th_fmt)

        rev = is_data.revenue
        cogs = is_data.cogs
        gp = is_data.gross_profit
        exp = is_data.operating_expenses
        np = is_data.net_profit

        rows_is = [
            ("營業收入 (Revenue)", float(rev), 1.0 if rev > 0 else 0.0, td_fmt),
            ("減：營業成本 (Cost of Goods Sold)", float(cogs), float(cogs / rev) if rev > 0 else 0.0, td_fmt),
            ("營業毛利 (Gross Profit)", float(gp), float(gp / rev) if rev > 0 else 0.0, subtotal_fmt),
            ("減：營業費用 (Operating Expenses)", float(exp), float(exp / rev) if rev > 0 else 0.0, td_fmt),
            ("本期營業淨利 (Net Operating Profit)", float(np), float(np / rev) if rev > 0 else 0.0, grand_total_fmt),
        ]

        for i, (label, val, pct, style) in enumerate(rows_is, start=4):
            lbl_style = grand_total_lbl if style == grand_total_fmt else (subtotal_fmt if style == subtotal_fmt else td_fmt)
            ws_is.write(i, 0, label, lbl_style)
            ws_is.write(i, 1, val, style)
            ws_is.write(i, 2, pct, pct_fmt)

        ws_is.set_column(0, 0, 32)
        ws_is.set_column(1, 1, 18)
        ws_is.set_column(2, 2, 14)

        # --- Sheet 2: 總分類帳試算表 (Trial Balance) ---
        ws_tb = workbook.add_worksheet("試算表 (Trial Balance)")
        tb_data = self.accounting_service.get_trial_balance()

        ws_tb.write(0, 0, "3Dollar ERP - 總分類帳試算表", title_fmt)
        balance_msg = "✓ 借貸嚴格平衡 (Balanced)" if tb_data.is_balanced else "⚠️ 借貸不平衡 (Imbalanced)"
        ws_tb.write(1, 0, f"基準日: {datetime.date.today().isoformat()} | 狀態: {balance_msg}", subtitle_fmt)

        headers_tb = ["科目代碼", "會計科目名稱", "科目類別", "借方累計發生額", "貸方累計發生額", "期末餘額借方", "期末餘額貸方"]
        for c, h in enumerate(headers_tb):
            ws_tb.write(3, c, h, th_fmt)

        tb_row = 4
        for item in tb_data.items:
            ws_tb.write(tb_row, 0, item.account_code, td_fmt)
            ws_tb.write(tb_row, 1, item.account_name, td_fmt)
            ws_tb.write(tb_row, 2, item.account_type.value, td_fmt)
            ws_tb.write(tb_row, 3, float(item.debit_total), curr_fmt)
            ws_tb.write(tb_row, 4, float(item.credit_total), curr_fmt)
            ws_tb.write(tb_row, 5, float(item.balance_debit), curr_fmt)
            ws_tb.write(tb_row, 6, float(item.balance_credit), curr_fmt)
            tb_row += 1

        # Totals
        ws_tb.write(tb_row, 0, "合計 (TOTAL)", grand_total_lbl)
        ws_tb.write(tb_row, 1, "", grand_total_lbl)
        ws_tb.write(tb_row, 2, "", grand_total_lbl)
        ws_tb.write(tb_row, 3, float(tb_data.total_debit), grand_total_fmt)
        ws_tb.write(tb_row, 4, float(tb_data.total_credit), grand_total_fmt)
        ws_tb.write(tb_row, 5, "", grand_total_lbl)
        ws_tb.write(tb_row, 6, "", grand_total_lbl)

        ws_tb.set_column(0, 0, 12)
        ws_tb.set_column(1, 1, 20)
        ws_tb.set_column(2, 2, 14)
        ws_tb.set_column(3, 6, 16)

        # --- Sheet 3: 應收/應付帳齡矩陣 (AR & AP Aging) ---
        ws_aging = workbook.add_worksheet("帳齡分析 (Aging Matrix)")
        ar_aging = self.accounting_service.get_ar_aging()
        ap_aging = self.accounting_service.get_ap_aging()

        ws_aging.write(0, 0, "3Dollar ERP - 應收帳款 (AR) 與應付帳款 (AP) 帳齡分析", title_fmt)
        ws_aging.write(1, 0, f"分析基準日: {datetime.date.today().isoformat()}", subtitle_fmt)

        ws_aging.write(3, 0, "應收帳款 (AR) 分佈", th_fmt)
        ws_aging.write(3, 1, "帳齡區間", th_fmt)
        ws_aging.write(3, 2, "未收總額", th_fmt)

        ar_buckets = [
            ("未到期 (Current)", float(ar_aging.current_amount)),
            ("逾期 1 - 30 天", float(ar_aging.days_1_30_amount)),
            ("逾期 31 - 60 天", float(ar_aging.days_31_60_amount)),
            ("逾期 60+ 天", float(ar_aging.days_60_plus_amount)),
        ]
        r = 4
        for b_name, b_val in ar_buckets:
            ws_aging.write(r, 1, b_name, td_fmt)
            ws_aging.write(r, 2, b_val, curr_fmt)
            r += 1
        ws_aging.write(r, 1, "應收總計", grand_total_lbl)
        ws_aging.write(r, 2, float(ar_aging.total_outstanding), grand_total_fmt)

        r += 2
        ws_aging.write(r, 0, "應付帳款 (AP) 分佈", th_fmt)
        ws_aging.write(r, 1, "帳齡區間", th_fmt)
        ws_aging.write(r, 2, "未付總額", th_fmt)
        r += 1

        ap_buckets = [
            ("未到期 (Current)", float(ap_aging.current_amount)),
            ("逾期 1 - 30 天", float(ap_aging.days_1_30_amount)),
            ("逾期 31 - 60 天", float(ap_aging.days_31_60_amount)),
            ("逾期 60+ 天", float(ap_aging.days_60_plus_amount)),
        ]
        for b_name, b_val in ap_buckets:
            ws_aging.write(r, 1, b_name, td_fmt)
            ws_aging.write(r, 2, b_val, curr_fmt)
            r += 1
        ws_aging.write(r, 1, "應付總計", grand_total_lbl)
        ws_aging.write(r, 2, float(ap_aging.total_outstanding), grand_total_fmt)

        ws_aging.set_column(0, 0, 20)
        ws_aging.set_column(1, 1, 22)
        ws_aging.set_column(2, 2, 18)

        # --- Sheet 4: 雙倉庫存盤點底冊 (Stock Inventory Valuation) ---
        ws_inv = workbook.add_worksheet("庫存盤點底冊 (Stock Valuation)")
        ws_inv.write(0, 0, "3Dollar ERP - 雙倉庫存盤點與估值底冊", title_fmt)
        ws_inv.write(1, 0, f"盤點基準日: {datetime.date.today().isoformat()}", subtitle_fmt)

        headers_inv = ["倉庫代碼", "倉庫名稱", "品號 (SKU)", "品名", "計量單位", "庫存數量", "移動平均單價", "庫存總估值"]
        for c, h in enumerate(headers_inv):
            ws_inv.write(3, c, h, th_fmt)

        inv_row = 4
        total_inv_val = Decimal("0.0")

        with self.db.transaction() as conn:
            stock_rows = conn.execute(
                """
                SELECT w.warehouse_id, w.name as wh_name, p.sku, p.name as prod_name, p.base_unit,
                       COALESCE(SUM(sl.qty_delta), 0) as physical_qty,
                       p.cost_price
                FROM warehouses w
                CROSS JOIN products p
                LEFT JOIN stock_ledger sl ON sl.warehouse_id = w.warehouse_id AND sl.sku = p.sku
                GROUP BY w.warehouse_id, p.sku
                ORDER BY w.warehouse_id, p.sku
                """
            ).fetchall()

            for sr in stock_rows:
                qty = Decimal(str(sr["physical_qty"]))
                cost = Decimal(str(sr["cost_price"]))
                val = qty * cost
                total_inv_val += val

                ws_inv.write(inv_row, 0, sr["warehouse_id"], td_fmt)
                ws_inv.write(inv_row, 1, sr["wh_name"], td_fmt)
                ws_inv.write(inv_row, 2, sr["sku"], td_fmt)
                ws_inv.write(inv_row, 3, sr["prod_name"], td_fmt)
                ws_inv.write(inv_row, 4, sr["base_unit"], td_fmt)
                ws_inv.write(inv_row, 5, float(qty), num_fmt)
                ws_inv.write(inv_row, 6, float(cost), curr_fmt)
                ws_inv.write(inv_row, 7, float(val), curr_fmt)
                inv_row += 1

        ws_inv.write(inv_row, 0, "合計 (TOTAL)", grand_total_lbl)
        ws_inv.write(inv_row, 1, "", grand_total_lbl)
        ws_inv.write(inv_row, 2, "", grand_total_lbl)
        ws_inv.write(inv_row, 3, "", grand_total_lbl)
        ws_inv.write(inv_row, 4, "", grand_total_lbl)
        ws_inv.write(inv_row, 5, "", grand_total_lbl)
        ws_inv.write(inv_row, 6, "", grand_total_lbl)
        ws_inv.write(inv_row, 7, float(total_inv_val), grand_total_fmt)

        ws_inv.set_column(0, 0, 14)
        ws_inv.set_column(1, 1, 16)
        ws_inv.set_column(2, 2, 16)
        ws_inv.set_column(3, 3, 24)
        ws_inv.set_column(4, 4, 10)
        ws_inv.set_column(5, 5, 12)
        ws_inv.set_column(6, 7, 16)

        workbook.close()
        output.seek(0)
        return output.getvalue()

    def generate_stock_inventory_valuation_excel(self) -> bytes:
        """Generate standalone stocktaking and inventory valuation Excel workbook (.xlsx)."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 15,
            "font_color": "#1E293B",
            "font_name": "Microsoft JhengHei",
        })
        subtitle_fmt = workbook.add_format({
            "font_size": 9,
            "font_color": "#64748B",
            "font_name": "Microsoft JhengHei",
        })
        th_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1E293B",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
        })
        td_fmt = workbook.add_format({
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
        })
        num_fmt = workbook.add_format({
            "valign": "vcenter",
            "align": "right",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
            "num_format": "#,##0",
        })
        curr_fmt = workbook.add_format({
            "valign": "vcenter",
            "align": "right",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
            "num_format": "NT$ #,##0.00",
        })
        grand_total_lbl = workbook.add_format({
            "bold": True,
            "bg_color": "#E2E8F0",
            "valign": "vcenter",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
        })
        grand_total_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#E2E8F0",
            "valign": "vcenter",
            "align": "right",
            "border": 1,
            "font_name": "Microsoft JhengHei",
            "font_size": 10,
            "num_format": "NT$ #,##0.00",
        })

        ws_inv = workbook.add_worksheet("庫存盤點底冊 (Stock Valuation)")
        ws_inv.write(0, 0, "3Dollar ERP - 雙倉庫存盤點與估值底冊", title_fmt)
        ws_inv.write(1, 0, f"盤點基準日: {datetime.date.today().isoformat()}", subtitle_fmt)

        headers_inv = ["倉庫代碼", "倉庫名稱", "品號 (SKU)", "品名", "計量單位", "庫存數量", "移動平均單價", "庫存總估值"]
        for c, h in enumerate(headers_inv):
            ws_inv.write(3, c, h, th_fmt)

        inv_row = 4
        total_inv_val = Decimal("0.0")

        with self.db.transaction() as conn:
            stock_rows = conn.execute(
                """
                SELECT w.warehouse_id, w.name as wh_name, p.sku, p.name as prod_name, p.base_unit,
                       COALESCE(SUM(sl.qty_delta), 0) as physical_qty,
                       p.cost_price
                FROM warehouses w
                CROSS JOIN products p
                LEFT JOIN stock_ledger sl ON sl.warehouse_id = w.warehouse_id AND sl.sku = p.sku
                GROUP BY w.warehouse_id, p.sku
                ORDER BY w.warehouse_id, p.sku
                """
            ).fetchall()

            for sr in stock_rows:
                qty = Decimal(str(sr["physical_qty"]))
                cost = Decimal(str(sr["cost_price"]))
                val = qty * cost
                total_inv_val += val

                ws_inv.write(inv_row, 0, sr["warehouse_id"], td_fmt)
                ws_inv.write(inv_row, 1, sr["wh_name"], td_fmt)
                ws_inv.write(inv_row, 2, sr["sku"], td_fmt)
                ws_inv.write(inv_row, 3, sr["prod_name"], td_fmt)
                ws_inv.write(inv_row, 4, sr["base_unit"], td_fmt)
                ws_inv.write(inv_row, 5, float(qty), num_fmt)
                ws_inv.write(inv_row, 6, float(cost), curr_fmt)
                ws_inv.write(inv_row, 7, float(val), curr_fmt)
                inv_row += 1

        ws_inv.write(inv_row, 0, "合計 (TOTAL)", grand_total_lbl)
        ws_inv.write(inv_row, 1, "", grand_total_lbl)
        ws_inv.write(inv_row, 2, "", grand_total_lbl)
        ws_inv.write(inv_row, 3, "", grand_total_lbl)
        ws_inv.write(inv_row, 4, "", grand_total_lbl)
        ws_inv.write(inv_row, 5, "", grand_total_lbl)
        ws_inv.write(inv_row, 6, "", grand_total_lbl)
        ws_inv.write(inv_row, 7, float(total_inv_val), grand_total_fmt)

        ws_inv.set_column(0, 0, 14)
        ws_inv.set_column(1, 1, 16)
        ws_inv.set_column(2, 2, 16)
        ws_inv.set_column(3, 3, 24)
        ws_inv.set_column(4, 4, 10)
        ws_inv.set_column(5, 5, 12)
        ws_inv.set_column(6, 7, 16)

        workbook.close()
        output.seek(0)
        return output.getvalue()
