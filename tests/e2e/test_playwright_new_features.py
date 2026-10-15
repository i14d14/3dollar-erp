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
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.services.crm_service import CrmService
from src.channel_ui.web.app import create_app

PORT = 8012
BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{PORT}")


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


def test_playwright_all_new_features():
    """Playwright E2E UI verification for all new requested features in HEADED mode:
    1. Dashboard: low stock restock button pre-fills procurement form.
    2. Procurement: BOM comparison tab and one-click multi-supplier split POs.
    3. Inventory: dynamic warehouse names in transfer dropdown and one-click purchase button.
    4. Accounting: MathJax formula rendering and 4-in-1 executive financial report center.
    5. CRM: multi-item deal creation with dynamic pricing and quotation auto-inheritance.
    """
    bom_excel_path = None
    financial_report_path = None

    test_db_path = PROJECT_ROOT / "test_features_playwright.db"
    if test_db_path.exists():
        try:
            test_db_path.unlink()
        except Exception:
            pass

    db = Database(test_db_path)
    db.init_db()
    event_bus = EventBus()

    # Pre-seed inventory & products
    inv = InventoryService(db=db)
    inv.create_warehouse("WH-MAIN", "台北總部主倉")
    inv.create_warehouse("WH-STORE", "信義實體門市倉")
    inv.create_product(
        sku="SKU-PRO-01",
        name="旗艦智慧終端機",
        base_unit="PCS",
        cost_price=Decimal("1500.0"),
        selling_price=Decimal("2500.0"),
        safety_stock=10,
    )
    inv.create_product(
        sku="SKU-ACC-02",
        name="極速充電套件組",
        base_unit="SET",
        cost_price=Decimal("300.0"),
        selling_price=Decimal("650.0"),
        safety_stock=5,
    )

    # Pre-seed a historical purchase order to establish supplier quote history
    proc = ProcurementService(db=db, event_bus=event_bus)
    proc.create_purchase_order(
        supplier_name="祥茂電子精密工業",
        items=[("SKU-PRO-01", Decimal("10"), Decimal("1400.0"))],
    )
    proc.create_purchase_order(
        supplier_name="宏碁零組件供應商",
        items=[("SKU-ACC-02", Decimal("10"), Decimal("280.0"))],
    )

    # Seed CRM contact
    order_service = OrderService(db=db, event_bus=event_bus, inventory_service=inv)
    crm_service = CrmService(db=db, order_service=order_service, event_bus=event_bus)
    contact = crm_service.create_contact(
        company_name="聯成半導體科技股份有限公司",
        contact_name="林技術長",
        tax_id="23456789",
        phone="02-87654321",
    )

    app = create_app(db=db, event_bus=event_bus)
    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)
    print(f"[*] Playwright test server running at {BASE_URL}")

    with sync_playwright() as p:
        # Mandatory Headed Mode
        browser = p.chromium.launch(headless=False, slow_mo=350)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # -----------------------------------------------------------------
            # 1. Dashboard: Low stock alert & Pre-filled Procurement Form
            # -----------------------------------------------------------------
            print("\n[Scenario 1/5] Testing Dashboard Low Stock Pre-fill to Procurement Form...")
            page.goto(f"{BASE_URL}/")
            expect(page.locator("h1").filter(has_text="營運即時儀表板").first).to_be_visible()

            # Verify low stock alert box exists
            low_stock_box = page.locator("text=低於安全存量商品清單").first
            expect(low_stock_box).to_be_visible()

            # Click the restock button on SKU-PRO-01
            restock_btn = page.locator("a[href*='/procurement?sku=SKU-PRO-01']").first
            expect(restock_btn).to_be_visible()
            restock_btn.click()

            # Verify page redirected to /procurement and form inputs are pre-filled
            page.wait_for_url("**/procurement*")
            expect(page.locator("#input-supplier-name")).to_have_value("祥茂電子精密工業")
            expect(page.locator("#select-target-warehouse")).to_have_value("WH-MAIN")
            expect(page.locator(".sku-select").first).to_have_value("SKU-PRO-01")
            expect(page.locator(".qty-input").first).to_have_value("10")
            expect(page.locator(".cost-input").first).to_have_value("1500.00")
            print("  -> Dashboard restock button successfully pre-filled supplier, warehouse, SKU, shortage qty, and unit cost!")

            # -----------------------------------------------------------------
            # 2. Procurement: BOM Comparison & One-Click Split POs
            # -----------------------------------------------------------------
            print("\n[Scenario 2/5] Testing BOM Comparison & One-Click Multi-Supplier Split POs...")
            # Switch to BOM Tab
            page.locator("#tab-btn-bom").click()
            expect(page.locator("#section-bom-po")).to_be_visible()

            # Download sample BOM
            with page.expect_download() as download_info:
                page.locator("a[href='/procurement/bom/sample']").click()
            download = download_info.value
            bom_excel_path = PROJECT_ROOT / "temp_procurement_bom.xlsx"
            download.save_as(str(bom_excel_path))
            assert bom_excel_path.exists()
            print(f"  -> Downloaded sample BOM Excel: {bom_excel_path.name}")

            # Upload the BOM Excel file
            file_input = page.locator("#section-bom-po input[name='file']")
            file_input.set_input_files(str(bom_excel_path))
            page.locator("#section-bom-po button:has-text('開始智慧比價')").click()

            # Verify comparison cards & table rendered
            expect(page.locator("#procurement-bom-result-container")).to_contain_text("BOM 清單總項數", timeout=10000)
            expect(page.locator("#procurement-bom-result-container")).to_contain_text("最低採購成本預估")
            expect(page.locator("#btn-split-bom-pos")).to_be_visible()
            print("  -> BOM comparison cards and multi-supplier breakdown loaded successfully.")

            # Click one-click split PO button
            page.locator("#btn-split-bom-pos").click()
            page.wait_for_timeout(1000)

            # Verify success message and multiple POs created in the PO stream table below
            expect(page.locator("#procurement-container")).to_contain_text("成功為", timeout=10000)
            expect(page.locator("#procurement-container")).to_contain_text("家供應商自動分割建立採購單")
            expect(page.locator("#po-tbody")).to_contain_text("祥茂電子精密工業")
            print("  -> Successfully created split POs by supplier and refreshed the PO ledger!")

            # -----------------------------------------------------------------
            # 3. Inventory: Dynamic Warehouse Names & One-Click Purchase
            # -----------------------------------------------------------------
            print("\n[Scenario 3/5] Testing Inventory Dynamic Warehouse Names & One-Click Restock...")
            page.goto(f"{BASE_URL}/inventory")
            expect(page.locator("h1").filter(has_text="多倉庫存與雙記帳流水").first).to_be_visible()

            # Verify warehouse names in transfer dropdowns
            from_select = page.locator("select[name='from_warehouse_id']")
            expect(from_select).to_contain_text("台北總部主倉")
            expect(from_select).to_contain_text("信義實體門市倉")

            # Verify low stock row has 一鍵下單 button
            one_click_btn = page.locator("a:has-text('一鍵下單')").first
            expect(one_click_btn).to_be_visible()
            one_click_btn.click()

            # Verify redirected to procurement with prefilled SKU
            page.wait_for_url("**/procurement*")
            expect(page.locator(".sku-select").first).not_to_have_value("")
            print("  -> Dynamic warehouse names and one-click restock button verified successfully!")

            # -----------------------------------------------------------------
            # 4. Accounting: MathJax Formula & 4-in-1 Report Center
            # -----------------------------------------------------------------
            print("\n[Scenario 4/5] Testing Accounting MathJax Rendering & 4-in-1 Financial Reports...")
            page.goto(f"{BASE_URL}/accounting?tab=trial_balance")
            expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()

            # Check trial balance EAS equation text exists
            sub_title = page.locator("text=/遵循 EAS 商業會計借貸恆等式/")
            expect(sub_title).to_be_visible()
            print("  -> Accounting trial balance loaded with EAS equation.")

            # Switch to Reports Tab
            page.locator("a[href='/accounting?tab=reports']").click()
            expect(page.locator("#accounting-reports-container")).to_be_visible()
            expect(page.locator("h2:has-text('全方位財務與營運整合報表中心')")).to_be_visible()

            # Download 4-in-1 executive financial workbook
            with page.expect_download() as rep_download_info:
                page.locator("#btn-download-executive-report").click()
            rep_download = rep_download_info.value
            financial_report_path = PROJECT_ROOT / "temp_financial_4in1.xlsx"
            rep_download.save_as(str(financial_report_path))
            assert financial_report_path.exists()
            assert financial_report_path.stat().st_size > 1000
            print(f"  -> Successfully streamed 4-in-1 financial report: {financial_report_path.stat().st_size} bytes")

            # -----------------------------------------------------------------
            # 5. CRM: Multi-Item Deal Creation & Quotation Auto-Inheritance
            # -----------------------------------------------------------------
            print("\n[Scenario 5/5] Testing CRM Multi-Item Deal Pricing & Quotation Inheritance...")
            page.goto(f"{BASE_URL}/crm")
            expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM 前段商機與文件中心").first).to_be_visible()

            # Open "建立新商機" modal
            page.locator("button:has-text('建立新商機')").first.click()
            deal_modal = page.locator("#modal-new-deal")
            expect(deal_modal).to_be_visible()

            # Fill in deal form
            deal_modal.locator("#deal-contact-select").select_option(value=contact.contact_id)
            deal_modal.locator("input[name='title']").fill("2026 智慧半導體產線感測設備整建案")
            deal_modal.locator("select[name='stage']").select_option(value="LEAD")

            # Item 1: SKU-PRO-01, qty=5, price=2500 -> 12,500
            deal_modal.locator("select[name='sku_1']").select_option(value="SKU-PRO-01")
            deal_modal.locator("#deal_qty_1").fill("5")
            deal_modal.locator("#deal_price_1").fill("2500")

            # Item 2: SKU-ACC-02, qty=2, price=650 -> 1,300
            deal_modal.locator("select[name='sku_2']").select_option(value="SKU-ACC-02")
            deal_modal.locator("#deal_qty_2").fill("2")
            deal_modal.locator("#deal_price_2").fill("650")

            # Trigger calculation by clicking another input or dispatching event
            page.evaluate("calcDealTotal()")
            page.wait_for_timeout(300)

            # Check calculated total: 12500 + 1300 = 13,800
            expect(deal_modal.locator("#deal-total-display")).to_contain_text("13,800")
            print("  -> Deal items dynamically calculated expected total: NT$ 13,800")

            # Submit deal
            deal_modal.locator("button[type='submit']").click()
            page.wait_for_timeout(1000)

            # Verify deal card appears on Kanban
            created_card = page.locator("div[id^='deal-card-']").filter(has_text="2026 智慧半導體產線感測設備整建案").first
            expect(created_card).to_be_visible()
            expect(created_card).to_contain_text("13,800")
            expect(created_card).to_contain_text("旗艦智慧終端機 x 5")
            expect(created_card).to_contain_text("極速充電套件組 x 2")
            print("  -> Deal card successfully rendered with items breakdown and NT$ 13,800!")

            # Advance deal to PROPOSAL
            advance_btn = created_card.locator("button:has-text('進展報價')").first
            expect(advance_btn).to_be_visible()
            advance_btn.click()
            page.wait_for_timeout(1000)

            # Locate card in proposal stage
            proposal_card = page.locator("div[id^='deal-card-']").filter(has_text="2026 智慧半導體產線感測設備整建案").first
            expect(proposal_card).to_be_visible()

            # Open quotation modal
            quote_btn = proposal_card.locator("button:has-text('報價單')").first
            expect(quote_btn).to_be_visible()
            quote_btn.click()

            # Verify quotation modal inherited the deal's items!
            quote_modal = page.locator("#modal-new-quote")
            expect(quote_modal).to_be_visible()
            expect(quote_modal.locator("select[name='sku_1']")).to_have_value("SKU-PRO-01")
            expect(quote_modal.locator("input[name='qty_1']")).to_have_value("5")
            expect(quote_modal.locator("input[name='price_1']")).to_have_value("2500")

            expect(quote_modal.locator("select[name='sku_2']")).to_have_value("SKU-ACC-02")
            expect(quote_modal.locator("input[name='qty_2']")).to_have_value("2")
            expect(quote_modal.locator("input[name='price_2']")).to_have_value("650")
            print("  -> Quotation modal successfully inherited items, quantities, and prices from the deal!")

            # Submit quotation
            quote_modal.locator("button[type='submit']").click()
            page.wait_for_timeout(1000)

            # Verify quote generated on the card
            updated_card = page.locator("div[id^='deal-card-']").filter(has_text="2026 智慧半導體產線感測設備整建案").first
            expect(updated_card).to_contain_text("商業報價單")
            expect(updated_card.locator("a:has-text('DOCX')")).to_be_visible()
            expect(updated_card.locator("a:has-text('預覽 PDF')")).to_be_visible()
            print("  -> Commercial quotation generated and document buttons (DOCX/PDF) are active!")

            print("\n[SUCCESS] All 5 Playwright Headed E2E Scenarios for the new features passed perfectly!")

        finally:
            browser.close()
            # Cleanup temp files
            for pth in [bom_excel_path, financial_report_path, test_db_path]:
                try:
                    if pth and pth.exists():
                        pth.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    test_playwright_all_new_features()
