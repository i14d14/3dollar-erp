from __future__ import annotations
import io
from decimal import Decimal
from typing import Optional
import xlsxwriter

from src.extended_core.accounting.models import IncomeStatement, TrialBalance


def export_trial_balance_xlsx(
    trial_balance: TrialBalance,
    company_name: str = "三圓科技股份有限公司",
) -> bytes:
    """Generate professional formatted Trial Balance Excel (.xlsx) file bytes."""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    ws = workbook.add_worksheet("會計試算表")

    # Formats
    title_fmt = workbook.add_format({
        "bold": True,
        "font_size": 16,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "valign": "vcenter",
    })
    subtitle_fmt = workbook.add_format({
        "bold": True,
        "font_size": 13,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "valign": "vcenter",
    })
    meta_fmt = workbook.add_format({
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "valign": "vcenter",
        "font_color": "#555555",
    })
    th_fmt = workbook.add_format({
        "bold": True,
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "bg_color": "#1E293B",
        "font_color": "#FFFFFF",
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
    text_cell = workbook.add_format({
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "border": 1,
        "valign": "vcenter",
    })
    code_cell = workbook.add_format({
        "font_size": 10,
        "font_name": "Consolas",
        "align": "center",
        "border": 1,
        "valign": "vcenter",
    })
    num_cell = workbook.add_format({
        "font_size": 10,
        "font_name": "Consolas",
        "num_format": "$#,##0.00",
        "border": 1,
        "align": "right",
        "valign": "vcenter",
    })
    total_label = workbook.add_format({
        "bold": True,
        "font_size": 11,
        "font_name": "Microsoft JhengHei",
        "bg_color": "#F1F5F9",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    total_num = workbook.add_format({
        "bold": True,
        "font_size": 11,
        "font_name": "Consolas",
        "num_format": "$#,##0.00",
        "bg_color": "#F1F5F9",
        "border": 1,
        "bottom": 6,  # double bottom border (accounting underline)
        "align": "right",
        "valign": "vcenter",
    })

    # Header section
    ws.merge_range("A1:G1", company_name, title_fmt)
    ws.merge_range("A2:G2", "會計試算表 (Trial Balance)", subtitle_fmt)
    ws.merge_range("A3:G3", f"基準日: {trial_balance.as_of_date.isoformat()}   幣別: 新台幣 (TWD)", meta_fmt)
    ws.set_row(0, 24)
    ws.set_row(1, 20)
    ws.set_row(2, 18)
    ws.set_row(4, 22)

    # Column Titles
    headers = [
        "科目代碼",
        "會計科目名稱",
        "科目類別",
        "借方累計發生",
        "貸方累計發生",
        "借方餘額 (Debit)",
        "貸方餘額 (Credit)",
    ]
    for col_idx, h in enumerate(headers):
        ws.write(4, col_idx, h, th_fmt)

    current_row = 5
    for item in trial_balance.items:
        ws.set_row(current_row, 18)
        ws.write(current_row, 0, item.account_code, code_cell)
        ws.write(current_row, 1, item.account_name, text_cell)
        ws.write(current_row, 2, item.account_type.value, text_cell)
        ws.write_number(current_row, 3, float(item.debit_total), num_cell)
        ws.write_number(current_row, 4, float(item.credit_total), num_cell)
        ws.write_number(current_row, 5, float(item.balance_debit), num_cell)
        ws.write_number(current_row, 6, float(item.balance_credit), num_cell)
        current_row += 1

    # Total Row
    ws.set_row(current_row, 22)
    ws.merge_range(current_row, 0, current_row, 4, "合 計 (Total)", total_label)
    ws.write_number(current_row, 5, float(trial_balance.total_debit), total_num)
    ws.write_number(current_row, 6, float(trial_balance.total_credit), total_num)

    # Auto-fit column widths
    col_widths = [12, 22, 14, 18, 18, 20, 20]
    for i, w in enumerate(col_widths):
        ws.set_column(i, i, w)

    workbook.close()
    return output.getvalue()


def export_income_statement_xlsx(
    income_statement: IncomeStatement,
    company_name: str = "三圓科技股份有限公司",
) -> bytes:
    """Generate professional formatted Income Statement Excel (.xlsx) file bytes."""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    ws = workbook.add_worksheet("損益表")

    # Formats
    title_fmt = workbook.add_format({
        "bold": True,
        "font_size": 16,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "valign": "vcenter",
    })
    subtitle_fmt = workbook.add_format({
        "bold": True,
        "font_size": 13,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "valign": "vcenter",
    })
    period_fmt = workbook.add_format({
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "align": "center",
        "font_color": "#555555",
    })
    th_fmt = workbook.add_format({
        "bold": True,
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "bg_color": "#0F172A",
        "font_color": "#FFFFFF",
        "align": "center",
        "border": 1,
    })
    item_fmt = workbook.add_format({
        "font_size": 11,
        "font_name": "Microsoft JhengHei",
        "valign": "vcenter",
        "border": 1,
    })
    indent_item_fmt = workbook.add_format({
        "font_size": 10,
        "font_name": "Microsoft JhengHei",
        "indent": 2,
        "valign": "vcenter",
        "border": 1,
    })
    highlight_item_fmt = workbook.add_format({
        "bold": True,
        "font_size": 11,
        "font_name": "Microsoft JhengHei",
        "bg_color": "#F8FAFC",
        "valign": "vcenter",
        "border": 1,
    })
    net_income_item_fmt = workbook.add_format({
        "bold": True,
        "font_size": 12,
        "font_name": "Microsoft JhengHei",
        "bg_color": "#E2E8F0",
        "valign": "vcenter",
        "border": 1,
    })
    num_fmt = workbook.add_format({
        "font_size": 11,
        "font_name": "Consolas",
        "num_format": "$#,##0.00",
        "align": "right",
        "valign": "vcenter",
        "border": 1,
    })
    pct_fmt = workbook.add_format({
        "font_size": 10,
        "font_name": "Consolas",
        "num_format": "0.00%",
        "align": "right",
        "valign": "vcenter",
        "border": 1,
    })
    highlight_num_fmt = workbook.add_format({
        "bold": True,
        "font_size": 11,
        "font_name": "Consolas",
        "num_format": "$#,##0.00",
        "bg_color": "#F8FAFC",
        "align": "right",
        "valign": "vcenter",
        "border": 1,
    })
    net_income_num_fmt = workbook.add_format({
        "bold": True,
        "font_size": 12,
        "font_name": "Consolas",
        "num_format": "$#,##0.00",
        "bg_color": "#E2E8F0",
        "align": "right",
        "valign": "vcenter",
        "border": 1,
        "bottom": 6,  # accounting double underline
    })

    # Header
    ws.merge_range("A1:C1", company_name, title_fmt)
    ws.merge_range("A2:C2", "損益表 (Income Statement)", subtitle_fmt)
    period_text = (
        f"期間: {income_statement.start_date.isoformat()} 至 {income_statement.end_date.isoformat()}"
        if income_statement.start_date
        else f"期間: 成立至今 至 {income_statement.end_date.isoformat()}"
    )
    ws.merge_range("A3:C3", f"{period_text}   幣別: 新台幣 (TWD)", period_fmt)

    ws.set_row(0, 24)
    ws.set_row(1, 20)
    ws.set_row(2, 18)
    ws.set_row(4, 22)

    # Table columns
    ws.write(4, 0, "會計項目 (Financial Item)", th_fmt)
    ws.write(4, 1, "金額 (TWD)", th_fmt)
    ws.write(4, 2, "營收比重 (%)", th_fmt)

    rev = float(income_statement.revenue)
    cogs = float(income_statement.cogs)
    gross = float(income_statement.gross_profit)
    exp = float(income_statement.operating_expenses)
    net = float(income_statement.net_profit)

    gross_pct = (gross / rev) if rev > 0 else 0.0
    cogs_pct = (cogs / rev) if rev > 0 else 0.0
    exp_pct = (exp / rev) if rev > 0 else 0.0
    net_pct = (net / rev) if rev > 0 else 0.0

    rows_data = [
        ("營業收入 (Sales Revenue)", rev, 1.0 if rev > 0 else 0.0, item_fmt, num_fmt),
        ("減：營業成本 (Cost of Goods Sold)", cogs, cogs_pct, indent_item_fmt, num_fmt),
        ("營業毛利 (Gross Profit)", gross, gross_pct, highlight_item_fmt, highlight_num_fmt),
        ("減：營業費用 (Operating Expenses)", exp, exp_pct, indent_item_fmt, num_fmt),
        ("本期營業淨利 (Operating Net Income)", net, net_pct, net_income_item_fmt, net_income_num_fmt),
    ]

    for idx, (label, val, pct, l_fmt, n_fmt) in enumerate(rows_data, start=5):
        ws.set_row(idx, 20)
        ws.write(idx, 0, label, l_fmt)
        ws.write_number(idx, 1, val, n_fmt)
        ws.write_number(idx, 2, pct, pct_fmt)

    ws.set_column(0, 0, 36)
    ws.set_column(1, 1, 22)
    ws.set_column(2, 2, 16)

    workbook.close()
    return output.getvalue()
