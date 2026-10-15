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
from src.extended_core.crm.models import DealStage
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.services.crm_service import CrmService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.channel_ui.web.app import create_app

PORT = 8026
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


def test_playwright_batch3_multi_warehouse_suite():
    """Playwright E2E UI verification for Batch 3 (Multi-warehouse fulfillment) in MANDATORY HEADED mode:
    1. Procurement: Create PO targeting WH-STORE, submit it, open receive modal (defaults to WH-STORE),
       and confirm receipt into WH-STORE.
    2. CRM: Open convert deal modal, select destination warehouse as WH-STORE, and convert to ERP order.
    3. Orders: Locate the converted order with WH-STORE badge, lock stock in WH-STORE,
       open ship modal (showing WH-STORE), and ship order deducting inventory strictly from WH-STORE.
    """
    test_db_path = PROJECT_ROOT / "test_batch3_playwright.db"
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

    # Initial stock: 100 in WH-MAIN, 0 in WH-STORE
    inv.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("100.0"), Decimal("120.0"), "INIT-01", "期初主倉盤點入庫")

    order_svc = OrderService(db=db, inventory_service=inv, event_bus=event_bus)
    proc_svc = ProcurementService(db=db, event_bus=event_bus)
    crm_svc = CrmService(db=db, order_service=order_svc)
    acct_svc = AccountingService(db=db)

    # Seed Contact, Deal, and Quote in CRM
    contact = crm_svc.create_contact(
        company_name="信義旗艦咖啡館",
        contact_name="林店長",
        tax_id="88887777",
        email="store@xinyi-cafe.tw",
        phone="02-8765-4321",
    )

    deal = crm_svc.create_deal(
        contact_id=contact.contact_id,
        title="門市咖啡豆常態補貨專案",
        expected_amount=Decimal("5600.0"),
        stage=DealStage.DISCOVERY,
    )

    quote = crm_svc.create_quote(
        deal_id=deal.deal_id,
        items=[
            ("SKU-PRO-01", Decimal("20.0"), Decimal("280.0")),
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

            # =============================================================
            # Part 1: Procurement PO targeting WH-STORE
            # =============================================================
            print("\n[Playwright Headed] 1. 前往採購作業中心...")
            page.goto(f"{BASE_URL}/procurement", wait_until="networkidle")
            page.wait_for_timeout(400)

            expect(page.locator("body")).to_contain_text("採購與進貨作業中心")

            print("[Playwright Headed] 1.1 填寫採購單表單 (目標倉庫: WH-STORE)...")
            page.locator("input[name='supplier_name']").fill("台灣優質生豆進口商")
            page.locator("select[name='target_warehouse']").select_option("WH-STORE")
            page.locator("select[name='sku']").select_option("SKU-PRO-01")
            page.locator("input[name='qty']").fill("50")
            page.locator("input[name='unit_cost']").fill("110.0")

            # Submit PO creation form
            page.locator("button:has-text('建立採購單')").click()
            page.wait_for_timeout(600)

            # Verify PO row created with WH-STORE badge
            po_row = page.locator("tr:has-text('台灣優質生豆進口商')").first
            expect(po_row).to_be_visible()
            expect(po_row).to_contain_text("進貨倉: WH-STORE")
            expect(po_row).to_contain_text("草稿 (DRAFT)")
            print("[Playwright Headed] -> 成功建立採購單，標註進貨倉為 WH-STORE！")

            # Click Submit PO
            print("[Playwright Headed] 1.2 送出採購單 (SUBMIT)...")
            submit_btn = po_row.locator("button:has-text('確認下訂')")
            submit_btn.click()
            page.wait_for_timeout(600)

            po_row = page.locator("tr:has-text('台灣優質生豆進口商')").first
            expect(po_row).to_contain_text("待到貨 (SUBMITTED)")

            # Click Receive Goods modal
            print("[Playwright Headed] 1.3 開啟驗收入庫彈窗並驗證預設入庫倉...")
            recv_btn = po_row.locator("button:has-text('驗收入庫')")
            recv_btn.click()

            receive_modal = page.locator("#receive-po-modal")
            expect(receive_modal).to_be_visible(timeout=5000)
            page.wait_for_timeout(400)

            # Check that warehouse select defaults to WH-STORE
            wh_select = receive_modal.locator("select[name='warehouse_id']")
            expect(wh_select).to_have_value("WH-STORE")
            print("[Playwright Headed] -> 入庫彈窗已正確預設目標進貨倉為 WH-STORE！")

            # Confirm Receipt
            confirm_recv_btn = receive_modal.locator("button:has-text('確認入庫並立帳')")
            confirm_recv_btn.click()
            expect(receive_modal).to_be_hidden(timeout=5000)

            # Verify Toast & PO status
            toast = page.locator("#toast-container")
            expect(toast).to_contain_text("已成功驗收入庫", timeout=5000)
            page.wait_for_timeout(500)

            po_row = page.locator("tr:has-text('台灣優質生豆進口商')").first
            expect(po_row).to_contain_text("已驗收入庫 (RECEIVED)")
            print("[Playwright Headed] -> 驗收入庫完成！WH-STORE 庫存已增加 50 件。")

            # =============================================================
            # Part 2: CRM Deal Conversion to WH-STORE Order
            # =============================================================
            print("\n[Playwright Headed] 2. 前往 CRM 商機看板進行贏單轉單...")
            page.goto(f"{BASE_URL}/crm", wait_until="networkidle")
            page.wait_for_timeout(400)

            expect(page.locator("body")).to_contain_text("門市咖啡豆常態補貨專案")
            convert_btn = page.locator("button:has-text('⚡ 贏單轉 ERP')")
            expect(convert_btn).to_be_visible()
            convert_btn.click()

            convert_modal = page.locator("#convert-deal-modal")
            expect(convert_modal).to_be_visible(timeout=5000)
            page.wait_for_timeout(400)

            # Check warehouse dropdown exists and select WH-STORE
            print("[Playwright Headed] 2.1 選擇出貨倉庫為 WH-STORE (信義實體門市倉)...")
            deal_wh_select = convert_modal.locator("select[name='warehouse_id']")
            expect(deal_wh_select).to_be_visible()
            deal_wh_select.select_option("WH-STORE")

            # Submit conversion
            convert_modal.locator("button[type='submit']").click()
            expect(convert_modal).to_be_hidden(timeout=5000)
            expect(toast).to_contain_text("商機已成功拋轉為 ERP 銷售訂單", timeout=5000)
            page.wait_for_timeout(500)
            print("[Playwright Headed] -> 商機拋轉 ERP 訂單成功！")

            # =============================================================
            # Part 3: Orders Fulfillment in WH-STORE
            # =============================================================
            print("\n[Playwright Headed] 3. 前往訂單與出貨中心...")
            page.goto(f"{BASE_URL}/orders", wait_until="networkidle")
            page.wait_for_timeout(500)

            # Find the new CRM order row
            order_row = page.locator("tr:has-text('CRM')").first
            expect(order_row).to_be_visible()
            expect(order_row).to_contain_text("WH-STORE")
            expect(order_row).to_contain_text("DRAFT")
            print("[Playwright Headed] -> 訂單列表確認已標註出貨倉 WH-STORE！")

            # Click Lock Stock
            print("[Playwright Headed] 3.1 執行虛擬庫存鎖定 (Lock)...")
            lock_btn = order_row.locator("button:has-text('鎖庫確認')")
            lock_btn.click()
            page.wait_for_timeout(600)

            order_row = page.locator("tr:has-text('CRM')").first
            expect(order_row).to_contain_text("CONFIRMED")
            print("[Playwright Headed] -> 庫存鎖定成功，訂單推進至 CONFIRMED！")

            # Click Ship
            print("[Playwright Headed] 3.2 點擊出貨，驗證出貨彈窗出貨倉...")
            ship_btn = order_row.locator("button:has-text('一鍵出貨')").first
            ship_btn.click()

            ship_modal = page.locator("#ship-confirm-modal")
            expect(ship_modal).to_be_visible(timeout=5000)
            page.wait_for_timeout(400)

            # Verify modal displays WH-STORE
            expect(ship_modal).to_contain_text("WH-STORE")
            print("[Playwright Headed] -> 出貨確認彈窗正確顯示出貨來源倉為 WH-STORE！")

            # Confirm Shipment
            ship_modal.locator("button:has-text('確認執行出貨')").click()
            expect(ship_modal).to_be_hidden(timeout=5000)
            page.wait_for_timeout(600)

            order_row = page.locator("tr:has-text('CRM')").first
            expect(order_row).to_contain_text("SHIPPED")
            print("[Playwright Headed] -> 訂單出貨完成，狀態推進至 SHIPPED！")

            # =============================================================
            # Part 4: Verify Multi-Warehouse Stock Isolation in DB
            # =============================================================
            print("\n[Playwright Headed] 4. 驗證多倉庫存帳本嚴格隔離...")
            # WH-MAIN should still have exactly 100
            bal_main = inv.get_stock_balance("WH-MAIN", "SKU-PRO-01")
            assert bal_main == Decimal("100.0"), f"WH-MAIN stock altered unexpectedly: {bal_main}"

            # WH-STORE had 0, received 50, shipped 20 -> should have exactly 30
            bal_store = inv.get_stock_balance("WH-STORE", "SKU-PRO-01")
            assert bal_store == Decimal("30.0"), f"WH-STORE stock expected 30.0, got: {bal_store}"
            print(f"[Playwright Headed] -> 庫存精確核實：WH-MAIN = {bal_main} (未受干擾), WH-STORE = {bal_store} (50進 - 20出 = 30)！")

            browser.close()
            print("\n[Playwright Headed] ✅ Batch 3 Playwright Headed E2E 全部驗證通過！\n")

    finally:
        server.should_exit = True
        time.sleep(0.5)
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    test_playwright_batch3_multi_warehouse_suite()
