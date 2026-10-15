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
from src.core.domain.order import OrderChannel
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.extended_core.crm.models import DealStage
from src.extended_core.crm.services.crm_service import CrmService
from src.channel_ui.web.app import create_app

PORT = 8011
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


def test_playwright_phase1_full_suite():
    """Playwright E2E UI verification for Phase 1 features in headed mode:
    1. Shipping Carrier Waybill Generation & Tracking Number UI reflection upon order fulfillment.
    2. Native PDF Invoice Extraction & AP Creation via /ai/tools.
    3. Executive Financial 4-in-1 Report Streaming via relocated /accounting?tab=reports.
    4. CRM Multi-item Deal Pipeline & Quotation UI reflection.
    """
    invoice_pdf_path = None
    financial_report_path = None

    test_db_path = PROJECT_ROOT / "test_phase1_playwright.db"
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
    inv.create_warehouse("WH-MAIN", "台北總倉")
    inv.create_warehouse("WH-STORE", "信義旗艦店")
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
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-PRO-01",
        qty_delta=Decimal("50.0"),
        unit_cost=Decimal("1500.0"),
        reference_id="INIT-001",
        notes="期初庫存",
    )

    # Seed an order ready to ship
    order_service = OrderService(db=db, event_bus=event_bus, inventory_service=inv)
    test_order = order_service.create_order(
        customer_id="CUST-PHASE1-TEST",
        items=[("SKU-PRO-01", Decimal("2.0"), Decimal("2500.0"))],
        channel=OrderChannel.DIRECT,
    )
    order_service.confirm_order(test_order.order_id, "WH-MAIN")

    # Seed a CRM contact and multi-item deal
    crm_service = CrmService(db=db, order_service=order_service, event_bus=event_bus)
    contact = crm_service.create_contact(
        company_name="宏遠數位科技有限公司",
        contact_name="陳協理",
        tax_id="88776655",
        phone="02-23456789",
    )
    crm_deal = crm_service.create_deal(
        contact_id=contact.contact_id,
        title="2026 智慧辦公室旗艦終端換裝案",
        stage=DealStage.LEAD,
        items=[
            ("SKU-PRO-01", Decimal("5"), Decimal("2500.0")),  # 12500
            ("SKU-ACC-02", Decimal("5"), Decimal("650.0")),   # 3250
        ],
    )

    app = create_app(db=db, event_bus=event_bus)
    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)
    print(f"[*] Test server running at {BASE_URL}")

    with sync_playwright() as p:
        # Mandatory Headed Mode
        browser = p.chromium.launch(headless=False, slow_mo=400)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # -----------------------------------------------------------------
            # 1. Shipping Carrier Waybill Generation & UI Tracking Number
            # -----------------------------------------------------------------
            print("\n[Scenario 1/4] Testing Shipping Carrier Waybill Generation on Order Shipment...")
            page.goto(f"{BASE_URL}/orders")
            expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

            order_row = page.locator(f"#order-row-{test_order.order_id}")
            expect(order_row).to_be_visible()
            expect(order_row).to_contain_text("CONFIRMED")

            # Click standard one-click ship button (一鍵出貨 (扣庫))
            ship_btn = order_row.locator("button:has-text('一鍵出貨')").first
            expect(ship_btn).to_be_visible()
            ship_btn.click()

            # Wait for HTMX row update
            page.wait_for_timeout(1000)
            updated_row = page.locator(f"#order-row-{test_order.order_id}")
            expect(updated_row).to_contain_text("SHIPPED")

            # Click DO button to open deliveries modal and inspect carrier tracking number
            do_btn = updated_row.locator("button:has-text('DO-')").first
            expect(do_btn).to_be_visible()
            do_btn.click()

            expect(page.locator("h3:has-text('出貨單紀錄與歷程')")).to_be_visible()
            # Verify carrier generated tracking number starts with TRK-
            tracking_locator = page.locator("text=/託運單號：TRK-\\d{8}-\\d+/").first
            expect(tracking_locator).to_be_visible()
            print(f"  -> Successfully generated carrier tracking number in delivery modal: {tracking_locator.inner_text()}")

            # Close deliveries modal
            page.locator("button:has-text('關閉視窗')").click()
            expect(page.locator("h3:has-text('出貨單紀錄與歷程')")).to_be_hidden()
            page.wait_for_timeout(500)

            # -----------------------------------------------------------------
            # 2. Native PDF Invoice Extraction & AP Creation
            # -----------------------------------------------------------------
            print("\n[Scenario 2/4] Testing Native PDF Invoice Extraction & AP Creation on /ai/tools...")
            page.goto(f"{BASE_URL}/ai/tools")
            expect(page.locator("h1").filter(has_text="檔案自動化與增強外掛").first).to_be_visible()

            # Download the sample Taiwan electronic invoice PDF file
            with page.expect_download() as download_info:
                page.locator("a[href='/ai/invoice/sample-pdf']").first.click()
            download = download_info.value
            invoice_pdf_path = PROJECT_ROOT / "temp_sample_invoice_test.pdf"
            download.save_as(str(invoice_pdf_path))
            assert invoice_pdf_path.exists()
            print(f"  -> Downloaded sample invoice PDF: {invoice_pdf_path.name}")

            # Upload the downloaded invoice PDF file to trigger extraction
            file_input = page.locator("#ai-tab-invoice input[name='file']")
            file_input.set_input_files(str(invoice_pdf_path))

            # Click extract button
            extract_btn = page.locator("#ai-tab-invoice button:has-text('抽取發票資料')")
            extract_btn.click()

            # Verify extracted invoice results loaded via HTMX
            expect(page.locator("#invoice-result-container")).to_contain_text("AB-98765432", timeout=10000)
            expect(page.locator("#invoice-result-container")).to_contain_text("祥茂電子精密工業")
            expect(page.locator("#invoice-result-container")).to_contain_text("金額勾稽吻合")
            print("  -> Invoice PDF vector text layer parsed and cross-checked successfully.")

            # Click confirm AP creation
            confirm_btn = page.locator("#invoice-result-container button:has-text('確認無誤，建立應付帳款')")
            confirm_btn.click()
            expect(page.locator("#invoice-result-container")).to_contain_text("應付帳款與會計分錄建立成功", timeout=10000)
            print("  -> Successfully created Accounts Payable (AP) and Journal Entry from invoice!")

            # -----------------------------------------------------------------
            # 3. Executive Financial 4-in-1 Workbook (Accounting Relocation)
            # -----------------------------------------------------------------
            print("\n[Scenario 3/4] Testing Relocated 4-in-1 Executive Financial Workbook on /accounting...")
            page.goto(f"{BASE_URL}/accounting?tab=reports")
            expect(page.locator("#accounting-reports-container")).to_be_visible()

            # Click export executive financial report
            with page.expect_download() as report_download_info:
                page.locator("#btn-download-executive-report").click()
            report_download = report_download_info.value
            financial_report_path = PROJECT_ROOT / "temp_financial_report_test.xlsx"
            report_download.save_as(str(financial_report_path))
            assert financial_report_path.exists()
            assert financial_report_path.stat().st_size > 1000
            print(f"  -> Successfully generated executive financial report from accounting: {financial_report_path.stat().st_size} bytes")

            # -----------------------------------------------------------------
            # 4. CRM Multi-Item Deal Pipeline & Quotation UI reflection
            # -----------------------------------------------------------------
            print("\n[Scenario 4/4] Testing CRM Multi-Item Deal Pipeline & Quotation Modal...")
            page.goto(f"{BASE_URL}/crm")
            expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM 前段商機與文件中心").first).to_be_visible()

            # Verify seeded deal appears on the Kanban board with correct calculated amount ($15,750)
            deal_card = page.locator(f"#deal-card-{crm_deal.deal_id}")
            expect(deal_card).to_be_visible()
            expect(deal_card).to_contain_text("2026 智慧辦公室旗艦終端換裝案")
            expect(deal_card).to_contain_text("15,750")
            print(f"  -> Seeded multi-item deal rendered with calculated expected amount: NT$ 15,750")

            # Advance deal to PROPOSAL
            advance_btn = deal_card.locator("button:has-text('進展報價')").first
            expect(advance_btn).to_be_visible()
            advance_btn.click()
            page.wait_for_timeout(1000)

            # Locate card in proposal column
            proposal_card = page.locator(f"#deal-card-{crm_deal.deal_id}")
            expect(proposal_card).to_be_visible()

            # Open quotation modal for this deal
            quote_btn = proposal_card.locator("button:has-text('報價單')").first
            expect(quote_btn).to_be_visible()
            quote_btn.click()

            # Verify quotation modal opens
            quote_modal = page.locator("#modal-new-quote")
            expect(quote_modal).to_be_visible()
            expect(quote_modal).to_contain_text("建立商業報價單")
            expect(quote_modal.locator("#quote-modal-deal-title")).to_contain_text(crm_deal.deal_id)
            print("  -> Quotation modal successfully opened and linked to the multi-item deal.")

            # Close modal
            quote_modal.locator("button:has-text('取消')").click()
            expect(quote_modal).to_be_hidden()

            print("\n[SUCCESS] All 4 Playwright Headed E2E Scenarios for Phase 1 passed perfectly!")

        finally:
            browser.close()
            # Cleanup temp files
            for pth in [invoice_pdf_path, financial_report_path, test_db_path]:
                try:
                    if pth and pth.exists():
                        pth.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    test_playwright_phase1_full_suite()
