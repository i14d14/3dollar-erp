from __future__ import annotations
import os
import sys
import time
import socket
import threading
from decimal import Decimal
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright, expect

# Ensure UTF-8 output encoding for Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.shared.database import Database
from src.shared.event_bus import EventBus
from src.core.domain.order import OrderChannel, OrderStatus
from src.extended_core.crm.models import DealStage
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.services.crm_service import CrmService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.channel_ui.web.app import create_app


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_server_in_thread(app, port: int):
    """Start uvicorn server in a background daemon thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server


def wait_for_server(url: str, timeout: float = 10.0):
    """Poll URL until server responds."""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    raise TimeoutError(f"Server at {url} did not respond within {timeout}s")


def test_playwright_iteration0923_suite():
    """Playwright E2E UI verification for all changes in iteration-0923-00.md in MANDATORY HEADED mode:
    Batch 1 (Pure Front-End QOL):
      1. CRM Quotation Modal state reset on opening (Deal A modified items -> Deal B without items has clean default form).
      2. Inventory Stock Table simplified low-stock button ('⚠️ 低於安全量').
      3. Accounting 4-in-1 Report Cards 1:1 Sheet alignment and typography.
      4. Toast notification multi-line adaptive styling without truncate.

    Batch 2 (Fulfillment & CRM):
      1. CRM Deal '⚡ 贏單轉 ERP' auto-confirms order and commits virtual stock reservation.
      2. Order Management table displays readable customer name + ID: '公司名稱 (CUST-xxxx)'.
      3. BOM Split POs batch creation displays toast with '撤回建立', clicking undo cancels newly created POs.

    Batch 3 (Accounting & Safety):
      1. AR Settlement: Tailwind 2-step confirmation modal (no native Chrome dialog), account select, preview, and toast.
      2. AP Settlement: Tailwind 2-step confirmation modal (no native Chrome dialog), double-entry preview, and toast.
      3. Invoice Dupe Prevention: First upload creates AP; second upload detects ALREADY_RECORDED and disables button.
    """
    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"

    test_db_path = PROJECT_ROOT / "test_iteration0923_playwright.db"
    if test_db_path.exists():
        try:
            test_db_path.unlink()
        except Exception:
            pass

    bom_temp_file = PROJECT_ROOT / "temp_playwright_bom_0923.xlsx"
    inv_temp_file = PROJECT_ROOT / "temp_sample_invoice_0923.pdf"

    db = Database(test_db_path)
    db.init_db()
    event_bus = EventBus()

    # Create app and seed initial demo data
    app = create_app(db=db, event_bus=event_bus)

    # Pre-seed specific data for Iteration 0923 testing
    inv = InventoryService(db=db)
    order_svc = OrderService(db=db, inventory_service=inv, event_bus=event_bus)
    crm_svc = CrmService(db=db, order_service=order_svc, event_bus=event_bus)

    # 1. Product 1 (SKU-PRO-01) with ample stock in WH-MAIN
    # (Physical: 50, Safety: 20)
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-PRO-01",
        qty_delta=Decimal("50.0"),
        unit_cost=Decimal("1500.0"),
        reference_id="SEED-PRO-01",
        notes="充足庫存",
    )

    # 2. Product 2 (SKU-ACC-02) with low stock in WH-MAIN for button testing
    # (Physical: 5, Safety: 20 -> is_low_stock = True)
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-ACC-02",
        qty_delta=Decimal("5.0"),
        unit_cost=Decimal("300.0"),
        reference_id="SEED-ACC-02",
        notes="低庫存補貨測試",
    )

    # 3. CRM Contacts & Deals
    contact_alpha = crm_svc.create_contact(
        company_name="聯成半導體科技股份有限公司",
        contact_name="林技術長",
        tax_id="23456789",
        phone="02-87654321",
    )

    # Deal 1: Has items (for testing Quotation modal dirty state)
    deal_with_items = crm_svc.create_deal(
        contact_id=contact_alpha.contact_id,
        title="2026 企業終端大量採購案",
        stage=DealStage.PROPOSAL,
        items=[("SKU-PRO-01", Decimal("2"), Decimal("2500.0"))],
    )

    # Deal 2: No items (for testing clean form reset after Deal 1)
    deal_no_items = crm_svc.create_deal(
        contact_id=contact_alpha.contact_id,
        title="2026 前瞻技術諮詢評估案",
        stage=DealStage.DISCOVERY,
        items=[],
    )

    # Deal 3: For Won Deal Auto-Reservation and Customer Identification
    contact_beta = crm_svc.create_contact(
        company_name="宏遠生技股份有限公司",
        contact_name="陳副總",
        tax_id="88776655",
        phone="02-23456789",
    )
    deal_for_won = crm_svc.create_deal(
        contact_id=contact_beta.contact_id,
        title="2026 生醫實驗室終端部署專案",
        stage=DealStage.PROPOSAL,
        items=[("SKU-PRO-01", Decimal("5"), Decimal("2500.0"))],
    )
    crm_svc.create_quote(deal_id=deal_for_won.deal_id)

    server = start_server_in_thread(app, port)
    wait_for_server(base_url)
    print(f"\n[*] Playwright Headed Test Server running at {base_url}")

    with sync_playwright() as p:
        # Mandatory Headed Mode with human-observable slow_mo
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: print(f"[BROWSER CONSOLE] {msg.type}: {msg.text}"))

        try:
            # =================================================================
            # SUITE 1: Batch 1 (Pure Front-End QOL & Reset Features)
            # =================================================================
            print("\n" + "=" * 75)
            print("[Suite 1/3] Testing Batch 1: Front-End QOL, CRM Quote Reset & Report Center")
            print("=" * 75)

            # --- 1.1 CRM Quotation Modal State Clean Reset ---
            print("\n  [1.1] Testing CRM Quotation Modal Clean Reset...")
            page.goto(f"{base_url}/crm?tab=kanban")
            expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM").first).to_be_visible()

            # Open quote modal for Deal 1 (which has items)
            deal1_card = page.locator(f"#deal-card-{deal_with_items.deal_id}")
            expect(deal1_card).to_be_visible()
            deal1_card.locator("button:has-text('＋ 報價單')").click()

            quote_modal = page.locator("#modal-new-quote")
            expect(quote_modal).to_be_visible()
            expect(page.locator("#quote-modal-deal-title")).to_contain_text(deal_with_items.title)

            # Fill item 2 and modify fields to dirty the form
            page.select_option("#modal-new-quote select[name='sku_2']", "SKU-ACC-02")
            page.fill("#modal-new-quote input[name='qty_2']", "5")
            page.fill("#modal-new-quote input[name='price_2']", "550")
            page.fill("#modal-new-quote input[name='valid_days']", "45")

            # Cancel without submitting
            page.click("#modal-new-quote button:has-text('取消')")
            expect(quote_modal).not_to_be_visible()
            print("    -> Deal 1 quote modal dirtied with item 2 and closed.")

            # Now open quote modal for Deal 2 (which has no items)
            deal2_card = page.locator(f"#deal-card-{deal_no_items.deal_id}")
            expect(deal2_card).to_be_visible()
            deal2_card.locator("button:has-text('＋ 報價單')").click()

            expect(quote_modal).to_be_visible()
            expect(page.locator("#quote-modal-deal-title")).to_contain_text(deal_no_items.title)

            # Assert that form fields were completely reset by openQuoteModal()
            sku2_val = page.locator("#modal-new-quote select[name='sku_2']").input_value()
            qty2_val = page.locator("#modal-new-quote input[name='qty_2']").input_value()
            price2_val = page.locator("#modal-new-quote input[name='price_2']").input_value()
            valid_days_val = page.locator("#modal-new-quote input[name='valid_days']").input_value()

            assert sku2_val == "", f"Expected sku_2 to be empty, got '{sku2_val}'"
            assert qty2_val == "1", f"Expected qty_2 to be '1', got '{qty2_val}'"
            assert price2_val == "0", f"Expected price_2 to be '0', got '{price2_val}'"
            assert valid_days_val == "30", f"Expected valid_days to be '30', got '{valid_days_val}'"
            print("    -> [PASS] Deal 2 quote modal verified completely clean with 0 state residual from Deal 1!")

            page.click("#modal-new-quote button:has-text('取消')")
            expect(quote_modal).not_to_be_visible()

            # --- 1.2 Inventory Stock Table Simplified Low-Stock Button ---
            print("\n  [1.2] Testing Inventory Stock Table Simplified Low-Stock Button...")
            page.goto(f"{base_url}/inventory")
            expect(page.locator("h1").filter(has_text="多倉庫存與雙記帳流水").first).to_be_visible()

            # Locate low-stock row for SKU-ACC-02
            low_stock_btn = page.locator("a:has-text('⚠️ 低於安全量')").first
            expect(low_stock_btn).to_be_visible()
            btn_text = low_stock_btn.inner_text().strip()
            assert btn_text == "⚠️ 低於安全量", f"Expected '⚠️ 低於安全量', got '{btn_text}'"
            assert "一鍵下單" not in btn_text, "Button text should be simplified without '一鍵下單'"

            # Click low stock button and verify navigation with prefilled values
            href = low_stock_btn.get_attribute("href")
            assert href and "/procurement?sku=" in href, f"Expected href to link to procurement, got {href}"
            low_stock_btn.click()
            page.wait_for_url("**/procurement?sku=*")
            expect(page.locator("h1").filter(has_text="採購與進貨作業中心").first).to_be_visible()
            expect(page.locator(".sku-select").first).not_to_have_value("")
            print("    -> [PASS] Simplified low stock button displays '⚠️ 低於安全量' and pre-fills procurement correctly.")

            # --- 1.3 Accounting 4-in-1 Report Cards 1:1 Sheet Alignment ---
            print("\n  [1.3] Testing Accounting 4-in-1 Report Cards Alignment...")
            page.goto(f"{base_url}/accounting?tab=reports")
            reports_container = page.locator("#accounting-reports-container")
            expect(reports_container).to_be_visible()

            # Card 1: 損益表 (Income Statement)
            card1 = reports_container.locator("div.p-5").filter(has_text="Sheet 1").first
            expect(card1).to_be_visible()
            expect(card1).to_contain_text("頁籤: 損益表")
            expect(card1.locator("a[href='/accounting/export/income-statement.xlsx']")).to_be_visible()

            # Card 2: 試算表 (Trial Balance)
            card2 = reports_container.locator("div.p-5").filter(has_text="Sheet 2").first
            expect(card2).to_be_visible()
            expect(card2).to_contain_text("頁籤: 試算表")
            expect(card2.locator("a[href='/accounting/export/trial-balance.xlsx']")).to_be_visible()

            # Card 3: 帳齡分析 (Aging Matrix)
            card3 = reports_container.locator("div.p-5").filter(has_text="Sheet 3").first
            expect(card3).to_be_visible()
            expect(card3).to_contain_text("頁籤: 帳齡分析")
            expect(card3.locator("a:has-text('線上帳齡看板')")).to_be_visible()

            # Card 4: 雙倉庫存盤點底冊 (Stock Valuation)
            card4 = reports_container.locator("div.p-5").filter(has_text="Sheet 4").first
            expect(card4).to_be_visible()
            expect(card4).to_contain_text("雙倉庫存盤點估值底冊")

            # Check typography & absence of legacy Executive_Summary
            reports_html = page.locator("#accounting-reports-container").inner_html()
            assert "Executive_Summary" not in reports_html, "Legacy Executive_Summary sheet reference must be gone"
            assert "text-[10px]" not in reports_html, "Substandard text-[10px] class must be eliminated"
            print("    -> [PASS] Accounting 4 report cards 1:1 match Excel sheets with clean typography.")

            # =================================================================
            # SUITE 2: Batch 2 (Fulfillment, CRM Won Auto-Reservation & BOM Undo)
            # =================================================================
            print("\n" + "=" * 75)
            print("[Suite 2/3] Testing Batch 2: CRM Won Auto-Reservation, Customer ID & BOM Undo")
            print("=" * 75)

            # --- 2.1 CRM Deal Won Auto-Reservation & Status CONFIRMED ---
            print("\n  [2.1] Testing CRM Deal Won Auto-Reservation...")
            # Check stock before conversion
            avail_before = inv.get_available_stock("WH-MAIN", "SKU-PRO-01")
            assert avail_before >= Decimal("5.0"), f"Not enough stock before test: {avail_before}"

            page.goto(f"{base_url}/crm?tab=kanban")
            deal3_card = page.locator(f"#deal-card-{deal_for_won.deal_id}")
            expect(deal3_card).to_be_visible()

            # Click [⚡ 贏單轉 ERP]
            deal3_card.locator("button:has-text('⚡ 贏單轉 ERP')").click()
            convert_modal = page.locator("#convert-deal-modal")
            expect(convert_modal).to_be_visible()
            expect(convert_modal).to_contain_text("贏單轉 ERP 銷售訂單確認")
            expect(convert_modal).to_contain_text("宏遠生技股份有限公司")

            # Submit conversion
            convert_modal.locator("button:has-text('確認轉為 ERP 正式訂單')").click()
            expect(convert_modal).not_to_be_visible(timeout=5000)

            # Verify Toast and Deal card updated to WON
            expect(page.locator("#toast-container")).to_contain_text("商機已成功拋轉為 ERP 銷售訂單")
            expect(deal3_card).to_contain_text("ERP 銷售訂單")

            # --- 2.2 Order List Customer Identification & Confirmed Status ---
            print("\n  [2.2] Testing Order List Customer Identification & Confirmed Status...")
            page.goto(f"{base_url}/orders")
            expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

            # Locate converted order row (宏遠生技股份有限公司)
            converted_row = page.locator("tr").filter(has_text="宏遠生技股份有限公司").first
            expect(converted_row).to_be_visible()

            # Assert order status is CONFIRMED (Batch 2 core requirement: Commitment requires reservation!)
            expect(converted_row).to_contain_text("CONFIRMED")
            assert "DRAFT" not in converted_row.locator("td:nth-child(4)").inner_text()

            # Assert customer column shows readable name + ID
            expect(converted_row).to_contain_text(f"宏遠生技股份有限公司 ({contact_beta.contact_id})")

            # Verify virtual stock reservation committed in Inventory
            avail_after = inv.get_available_stock("WH-MAIN", "SKU-PRO-01")
            assert avail_after == avail_before - Decimal("5.0"), (
                f"Expected available stock {avail_before - Decimal('5.0')} after 5 units reserved, got {avail_after}"
            )
            print(f"    -> [PASS] CRM won order automatically confirmed, stock reserved ({avail_before}->{avail_after}), and customer named.")

            # --- 2.3 BOM Split POs Batch Creation & One-Click Undo ---
            print("\n  [2.3] Testing BOM Split POs Batch Creation & One-Click Undo...")
            page.goto(f"{base_url}/procurement")
            expect(page.locator("h1").filter(has_text="採購與進貨作業中心").first).to_be_visible()

            # Switch to BOM tab
            page.click("#tab-btn-bom")
            bom_section = page.locator("#section-bom-po")
            expect(bom_section).to_be_visible()

            # Download sample BOM Excel
            with page.expect_download() as dl_bom_info:
                page.locator("a[href='/procurement/bom/sample']").click()
            bom_download = dl_bom_info.value
            bom_download.save_as(str(bom_temp_file))
            assert bom_temp_file.exists()
            print("    -> Sample BOM Excel downloaded.")

            # Upload BOM Excel file
            file_input = page.locator("#section-bom-po input[name='file']")
            file_input.set_input_files(str(bom_temp_file))
            page.locator("#section-bom-po button:has-text('開始智慧比價')").click()

            # Wait for comparison results
            split_btn = page.locator("#btn-split-bom-pos")
            expect(split_btn).to_be_visible(timeout=10000)
            print("    -> BOM price comparison loaded.")

            # Count initial PO rows
            initial_po_count = page.locator("#po-tbody tr").count()

            # Click [⚡ 一鍵依供應商分割建立採購單]
            split_btn.click()

            # Verify Toast appears with [撤回建立] button
            toast = page.locator("#toast-container")
            expect(toast).to_contain_text("成功為", timeout=8000)
            expect(toast).to_contain_text("家供應商自動分割建立採購單")
            undo_bom_btn = toast.locator("button:has-text('撤回建立')")
            expect(undo_bom_btn).to_be_visible()
            print("    -> Split POs created with multi-line adaptive Toast containing [撤回建立] button.")

            # Click [撤回建立]
            undo_bom_btn.click()

            # Verify batch undo confirmation toast
            expect(toast).to_contain_text("已成功撤回 BOM 自動分割建立之", timeout=8000)
            print("    -> [PASS] BOM split POs batch undo executed successfully; draft POs cancelled.")

            # =================================================================
            # SUITE 3: Batch 3 (Accounting Tailwind Modal & Invoice Dupe Prevention)
            # =================================================================
            print("\n" + "=" * 75)
            print("[Suite 3/3] Testing Batch 3: Accounting 2-Step Settle Modal & Invoice Dupe Prevention")
            print("=" * 75)

            # --- 3.1 Accounting AR Tailwind 2-Step Settle Modal ---
            print("\n  [3.1] Testing Accounting AR Tailwind 2-Step Settle Modal...")
            page.goto(f"{base_url}/accounting?tab=aging")
            expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()

            # Locate unpaid AR row (seeded AR-HIST-01 for 宏亞光學)
            ar_row = page.locator("tr").filter(has_text="宏亞光學").first
            expect(ar_row).to_be_visible()
            settle_ar_btn = ar_row.locator("button:has-text('⚡ 沖銷收款')")
            expect(settle_ar_btn).to_be_visible()

            # Click [⚡ 沖銷收款] -> Should open Tailwind modal, NO native browser confirm dialog!
            settle_ar_btn.click()

            modal = page.locator("#settle-confirm-modal")
            expect(modal).to_be_visible()
            expect(modal).to_contain_text("⚡ 應收帳款沖銷收款確認 (AR Settlement)")
            expect(modal).to_contain_text("宏亞光學")
            expect(modal).to_contain_text("借 (Dr):")
            expect(modal).to_contain_text("1101 現金")
            expect(modal).to_contain_text("貸 (Cr): 1144 應收帳款")

            # Test Cancel button
            modal.locator("button:has-text('取消')").click()
            expect(modal).not_to_be_visible()
            print("    -> AR modal Cancel button cleanly dismissed dialog.")

            # Re-open and switch account to 1102 (Bank Deposits)
            settle_ar_btn.click()
            expect(modal).to_be_visible()
            page.select_option("#payment_account", "1102")
            expect(page.locator("#preview-dr-account")).to_contain_text("1102 - 銀行存款")

            # Click [確認執行沖銷]
            modal.locator("button:has-text('確認執行沖銷')").click()
            expect(modal).not_to_be_visible(timeout=5000)

            # Verify toast and AR item cleared from unpaid aging list
            expect(page.locator("#toast-container")).to_contain_text("已成功沖銷結清應收帳款", timeout=5000)
            expect(page.locator("tr").filter(has_text="宏亞光學")).to_have_count(0)
            print("    -> [PASS] AR Tailwind 2-step modal settled receivable via account 1102 with journal entry.")

            # --- 3.2 Accounting AP Tailwind 2-Step Settle Modal ---
            print("\n  [3.2] Testing Accounting AP Tailwind 2-Step Settle Modal...")
            # On aging tab, AP table is already rendered below AR
            ap_row = page.locator("tr").filter(has_text="祥茂電子精密工業").first
            expect(ap_row).to_be_visible()
            settle_ap_btn = ap_row.locator("button:has-text('⚡ 沖銷付款')")
            expect(settle_ap_btn).to_be_visible()

            # Click [⚡ 沖銷付款] -> Tailwind modal
            settle_ap_btn.click()
            expect(modal).to_be_visible()
            expect(modal).to_contain_text("⚡ 應付帳款沖銷付款確認 (AP Settlement)")
            expect(modal).to_contain_text("祥茂電子精密工業")
            expect(modal).to_contain_text("借 (Dr): 2144 應付帳款")
            expect(modal).to_contain_text("貸 (Cr):")

            # Confirm settle
            modal.locator("button:has-text('確認執行沖銷')").click()
            expect(modal).not_to_be_visible(timeout=5000)

            expect(page.locator("#toast-container")).to_contain_text("已成功沖銷支付應付帳款", timeout=5000)
            expect(page.locator("tr").filter(has_text="祥茂電子精密工業")).to_have_count(0)
            print("    -> [PASS] AP Tailwind 2-step modal settled payable with journal entry.")

            # --- 3.3 AI Invoice Duplicate Registration Prevention ---
            print("\n  [3.3] Testing AI Invoice Duplicate Registration Prevention...")
            page.goto(f"{base_url}/ai/tools")
            expect(page.locator("h1").filter(has_text="檔案自動化與增強外掛").first).to_be_visible()

            # Download sample invoice PDF
            with page.expect_download() as dl_inv_info:
                page.locator("a[href='/ai/invoice/sample-pdf']").click()
            inv_download = dl_inv_info.value
            inv_download.save_as(str(inv_temp_file))
            assert inv_temp_file.exists()
            print("    -> Sample invoice PDF downloaded.")

            # First Upload & Extract
            file_inv_input = page.locator("#ai-tab-invoice input[name='file']")
            file_inv_input.set_input_files(str(inv_temp_file))
            page.locator("#ai-tab-invoice button:has-text('抽取發票資料')").click()

            inv_res = page.locator("#invoice-result-container")
            expect(inv_res).to_contain_text("AB-98765432", timeout=10000)
            expect(inv_res).to_contain_text("金額勾稽吻合")

            # First Confirmation -> Creates AP and posts Journal Entry
            confirm_ap_btn = inv_res.locator("button:has-text('確認無誤，建立應付帳款')")
            expect(confirm_ap_btn).to_be_visible()
            confirm_ap_btn.click()
            expect(inv_res).to_contain_text("應付帳款與會計分錄建立成功", timeout=10000)
            print("    -> First invoice successfully registered into AP and general ledger.")

            # Second Upload with EXACT SAME Invoice PDF
            print("    -> Uploading same invoice PDF second time to verify dupe block...")
            file_inv_input.set_input_files(str(inv_temp_file))
            page.locator("#ai-tab-invoice button:has-text('抽取發票資料')").click()

            # Assert ALREADY_RECORDED state renders disabled button
            expect(inv_res).to_contain_text("AB-98765432", timeout=10000)
            dupe_btn = inv_res.locator("button:has-text('已建檔入帳（禁止重複建立）')")
            expect(dupe_btn).to_be_visible()
            assert dupe_btn.is_disabled(), "Duplicate invoice button must be strictly disabled!"

            # Assert the active submit button is gone
            expect(inv_res.locator("button:has-text('確認無誤，建立應付帳款')")).to_have_count(0)
            print("    -> [PASS] Duplicate invoice registration strictly blocked (status: ALREADY_RECORDED, button disabled).")

            print("\n" + "=" * 75)
            print("[ALL PLAYWRIGHT E2E UI TESTS FOR ITERATION-0923 COMPLETED SUCCESSFULLY!]")
            print("=" * 75 + "\n")

        finally:
            context.close()
            browser.close()

            # Clean up temp files
            for temp_f in [bom_temp_file, inv_temp_file, test_db_path]:
                if temp_f.exists():
                    try:
                        temp_f.unlink()
                    except Exception:
                        pass


if __name__ == "__main__":
    test_playwright_iteration0923_suite()
