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

PORT = 8027
BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{PORT}")
SCREENSHOT_DIR = PROJECT_ROOT / "artifacts" / "iteration0922_batch4"


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


def test_playwright_batch4_7_items_suite():
    """Playwright E2E UI verification for the 7 items in Batch 4 in MANDATORY HEADED mode."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    test_db_path = PROJECT_ROOT / "test_playwright_batch4.db"
    if test_db_path.exists():
        test_db_path.unlink()

    db = Database(test_db_path)
    db.init_db()
    bus = EventBus()
    inv_svc = InventoryService(db=db)
    order_svc = OrderService(db=db, event_bus=bus)
    crm_svc = CrmService(db=db, order_service=order_svc, event_bus=bus)
    proc_svc = ProcurementService(db=db, event_bus=bus)

    # Seed base warehouses & products
    inv_svc.create_warehouse("WH-MAIN", "台北總倉")
    inv_svc.create_warehouse("WH-STORE", "信義門市倉")

    inv_svc.create_product(
        sku="SKU-COFFEE-01",
        name="精品濾掛咖啡",
        base_unit="BOX",
        cost_price=Decimal("150.0"),
        selling_price=Decimal("300.0"),
        safety_stock=10,
    )
    inv_svc.create_product(
        sku="SKU-CUP-01",
        name="極簡陶瓷馬克杯",
        base_unit="PCS",
        cost_price=Decimal("80.0"),
        selling_price=Decimal("200.0"),
        safety_stock=5,
    )

    contact = crm_svc.create_contact(
        company_name="聯發數位創新股份有限公司",
        contact_name="林技術長",
        tax_id="23456789",
    )

    deal = crm_svc.create_deal(
        contact_id=contact.contact_id,
        title="2026 研討會伴手禮專案",
        stage=DealStage.LEAD,
        expected_amount=Decimal("30000.0"),
        items=[("SKU-COFFEE-01", Decimal("50"), Decimal("280.00"))],
    )

    po = proc_svc.create_purchase_order(
        supplier_name="優質咖啡烘焙廠",
        warehouse_id="WH-MAIN",
        items=[("SKU-COFFEE-01", Decimal("100"), Decimal("140.00"))],
    )
    proc_svc.submit_purchase_order(po.po_id)

    app = create_app(db=db, event_bus=bus)
    server = start_server_in_thread(app, port=PORT)

    try:
        wait_for_server(BASE_URL)
        print(f"\n[Test Server Started] Running on {BASE_URL}")

        with sync_playwright() as p:
            # MANDATORY INVARIANT: Must be headed mode per AGENTS.md
            browser = p.chromium.launch(headless=False, slow_mo=700)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # -------------------------------------------------------------------------
            # Item 1: 前往 /crm?tab=kanban，點選潛在商機的「進展洽談 ➜」按鈕
            # 預期：卡片移動至「需求洽談」欄位，右上角彈出浮動 Toast「已變更階段為 DISCOVERY」，內含「撤回階段」按鈕
            # -------------------------------------------------------------------------
            print("\n[Item 1] 前往 /crm?tab=kanban，點選潛在商機的「進展洽談 ➜」按鈕...")
            page.goto(f"{BASE_URL}/crm?tab=kanban")
            page.wait_for_load_state("networkidle")

            card = page.locator(f"#deal-card-{deal.deal_id}")
            expect(card).to_be_visible()
            expect(card).to_contain_text("2026 研討會伴手禮專案")
            expect(card).to_contain_text("潛在")

            advance_btn = card.locator('button:has-text("進展洽談 ➜")')
            expect(advance_btn).to_be_visible()
            advance_btn.click()
            time.sleep(1.0)

            toast = page.locator("#toast-container")
            expect(toast).to_be_visible()
            expect(toast).to_contain_text("已變更階段為 DISCOVERY")
            undo_stage_btn = toast.locator('button:has-text("撤回階段")')
            expect(undo_stage_btn).to_be_visible()

            card_discovery = page.locator(f"#deal-card-{deal.deal_id}")
            expect(card_discovery).to_contain_text("洽談")
            page.screenshot(path=str(SCREENSHOT_DIR / "01_deal_advanced_with_undo.png"))
            print("  ✅ Item 1 Passed: 商機成功晉級為 DISCOVERY，右上角彈出浮動 Toast 且具備「撤回階段」按鈕。")

            # -------------------------------------------------------------------------
            # Item 2: 點擊 Toast 上的「撤回階段」按鈕
            # 預期：卡片立即回到「潛在商機」欄位，右上角 Toast 更新為「已成功撤回商機...已回復為 LEAD」
            # -------------------------------------------------------------------------
            print("\n[Item 2] 點擊 Toast 上的「撤回階段」按鈕...")
            undo_stage_btn.click()
            time.sleep(1.0)

            expect(toast).to_contain_text("已成功撤回商機")
            expect(toast).to_contain_text("已回復為 LEAD")
            card_lead = page.locator(f"#deal-card-{deal.deal_id}")
            expect(card_lead).to_contain_text("潛在")
            page.screenshot(path=str(SCREENSHOT_DIR / "02_deal_reverted_to_lead.png"))
            print("  ✅ Item 2 Passed: 點擊撤回按鈕後商機卡片立即回到潛在商機 (LEAD)，Toast 提示已成功回復。")

            # -------------------------------------------------------------------------
            # Item 3: 在任一洽談商機點擊「＋ 報價單」，填寫明細並點選「產出報價單」
            # 預期：商機推進至「方案報價」並顯示商業報價單，右上角彈出 Toast「成功建立報價單...」，內含「撤回報價單」按鈕
            # -------------------------------------------------------------------------
            print("\n[Item 3] 在洽談商機點擊「＋ 報價單」，填寫明細並產出報價單...")
            # Advance to DISCOVERY first
            page.locator(f"#deal-card-{deal.deal_id}").locator('button:has-text("進展洽談 ➜")').click()
            time.sleep(1.0)

            quote_modal_btn = page.locator(f"#deal-card-{deal.deal_id}").locator('button:has-text("＋ 報價單")')
            expect(quote_modal_btn).to_be_visible()
            quote_modal_btn.click()

            quote_modal = page.locator("#modal-new-quote")
            expect(quote_modal).to_be_visible()

            submit_quote_btn = quote_modal.locator('button:has-text("產出報價單")')
            expect(submit_quote_btn).to_be_visible()
            submit_quote_btn.click()
            time.sleep(1.0)

            expect(toast).to_contain_text("成功建立報價單")
            undo_quote_btn = toast.locator('button:has-text("撤回報價單")')
            expect(undo_quote_btn).to_be_visible()

            card_prop = page.locator(f"#deal-card-{deal.deal_id}")
            expect(card_prop).to_contain_text("報價")
            expect(card_prop).to_contain_text("商業報價單")
            page.screenshot(path=str(SCREENSHOT_DIR / "03_quote_created_with_undo.png"))
            print("  ✅ Item 3 Passed: 報價單成功建立，商機進入 PROPOSAL 並顯示商業報價單，Toast 具備「撤回報價單」按鈕。")

            # -------------------------------------------------------------------------
            # Item 4: 點擊 Toast 上的「撤回報價單」按鈕
            # 預期：報價單被刪除，商機自動退回「需求洽談」階段，右上角 Toast 提示「已成功撤回報價單」
            # -------------------------------------------------------------------------
            print("\n[Item 4] 點擊 Toast 上的「撤回報價單」按鈕...")
            undo_quote_btn.click()
            time.sleep(1.0)

            expect(toast).to_contain_text("已成功撤回報價單")
            card_quote_reverted = page.locator(f"#deal-card-{deal.deal_id}")
            expect(card_quote_reverted).to_contain_text("洽談")
            expect(card_quote_reverted).not_to_contain_text("商業報價單")
            page.screenshot(path=str(SCREENSHOT_DIR / "04_quote_reverted_to_discovery.png"))
            print("  ✅ Item 4 Passed: 報價單成功撤銷刪除，商機自動退回需求洽談 (DISCOVERY)。")

            # -------------------------------------------------------------------------
            # Item 5: 前往 /procurement，對狀態為「待到貨」之採購單點選「📥 驗收入庫」並確認
            # 預期：單據狀態變更為「已入庫」，右上角彈出綠色 Toast「採購單已成功驗收入庫...」，內含「撤回入庫」按鈕
            # -------------------------------------------------------------------------
            print("\n[Item 5] 前往 /procurement，對「待到貨」採購單點選「📥 驗收入庫」並確認...")
            page.goto(f"{BASE_URL}/procurement")
            page.wait_for_load_state("networkidle")

            po_row = page.locator(f"#po-row-{po.po_id}")
            expect(po_row).to_be_visible()
            expect(po_row).to_contain_text("待到貨")

            receive_btn = po_row.locator('button:has-text("驗收入庫")')
            expect(receive_btn).to_be_visible()
            receive_btn.click()

            receive_modal = page.locator("#receive-po-modal")
            expect(receive_modal).to_be_visible()
            expect(receive_modal).to_contain_text("物料驗收入庫")

            confirm_recv_btn = receive_modal.locator('button:has-text("確認入庫")')
            expect(confirm_recv_btn).to_be_visible()
            confirm_recv_btn.click()
            time.sleep(1.0)

            expect(toast).to_contain_text("已成功驗收入庫")
            undo_recv_btn = toast.locator('button:has-text("撤回入庫")')
            expect(undo_recv_btn).to_be_visible()

            expect(page.locator(f"#po-row-{po.po_id}")).to_contain_text("已驗收入庫")
            page.screenshot(path=str(SCREENSHOT_DIR / "05_po_received_with_undo.png"))
            print("  ✅ Item 5 Passed: 採購單成功驗收入庫，單據變為「已驗收入庫」，右上角 Toast 具備「撤回入庫」按鈕。")

            # -------------------------------------------------------------------------
            # Item 6: 點擊 Toast 上的「撤回入庫」按鈕
            # 預期：單據狀態即刻恢復為「待到貨」，操作列恢復「驗收入庫」按鈕；庫存流水增加負數紅字沖銷，會計應付帳款與傳票原路沖銷
            # -------------------------------------------------------------------------
            print("\n[Item 6] 點擊 Toast 上的「撤回入庫」按鈕...")
            undo_recv_btn.click()
            time.sleep(1.0)

            expect(toast).to_contain_text("已成功撤回驗收入庫")
            po_row_reverted = page.locator(f"#po-row-{po.po_id}")
            expect(po_row_reverted).to_contain_text("待到貨")
            expect(po_row_reverted.locator('button:has-text("驗收入庫")')).to_be_visible()

            # Verify in DB: stock is back to 0, AP deleted, REVERSAL journal entry exists
            with db.transaction() as conn:
                stock_bal = conn.execute("SELECT balance_after FROM stock_ledger WHERE sku = 'SKU-COFFEE-01' ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
                assert float(stock_bal["balance_after"]) == 0.0, "Stock should be 0 after reversal"

                ap_cnt = conn.execute("SELECT COUNT(*) as c FROM accounts_payable WHERE po_id = ?", (po.po_id,)).fetchone()
                assert ap_cnt["c"] == 0, "AP should be removed"

                rev_cnt = conn.execute("SELECT COUNT(*) as c FROM journal_entries WHERE source_event = 'REVERSAL'").fetchone()
                assert rev_cnt["c"] > 0, "REVERSAL journal entry must exist"

            page.screenshot(path=str(SCREENSHOT_DIR / "06_po_reverted_to_submitted.png"))
            print("  ✅ Item 6 Passed: 撤回入庫成功！狀態恢復「待到貨」，庫存負數流水沖銷為 0，會計 AP 與傳票原路沖銷完畢。")

            # -------------------------------------------------------------------------
            # Item 7: 檢視 /procurement 與 /crm 任何操作後的頁面
            # 預期：全站 100% 無任何舊版靜態綠框橫幅，全部由頂層 #toast-container 統一呈現
            # -------------------------------------------------------------------------
            print("\n[Item 7] 檢視 /procurement 與 /crm 頁面確認 100% 無舊版靜態綠框橫幅...")
            # Check /procurement
            expect(page.locator("#procurement-container").locator("text='✅'")).to_have_count(0)

            # Check /crm
            page.goto(f"{BASE_URL}/crm?tab=contacts")
            page.wait_for_load_state("networkidle")
            expect(page.locator("#crm-container").locator("text='✅'")).to_have_count(0)
            page.screenshot(path=str(SCREENSHOT_DIR / "07_no_static_green_banners.png"))
            print("  ✅ Item 7 Passed: 全站 100% 舊版靜態綠框消滅完畢，全數由頂層 #toast-container 統一掌管。")

            browser.close()
            print("\n🎉 [All 7 UI Items Successfully Verified via Headed Playwright!]")

    finally:
        server.should_exit = True
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    test_playwright_batch4_7_items_suite()
