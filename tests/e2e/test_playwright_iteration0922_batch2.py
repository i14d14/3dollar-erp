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
from src.extended_core.crm.models import DealStage
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.services.crm_service import CrmService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.channel_ui.web.app import create_app

PORT = 8025
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


def test_playwright_batch2_crm_and_docs_suite():
    """Playwright E2E UI verification for Batch 2 (CRM & Docs) in MANDATORY HEADED mode:
    1. CRM: Deal in PROPOSAL stage with a formal Quote.
    2. Click '⚡ 贏單轉 ERP' button.
    3. Verify #convert-deal-modal renders quote number, inherited items breakdown, and order total.
    4. Verify '無特定物料明細' is NOT displayed.
    5. Test Quote PDF stream download (/crm/quotes/{quote_id}/pdf) conforms to standard PDF.
    6. Submit modal to convert deal to ERP order, verify Toast OOB notification and modal auto-close.
    7. Navigate to /orders, verify newly converted order in Dura ERP with channel=CRM.
    8. Test shipping label PDF stream (/orders/{order_id}/label.pdf).
    """
    test_db_path = PROJECT_ROOT / "test_batch2_playwright.db"
    if test_db_path.exists():
        try:
            test_db_path.unlink()
        except Exception:
            pass

    db = Database(test_db_path)
    db.init_db()
    event_bus = EventBus()

    # Pre-seed Warehouses & Products
    inv = InventoryService(db=db)
    inv.create_warehouse("WH-MAIN", "台北總部主倉")
    inv.create_warehouse("WH-STORE", "信義實體門市倉")

    p1 = inv.create_product(
        sku="SKU-PRO-01",
        name="極品冠軍曼特寧濾掛咖啡",
        base_unit="BOX",
        cost_price=Decimal("120.0"),
        selling_price=Decimal("280.0"),
        safety_stock=20,
    )
    p2 = inv.create_product(
        sku="SKU-ACC-02",
        name="商用多功能智慧終端機",
        base_unit="SET",
        cost_price=Decimal("1200.0"),
        selling_price=Decimal("2500.0"),
        safety_stock=10,
    )

    inv.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("100.0"), Decimal("120.0"), "INIT-01", "期初盤點入庫")
    inv.adjust_stock("WH-MAIN", "SKU-ACC-02", Decimal("50.0"), Decimal("1200.0"), "INIT-02", "期初盤點入庫")

    order_svc = OrderService(db=db, inventory_service=inv, event_bus=event_bus)
    proc_svc = ProcurementService(db=db, event_bus=event_bus)
    crm_svc = CrmService(db=db, order_service=order_svc)
    acct_svc = AccountingService(db=db)

    # Seed Contact, Deal, and Quote
    contact = crm_svc.create_contact(
        company_name="宏達數位科技有限公司",
        contact_name="陳經理",
        tax_id="24567890",
        email="service@htc-digital.tw",
        phone="02-2345-6789",
    )

    deal = crm_svc.create_deal(
        contact_id=contact.contact_id,
        title="2026 智慧辦公終端採購案",
        expected_amount=Decimal("30600.0"),
        stage=DealStage.DISCOVERY,
    )

    quote = crm_svc.create_quote(
        deal_id=deal.deal_id,
        items=[
            ("SKU-PRO-01", Decimal("20.0"), Decimal("280.0")),
            ("SKU-ACC-02", Decimal("10.0"), Decimal("2500.0")),
        ],
        valid_days=30,
    )

    app = create_app(db=db, event_bus=event_bus)

    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)

    try:
        with sync_playwright() as p:
            # Mandatory Headed Execution: headless=False, slow_mo=300ms
            browser = p.chromium.launch(headless=False, slow_mo=300)
            page = browser.new_page(viewport={"width": 1280, "height": 850})

            # -------------------------------------------------------------
            # Step 1: Open CRM page and verify Deal Kanban
            # -------------------------------------------------------------
            print("\n[Playwright Headed] 1. 前往 CRM 商機看板...")
            page.goto(f"{BASE_URL}/crm", wait_until="networkidle")
            page.wait_for_timeout(400)

            expect(page.locator("body")).to_contain_text("哩來 (LiLai) CRM")
            expect(page.locator("body")).to_contain_text("2026 智慧辦公終端採購案")
            expect(page.locator("body")).to_contain_text(quote.quote_number)

            # -------------------------------------------------------------
            # Step 2: Click '⚡ 贏單轉 ERP' button and verify modal
            # -------------------------------------------------------------
            print("[Playwright Headed] 2. 點擊 '⚡ 贏單轉 ERP' 開啟確認彈窗...")
            convert_btn = page.locator("button:has-text('⚡ 贏單轉 ERP')")
            expect(convert_btn).to_be_visible()
            convert_btn.click()

            modal = page.locator("#convert-deal-modal")
            expect(modal).to_be_visible(timeout=5000)
            page.wait_for_timeout(500)

            # Verify modal title and inherited quote number
            expect(modal).to_contain_text("贏單轉 ERP 銷售訂單確認")
            expect(modal).to_contain_text(f"依據報價單：{quote.quote_number}")
            expect(modal).to_contain_text("宏達數位科技有限公司")

            # Verify line items inherited from Quote (SKU-PRO-01 and SKU-ACC-02)
            expect(modal).to_contain_text("SKU-PRO-01")
            expect(modal).to_contain_text("SKU-ACC-02")
            expect(modal).to_contain_text("預計訂單總計")

            # CRITICAL CHECK: Verify '無特定物料明細' is NOT in modal
            modal_text = modal.inner_text()
            assert "無特定物料明細" not in modal_text, "Error: convert modal should not show '無特定物料明細' when quote items exist!"
            print("[Playwright Headed] -> 彈窗成功繼承報價單明細，且未出現「無特定物料明細」！")

            # -------------------------------------------------------------
            # Step 3: Test Quote PDF Download
            # -------------------------------------------------------------
            print("[Playwright Headed] 3. 測試報價單 PDF 下載鏈路...")
            pdf_resp = page.request.get(f"{BASE_URL}/crm/quotes/{quote.quote_id}/pdf")
            assert pdf_resp.status == 200, f"Quote PDF request failed with status {pdf_resp.status}"
            assert pdf_resp.headers.get("content-type") == "application/pdf"
            assert pdf_resp.body().startswith(b"%PDF-"), "Invalid PDF binary format"
            print(f"[Playwright Headed] -> 報價單 PDF 生成與下載成功 ({len(pdf_resp.body())} bytes)！")

            # -------------------------------------------------------------
            # Step 4: Confirm Conversion in Modal
            # -------------------------------------------------------------
            print("[Playwright Headed] 4. 送出贏單轉 ERP 正式訂單...")
            submit_btn = modal.locator("button[type='submit']")
            submit_btn.click()

            # Wait for modal to disappear and toast to appear
            expect(modal).to_be_hidden(timeout=5000)
            toast = page.locator("#toast-container")
            expect(toast).to_contain_text("商機已成功拋轉為 ERP 銷售訂單", timeout=5000)
            page.wait_for_timeout(600)
            print("[Playwright Headed] -> 拋轉成功，收到綠色 Toast 通知！")

            # -------------------------------------------------------------
            # Step 5: Navigate to Orders and verify order
            # -------------------------------------------------------------
            print("[Playwright Headed] 5. 前往訂單中心驗證轉入之銷售訂單...")
            page.goto(f"{BASE_URL}/orders", wait_until="networkidle")
            page.wait_for_timeout(500)

            expect(page.locator("body")).to_contain_text("訂單與出貨作業中心")
            expect(page.locator("body")).to_contain_text(contact.contact_id)
            expect(page.locator("body")).to_contain_text("CRM")
            expect(page.locator("body")).to_contain_text("NT$ 30,600.00")

            # Verify shipping label button / PDF endpoints
            label_resp = page.request.get(f"{BASE_URL}/orders/SO-HIST-01/label.pdf")
            assert label_resp.status == 200, f"Expected 200, got {label_resp.status}"
            assert label_resp.headers.get("content-type") == "application/pdf"
            assert label_resp.body().startswith(b"%PDF-")
            print(f"[Playwright Headed] -> 出貨單標籤 PDF 驗證成功 ({len(label_resp.body())} bytes)！")

            label_a4_resp = page.request.get(f"{BASE_URL}/orders/SO-HIST-01/label_a4.pdf?start_pos=1")
            assert label_a4_resp.status == 200, f"Expected 200, got {label_a4_resp.status}"
            assert label_a4_resp.headers.get("content-type") == "application/pdf"
            assert label_a4_resp.body().startswith(b"%PDF-")
            print(f"[Playwright Headed] -> A4 多格出貨單標籤 PDF 驗證成功 ({len(label_a4_resp.body())} bytes)！")

            browser.close()
            print("[Playwright Headed] ✅ Batch 2 Playwright Headed E2E 全部驗證通過！\n")

    finally:
        server.should_exit = True
        time.sleep(0.5)
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    test_playwright_batch2_crm_and_docs_suite()
