from __future__ import annotations
import os
import re
from pathlib import Path
import openpyxl
import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


def test_day6_full_user_flow(page: Page, tmp_path: Path):
    """E2E verification of Day 6 AI & File Automation features across all 5 spec scenarios."""

    # ---------------------------------------------------------
    # Scenario 1: Page Load & Tab Switching
    # ---------------------------------------------------------
    page.goto(f"{BASE_URL}/ai/tools")
    expect(page.locator("h1").filter(has_text="檔案自動化").first).to_be_visible()
    expect(page.locator("aside")).to_contain_text("檔案自動化")

    # Switch to Invoice tab
    page.locator("#tab-btn-invoice").click()
    expect(page.locator("#ai-tab-invoice")).not_to_have_class(re.compile(r"hidden"))
    expect(page.locator("#ai-tab-bom")).to_have_class(re.compile(r"hidden"))

    # Switch to Reports tab
    page.locator("#tab-btn-reports").click()
    expect(page.locator("#ai-tab-reports")).not_to_have_class(re.compile(r"hidden"))
    expect(page.locator("#ai-tab-invoice")).to_have_class(re.compile(r"hidden"))

    # Switch back to BOM tab
    page.locator("#tab-btn-bom").click()
    expect(page.locator("#ai-tab-bom")).not_to_have_class(re.compile(r"hidden"))
    expect(page.locator("#ai-tab-reports")).to_have_class(re.compile(r"hidden"))

    # ---------------------------------------------------------
    # Scenario 2: BOM Excel Download, Upload & Price Comparison
    # ---------------------------------------------------------
    with page.expect_download() as download_info:
        page.get_by_role("link", name="下載 BOM 匯入範本 (.xlsx)").first.click()
    bom_download = download_info.value
    bom_path = tmp_path / "sample_bom.xlsx"
    bom_download.save_as(str(bom_path))
    assert bom_path.stat().st_size > 1000

    page.locator("#ai-tab-bom input[name='file']").set_input_files(str(bom_path))
    page.locator("#ai-tab-bom button:has-text('開始智慧比價')").click()

    bom_result = page.locator("#bom-result-container")
    expect(bom_result).to_contain_text("BOM 物料比價明細表", timeout=10000)
    expect(bom_result).to_contain_text("推薦供應商")
    expect(bom_result).to_contain_text("SKU-PRO-01")
    expect(bom_result).to_contain_text("SKU-ACC-02")
    expect(bom_result).to_contain_text("最低採購成本預估")
    expect(bom_result).to_contain_text("預估採購節省金額")

    # ---------------------------------------------------------
    # Scenario 3: Taiwan E-Invoice PDF Download, Parse & AP Creation
    # ---------------------------------------------------------
    inv_resp = page.request.get(f"{BASE_URL}/ai/invoice/sample-pdf")
    assert inv_resp.ok
    inv_path = tmp_path / "sample_invoice.pdf"
    inv_path.write_bytes(inv_resp.body())
    assert inv_path.stat().st_size > 500

    page.locator("#tab-btn-invoice").click()
    page.locator("#ai-tab-invoice input[name='file']").set_input_files(str(inv_path))
    page.locator("#ai-tab-invoice button:has-text('抽取發票資料')").click()

    inv_result = page.locator("#invoice-result-container")
    expect(inv_result).to_contain_text("AB-98765432", timeout=10000)
    expect(inv_result).to_contain_text("88888888")
    expect(inv_result).to_contain_text("12345678")
    expect(inv_result).to_contain_text("14,700")
    expect(inv_result).to_contain_text("14,000")
    expect(inv_result).to_contain_text("700")
    expect(inv_result).to_contain_text("金額勾稽吻合")

    # Click Confirm to create AP
    page.locator("#invoice-result-container button:has-text('確認無誤，建立應付帳款')").click()
    expect(inv_result).to_contain_text("應付帳款與會計分錄建立成功", timeout=10000)
    expect(inv_result).to_contain_text("AP-")

    # ---------------------------------------------------------
    # Scenario 5: Cross-verification with TanGii Accounting (Aging & Balance)
    # ---------------------------------------------------------
    # Navigate to accounting via the link in the confirmation card
    page.locator("a:has-text('前往探吉會計查閱')").click()
    expect(page.locator("h1").filter(has_text="探吉").first).to_be_visible()

    # Switch to Aging tab
    page.locator("a:has-text('應收/應付帳齡分析')").click()
    expect(page.locator("body")).to_contain_text("祥茂電子精密工業")
    expect(page.locator("body")).to_contain_text("14,700")
    expect(page.locator("body")).to_contain_text("沖銷付款")

    # Switch to Trial Balance tab
    page.locator("a:has-text('會計試算表')").click()
    expect(page.locator("body")).to_contain_text("借貸嚴格平衡")

    # ---------------------------------------------------------
    # Scenario 4: Executive Financial 4-in-1 Report Streaming Download
    # ---------------------------------------------------------
    page.goto(f"{BASE_URL}/ai/tools")
    page.locator("#tab-btn-reports").click()
    with page.expect_download() as rep_download_info:
        page.locator("a:has-text('匯出全套財務營運報表 (.xlsx)')").click()
    rep_download = rep_download_info.value
    assert re.search(r"3dollar_financial_executive_.*\.xlsx", rep_download.suggested_filename)

    rep_path = tmp_path / "report.xlsx"
    rep_download.save_as(str(rep_path))
    assert rep_path.stat().st_size > 2000

    # Verify 4 worksheets exist
    wb = openpyxl.load_workbook(str(rep_path), read_only=True)
    sheet_names = wb.sheetnames
    assert len(sheet_names) >= 4
    wb.close()

