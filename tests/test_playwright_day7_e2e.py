from __future__ import annotations
import os
import re
from pathlib import Path
import openpyxl
import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


def test_day7_unified_full_system_e2e(page: Page, tmp_path: Path):
    """Day 7 Full-System End-to-End Playwright Verification across all 4 layers:

    1. ERP Dashboard & Full Order Progression (DRAFT -> CONFIRMED -> SHIPPED -> COMPLETED).
    2. CRM Kanban & Customer Contacts (/crm).
    3. TanGii Accounting Trial Balance, P&L, and Aging Analysis (/accounting).
    4. AI File Tools & 4-in-1 Executive Financial Report Streaming (/ai/tools).
    """

    # -------------------------------------------------------------------------
    # 1. ERP Dashboard & Order Lifecycle (Dinkoko ERP)
    # -------------------------------------------------------------------------
    page.goto(f"{BASE_URL}/")
    expect(page.locator("h1").filter(has_text="營運即時儀表板").first).to_be_visible()

    # Verify KPI cards
    expect(page.locator("body")).to_contain_text("今日新增訂單")
    expect(page.locator("body")).to_contain_text("待出貨訂單")
    expect(page.locator("body")).to_contain_text("安全存量警報")
    expect(page.locator("body")).to_contain_text("待沖銷應收帳款")

    # Verify Multi-Channel badges in the orders table
    expect(page.locator("body")).to_contain_text("DIRECT")
    expect(page.locator("body")).to_contain_text("LINE")

    # Find a DRAFT order row to advance through the full lifecycle
    draft_btn = page.locator("button:has-text('鎖庫確認')").first
    if draft_btn.is_visible():
        row = draft_btn.locator("xpath=ancestor::tr")
        order_id_text = row.locator("td").first.locator("div").first.inner_text().strip()

        # Step 1: Click 鎖庫確認 -> transitions to CONFIRMED
        draft_btn.click()
        row_after_confirm = page.locator(f"#order-row-{order_id_text}")
        expect(row_after_confirm).to_contain_text("CONFIRMED", timeout=5000)
        expect(row_after_confirm.locator("button:has-text('一鍵出貨 (扣庫)')")).to_be_visible()

        # Step 2: Click 一鍵出貨 -> transitions to SHIPPED
        row_after_confirm.locator("button:has-text('一鍵出貨 (扣庫)')").click()
        row_after_ship = page.locator(f"#order-row-{order_id_text}")
        expect(row_after_ship).to_contain_text("SHIPPED", timeout=5000)
        expect(row_after_ship.locator("a:has-text('🏷️ 標籤')")).to_be_visible()
        expect(row_after_ship.locator("button:has-text('開立發票')")).to_be_visible()

        # Step 3: Click 開立發票 -> transitions to COMPLETED with both DO & INV dots green
        row_after_ship.locator("button:has-text('開立發票')").click()
        row_after_invoice = page.locator(f"#order-row-{order_id_text}")
        expect(row_after_invoice).to_contain_text("COMPLETED", timeout=5000)
        expect(row_after_invoice.locator("a:has-text('🧾 發票')")).to_be_visible()

    # -------------------------------------------------------------------------
    # 2. LiLai CRM Opportunity Kanban & Customer Directory (/crm)
    # -------------------------------------------------------------------------
    page.goto(f"{BASE_URL}/crm")
    expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM").first).to_be_visible()

    # Verify 4 Kanban stages
    expect(page.locator("body")).to_contain_text("潛在商機")
    expect(page.locator("body")).to_contain_text("需求洽談")
    expect(page.locator("body")).to_contain_text("方案報價")
    expect(page.locator("body")).to_contain_text("贏單成交")

    # Verify Customer Directory tab
    page.locator("a[href='/crm?tab=contacts']").click()
    expect(page.locator("body")).to_contain_text("宏達數位科技有限公司")
    expect(page.locator("body")).to_contain_text("24567890")

    # -------------------------------------------------------------------------
    # 3. TanGii Accounting Trial Balance, P&L and Aging (/accounting)
    # -------------------------------------------------------------------------
    page.goto(f"{BASE_URL}/accounting")
    expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()

    # Verify Financial KPIs
    expect(page.locator("body")).to_contain_text("本期營業收入")
    expect(page.locator("body")).to_contain_text("營業毛利")

    # Check Trial Balance strict balance
    page.locator("a[href='/accounting?tab=trial_balance']").click()
    expect(page.locator("body")).to_contain_text("借貸嚴格平衡")

    # Check Aging Analysis
    page.locator("a[href='/accounting?tab=aging']").click()
    expect(page.locator("body")).to_contain_text("帳齡分析")
    expect(page.locator("body")).to_contain_text("未到期")

    # -------------------------------------------------------------------------
    # 4. AI File Tools & 4-in-1 Executive Financial Report (/ai/tools)
    # -------------------------------------------------------------------------
    page.goto(f"{BASE_URL}/ai/tools")
    expect(page.locator("h1").filter(has_text="AI 檔案自動化").first).to_be_visible()

    # Switch to Reports tab and download 4-in-1 Report
    page.locator("#tab-btn-reports").click()
    expect(page.locator("#ai-tab-reports")).not_to_have_class(re.compile(r"hidden"))

    with page.expect_download() as rep_download_info:
        page.locator("a:has-text('匯出全套財務營運報表 (.xlsx)')").click()
    rep_download = rep_download_info.value
    assert re.search(r"3dollar_financial_executive_.*\.xlsx", rep_download.suggested_filename)

    rep_path = tmp_path / "playwright_report.xlsx"
    rep_download.save_as(str(rep_path))
    assert rep_path.stat().st_size > 2000

    wb = openpyxl.load_workbook(str(rep_path), read_only=True)
    sheet_names = wb.sheetnames
    assert "損益表 (Income Statement)" in sheet_names
    assert "試算表 (Trial Balance)" in sheet_names
    assert "帳齡分析 (Aging Matrix)" in sheet_names
    assert "庫存盤點底冊 (Stock Valuation)" in sheet_names
    wb.close()
