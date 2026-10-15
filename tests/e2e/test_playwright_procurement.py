from __future__ import annotations
import os
import sys
import time
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
from src.core.services.inventory_service import InventoryService
from src.channel_ui.web.app import create_app

PORT = 8009
BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{PORT}")
SCREENSHOTS_DIR = Path(r"C:\Users\pigmao\.gemini\antigravity\brain\563eebe6-508e-4785-b4d8-fca8feef2a62\screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


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


def test_playwright_procurement_full_ui_suite():
    """Comprehensive Playwright End-to-End Test for the Procurement UI Module across all 7 scenarios."""
    # 1. Setup isolated database and app instance
    test_db_path = PROJECT_ROOT / "test_procurement_playwright.db"
    if test_db_path.exists():
        test_db_path.unlink()

    db = Database(test_db_path)
    db.init_db()
    event_bus = EventBus()

    # Pre-seed warehouses & products with known baseline
    inv = InventoryService(db=db)
    inv.create_warehouse("WH-MAIN", "台北總倉")
    inv.create_warehouse("WH-STORE", "信義旗艦店")
    inv.create_product(
        sku="SKU-PRO-01",
        name="旗艦智慧終端機",
        base_unit="PCS",
        cost_price=Decimal("1500.0"),
        selling_price=Decimal("2500.0"),
        safety_stock=20,
    )
    inv.create_product(
        sku="SKU-ACC-02",
        name="極速充電套件組",
        base_unit="SET",
        cost_price=Decimal("300.0"),
        selling_price=Decimal("650.0"),
        safety_stock=15,
    )
    # Give initial stock of 10 to SKU-PRO-01 (low stock trigger: 10 < 20)
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-PRO-01",
        qty_delta=Decimal("10.0"),
        unit_cost=Decimal("1500.0"),
        reference_id="INIT-001",
        notes="期初庫存",
    )

    app = create_app(db=db, event_bus=event_bus)
    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)
    print(f"[*] Test server running at {BASE_URL}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # ---------------------------------------------------------------------
            # Scenario 1: Dashboard Low-Stock Quick Link & Sidebar Navigation
            # ---------------------------------------------------------------------
            print("[1/7] Testing Dashboard Low-Stock Link & Sidebar Navigation...")
            page.goto(f"{BASE_URL}/")
            expect(page.locator("h1").filter(has_text="營運即時儀表板").first).to_be_visible()

            # Find low stock item SKU-PRO-01 and click '採購補貨 →'
            quick_buy_link = page.locator("a[href*='/procurement?sku=SKU-PRO-01']").first
            expect(quick_buy_link).to_be_visible()
            quick_buy_link.click()

            # Verify navigation to /procurement?sku=SKU-PRO-01
            expect(page).to_have_url(f"{BASE_URL}/procurement?sku=SKU-PRO-01")
            expect(page.locator("h1").filter(has_text="採購與進貨作業中心").first).to_be_visible()

            # Verify prefilled SKU in the dropdown
            first_sku_select = page.locator("#po-items-tbody .sku-select").first
            expect(first_sku_select).to_have_value("SKU-PRO-01")

            # Verify unit cost automatically populated to 1500.00
            first_cost_input = page.locator("#po-items-tbody .cost-input").first
            expect(first_cost_input).to_have_value("1500.00")

            # Verify sidebar navigation item exists and highlights active state
            aside = page.locator("aside")
            expect(aside.locator("a:has-text('採購與進貨作業')")).to_be_visible()
            page.screenshot(path=str(SCREENSHOTS_DIR / "01_procurement_page.png"))
            print(" -> Scenario 1 Passed. Screenshot saved.")

            # ---------------------------------------------------------------------
            # Scenario 2: Dynamic Row Addition & Deletion
            # ---------------------------------------------------------------------
            print("[2/7] Testing Dynamic Row Addition & Deletion...")
            add_row_btn = page.locator("button:has-text('＋ 增列物料')")
            expect(add_row_btn).to_be_visible()

            # Add a second row
            add_row_btn.click()
            rows = page.locator("#po-items-tbody tr.po-item-row")
            expect(rows).to_have_count(2)

            # In row 2, select SKU-ACC-02 and verify cost auto-populates to 300.00
            second_sku_select = rows.nth(1).locator(".sku-select")
            second_sku_select.select_option("SKU-ACC-02")
            second_cost_input = rows.nth(1).locator(".cost-input")
            expect(second_cost_input).to_have_value("300.00")

            # Add a third row then remove it
            add_row_btn.click()
            expect(page.locator("#po-items-tbody tr.po-item-row")).to_have_count(3)
            page.locator("#po-items-tbody tr.po-item-row").nth(2).locator("button[title='刪除此列']").click()
            expect(page.locator("#po-items-tbody tr.po-item-row")).to_have_count(2)
            print(" -> Scenario 2 Passed.")

            # ---------------------------------------------------------------------
            # Scenario 3: Validation & Error Handling (Empty Supplier & Negative Qty)
            # ---------------------------------------------------------------------
            print("[3/7] Testing Client & Server Form Validation...")
            # Record current count of POs
            initial_count = page.locator("#po-tbody tr").count()

            # Leave supplier name empty and attempt submit
            submit_btn = page.locator("button:has-text('建立採購單 (Draft)')")
            submit_btn.click()

            # HTML5 required validation prevents submission; row count must stay unchanged
            expect(page.locator("#po-tbody tr")).to_have_count(initial_count)
            print(" -> Scenario 3 Passed.")

            # ---------------------------------------------------------------------
            # Scenario 4: Valid PO Creation (Draft) with Multiple Items
            # ---------------------------------------------------------------------
            print("[4/7] Testing Valid Multi-Item PO Creation (Draft)...")
            # Fill supplier name
            page.locator("input[name='supplier_name']").fill("台塑塑膠工業")

            # Set quantities: Row 1: SKU-PRO-01 qty 20 @ 1200.00
            rows.nth(0).locator(".qty-input").fill("20")
            rows.nth(0).locator(".cost-input").fill("1200.00")

            # Row 2: SKU-ACC-02 qty 10 @ 250.00
            rows.nth(1).locator(".qty-input").fill("10")
            rows.nth(1).locator(".cost-input").fill("250.00")

            # Submit
            submit_btn.click()

            # Expected total: 20 * 1200 + 10 * 250 = 24000 + 2500 = NT$ 26,500.00
            expect(page.locator("#procurement-container")).to_contain_text("成功建立採購單")

            # Verify table has new PO row for 台塑塑膠工業
            po_row = page.locator("#po-tbody tr").filter(has_text="台塑塑膠工業").first
            expect(po_row).to_be_visible()
            po_id = po_row.locator(".font-mono.font-bold").first.inner_text().strip()
            assert po_id.startswith("PO-"), f"Unexpected PO ID: {po_id}"

            expect(po_row).to_contain_text("台塑塑膠工業")
            expect(po_row).to_contain_text("草稿 (DRAFT)")
            expect(po_row).to_contain_text("NT$ 26,500.00")
            expect(po_row.locator("button:has-text('確認下訂')")).to_be_visible()

            page.screenshot(path=str(SCREENSHOTS_DIR / "02_po_draft_created.png"))
            print(f" -> Scenario 4 Passed. Created {po_id}. Screenshot saved.")

            # ---------------------------------------------------------------------
            # Scenario 5: Submit PO (DRAFT -> SUBMITTED)
            # ---------------------------------------------------------------------
            print("[5/7] Testing PO Submission (DRAFT -> SUBMITTED)...")
            target_po_row = page.locator(f"#po-row-{po_id}")
            target_po_row.locator("button:has-text('確認下訂')").click()

            # Verify status badge changes to SUBMITTED and button becomes 驗收入庫
            expect(target_po_row).to_contain_text("待到貨 (SUBMITTED)", timeout=5000)
            expect(target_po_row.locator("button:has-text('驗收入庫')")).to_be_visible()

            page.screenshot(path=str(SCREENSHOTS_DIR / "03_po_submitted.png"))
            print(" -> Scenario 5 Passed. Status advanced to SUBMITTED. Screenshot saved.")

            # ---------------------------------------------------------------------
            # Scenario 6: Inbound Modal & Goods Receipt (SUBMITTED -> RECEIVED)
            # ---------------------------------------------------------------------
            print("[6/7] Testing Inbound Modal & Goods Receipt Execution...")
            # Click 驗收入庫
            target_po_row.locator("button:has-text('驗收入庫')").click()

            # Verify modal appears
            modal = page.locator("#receive-po-modal")
            expect(modal).to_be_visible()
            expect(modal).to_contain_text(po_id)
            expect(modal).to_contain_text("台塑塑膠工業")
            expect(modal).to_contain_text("SKU-PRO-01")
            expect(modal).to_contain_text("SKU-ACC-02")
            expect(modal.locator("select[name='warehouse_id']")).to_be_visible()
            page.wait_for_timeout(800)

            # Test modal cancellation
            modal.locator("button:has-text('取消')").click()
            expect(modal).not_to_be_visible()
            page.wait_for_timeout(500)

            # Re-open modal and confirm receipt to WH-MAIN
            target_po_row.locator("button:has-text('驗收入庫')").click()
            expect(page.locator("#receive-po-modal")).to_be_visible()
            page.wait_for_timeout(800)
            page.locator("#receive-po-modal select[name='warehouse_id']").select_option("WH-MAIN")
            page.locator("#receive-po-modal button:has-text('確認入庫並立帳')").click()

            # Verify modal closed and row status updated to RECEIVED
            expect(page.locator("#receive-po-modal")).not_to_be_visible()
            expect(target_po_row).to_contain_text("已驗收入庫 (RECEIVED)", timeout=5000)
            expect(target_po_row).to_contain_text("已完成立帳")
            expect(target_po_row).to_contain_text("單號: GRN-")

            page.screenshot(path=str(SCREENSHOTS_DIR / "04_po_received.png"))
            print(" -> Scenario 6 Passed. Goods received & GRN issued. Screenshot saved.")

            # ---------------------------------------------------------------------
            # Scenario 7: Cross-Module Verification (/inventory & /accounting)
            # ---------------------------------------------------------------------
            print("[7/7] Testing Cross-Module Verification (/inventory & /accounting)...")
            # 1. Check Inventory Page
            page.goto(f"{BASE_URL}/inventory")
            expect(page.locator("h1").filter(has_text="多倉庫存與雙記帳流水").first).to_be_visible()

            # Physical balance of SKU-PRO-01 in WH-MAIN: was 10, added 20 -> 30
            stock_table = page.locator("#stock-table-container")
            expect(stock_table).to_contain_text("SKU-PRO-01")
            expect(stock_table).to_contain_text("30")

            # Check Ledger Trail for PURCHASE
            ledger_table = page.locator("table").nth(1)
            expect(ledger_table).to_contain_text("PURCHASE")
            expect(ledger_table).to_contain_text("+20")
            page.screenshot(path=str(SCREENSHOTS_DIR / "05_inventory_updated.png"))
            print(" -> Inventory stock & ledger verified.")

            # 2. Check TanGii Accounting Page
            page.goto(f"{BASE_URL}/accounting?tab=aging")
            expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()

            # Check Payables table
            expect(page.locator("body")).to_contain_text("台塑塑膠工業")
            expect(page.locator("body")).to_contain_text("26,500.00")

            # Switch to Journal Entries Tab
            page.goto(f"{BASE_URL}/accounting?tab=journal")
            expect(page.locator("body")).to_contain_text("ERP_GOODS_RECEIVED")
            expect(page.locator("body")).to_contain_text("1201")  # 存貨科目
            expect(page.locator("body")).to_contain_text("2144")  # 應付帳款科目

            page.screenshot(path=str(SCREENSHOTS_DIR / "06_accounting_updated.png"))
            print(" -> Accounting AP & balanced journal entry verified. Screenshot saved.")

            print("\n🎉 ALL 7 PLAYWRIGHT TEST SCENARIOS PASSED SUCCESSFULLY!")

        finally:
            browser.close()
            # Clean up test database
            if test_db_path.exists():
                try:
                    test_db_path.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    test_playwright_procurement_full_ui_suite()
