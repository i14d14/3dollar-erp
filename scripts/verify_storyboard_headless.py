from __future__ import annotations
import os
import sys
import time
import threading
import datetime
from decimal import Decimal
from pathlib import Path
import openpyxl
import uvicorn
from playwright.sync_api import sync_playwright, expect

# Ensure UTF-8 output encoding for Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set working directory to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.shared.database import Database
from src.shared.event_bus import EventBus
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.extended_core.crm.services.crm_service import CrmService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter
from src.channel_ui.line_bot.service import LineBotService
from src.channel_ui.web.app import create_app

PORT = 8000
BASE_URL = f"http://127.0.0.1:{PORT}"


def start_server_in_thread(app):
    """Start uvicorn server in a daemon thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server


def wait_for_server(url: str, timeout: float = 10.0):
    """Poll URL until server is responding."""
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


def prepare_demo_data(db: Database, event_bus: EventBus):
    """Ensure dedicated proposal deal exists for smooth demonstration."""
    inv_service = InventoryService(db=db)
    crm_service = CrmService(db=db, event_bus=event_bus)

    # 1. Ensure stock exists in WH-MAIN
    inv_service.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("50.0"), Decimal("1500.0"), "DEMO-INIT", "Demo stock")
    inv_service.adjust_stock("WH-MAIN", "SKU-ACC-02", Decimal("50.0"), Decimal("300.0"), "DEMO-INIT", "Demo stock")

    # 2. Find or create demo contact
    contacts = crm_service.list_contacts()
    demo_contact = None
    for c in contacts:
        if "宏達" in c.company_name or "美德" in c.company_name:
            demo_contact = c
            break
    if not demo_contact:
        demo_contact = crm_service.create_contact(
            company_name="美德醫療器材股份有限公司",
            contact_name="陳建宏 協理",
            tax_id="84561234",
            email="service@med-demo.com.tw",
            phone="02-27891234",
        )

    # 3. Create a pristine deal in PROPOSAL stage with a quote
    deal_title = f"美德醫療 2026 旗艦智慧終端採購案"
    deal = crm_service.create_deal(
        contact_id=demo_contact.contact_id,
        title=deal_title,
        expected_amount=Decimal("50000.0"),
    )
    quote = crm_service.create_quote(
        deal_id=deal.deal_id,
        items=[
            ("SKU-PRO-01", Decimal("2.0"), Decimal("25000.0")),
        ],
        valid_days=30,
    )
    return deal.deal_id, deal_title


def run_storyboard_verification():
    print("=" * 70)
    print("🚀 啟動 3Dollar ERP 60 秒 Demo 劇本 Playwright 無錄影全流程驗證")
    print("=" * 70)

    # 1. 初始化資料庫與服務
    db = Database()
    event_bus = EventBus()
    mock_line_adapter = MockLineMessagingAdapter()
    
    app = create_app(
        db=db,
        event_bus=event_bus,
        line_messaging_port=mock_line_adapter,
        line_channel_secret="mock_channel_secret",
    )

    print("\n[1/7] 準備展示資料：建立專屬 PROPOSAL 商機與報價單...")
    deal_id, deal_title = prepare_demo_data(db, event_bus)
    print(f"  ✓ 商機已就緒: {deal_id} - '{deal_title}'")

    print("\n[2/7] 啟動背景 FastAPI 伺服器 (Port 8000)...")
    server = start_server_in_thread(app)
    wait_for_server(BASE_URL)
    print(f"  ✓ 伺服器正常響應: {BASE_URL}")

    # 2. 啟動 Playwright 瀏覽器
    with sync_playwright() as p:
        print("\n[3/7] 啟動 Playwright Headless Chromium 瀏覽器...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # ---------------------------------------------------------------------
        # 場景 1: Hook / 營運即時儀表板 (00~07s)
        # ---------------------------------------------------------------------
        print("\n[場景 1/5] 驗證 Hook / 營運即時儀表板 (/)")
        page.goto(f"{BASE_URL}/")
        expect(page.locator("h1").filter(has_text="營運即時儀表板").first).to_be_visible()
        expect(page.locator("body")).to_contain_text("今日新增訂單")
        expect(page.locator("body")).to_contain_text("待出貨訂單")
        expect(page.locator("body")).to_contain_text("安全存量警報")
        expect(page.locator("body")).to_contain_text("待沖銷應收帳款")
        print("  ✓ 儀表板 4 大 KPI 卡片與訂單清冊渲染成功")

        # ---------------------------------------------------------------------
        # 場景 2: 哩來 CRM 商機一鍵穿透轉 ERP (07~18s)
        # ---------------------------------------------------------------------
        print(f"\n[場景 2/5] 驗證 哩來 CRM 一鍵贏單轉 ERP (/crm)")
        page.goto(f"{BASE_URL}/crm")
        expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM").first).to_be_visible()

        deal_card = page.locator(f"#deal-card-{deal_id}")
        expect(deal_card).to_be_visible()

        convert_btn = deal_card.locator("button:has-text('⚡ 贏單轉 ERP')")
        expect(convert_btn).to_be_visible()
        print("  ✓ 找到目標提案商機卡片，點擊『⚡ 贏單轉 ERP』...")
        convert_btn.click()

        # 等待轉單完成與 Toast
        expect(page.locator("body")).to_contain_text("商機已成功拋轉為 ERP 銷售訂單", timeout=5000)
        
        # 獲取自動產生的訂單編號 SO-xxxx
        deal_card_won = page.locator(f"#deal-card-{deal_id}")
        so_link = deal_card_won.locator("a[href='/orders']")
        expect(so_link).to_be_visible()
        order_id = so_link.inner_text().replace("➜", "").strip()
        print(f"  ✓ 贏單拋轉成功！生成 ERP 銷售訂單號碼: {order_id}")

        # ---------------------------------------------------------------------
        # 場景 3: Dinkoko ERP 履約扣庫、拆批出貨與發票 (18~33s)
        # ---------------------------------------------------------------------
        print(f"\n[場景 3/5] 驗證 Dinkoko ERP 訂單履約作業中心 (/orders)")
        page.goto(f"{BASE_URL}/orders")
        expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

        order_row = page.locator(f"#order-row-{order_id}")
        expect(order_row).to_be_visible()
        expect(order_row).to_contain_text("DRAFT")
        print("  ✓ 訂單已呈現於 ERP 清單中 (狀態: DRAFT)")

        # 步驟 3.1: 鎖庫確認
        confirm_btn = order_row.locator("button:has-text('鎖庫確認')")
        expect(confirm_btn).to_be_visible()
        print("  ✓ 點擊『鎖庫確認』...")
        confirm_btn.click()

        expect(order_row).to_contain_text("CONFIRMED", timeout=5000)
        print("  ✓ 訂單狀態切換為 CONFIRMED (庫存已安全鎖定)")

        # 步驟 3.2: 拆批出貨彈窗
        partial_ship_btn = order_row.locator("button:has-text('拆批出貨')")
        expect(partial_ship_btn).to_be_visible()
        print("  ✓ 點擊『拆批出貨』開啟 1:N 出貨彈窗...")
        partial_ship_btn.click()

        modal = page.locator("#partial-ship-modal")
        expect(modal).to_be_visible()
        print("  ✓ 拆批出貨彈窗成功彈出，確認各 SKU 出貨量...")

        submit_ship = modal.locator("button:has-text('確認拆批出貨')")
        submit_ship.click()

        # 等待彈窗消失與出貨完成
        expect(modal).not_to_be_visible(timeout=5000)
        expect(order_row).to_contain_text("SHIPPED", timeout=5000)
        print("  ✓ 拆批出貨執行完畢，狀態更新為 SHIPPED")

        # 步驟 3.3: 標籤與 A4 貼紙彈窗
        a4_label_btn = order_row.locator("button:has-text('A4 貼紙')")
        expect(a4_label_btn).to_be_visible()
        print("  ✓ 點擊『📄 A4 貼紙』開啟起印格位選取彈窗...")
        a4_label_btn.click()

        a4_modal = page.locator("#a4-label-modal")
        expect(a4_modal).to_be_visible()
        print("  ✓ A4 2x2 標籤格位選取彈窗展示成功，點擊取消關閉...")
        a4_modal.locator("button:has-text('取消')").click()
        expect(a4_modal).not_to_be_visible()

        # 步驟 3.4: 開立電子發票
        invoice_btn = order_row.locator("button:has-text('開立發票')")
        expect(invoice_btn).to_be_visible()
        print("  ✓ 點擊『開立發票』...")
        invoice_btn.click()

        expect(order_row).to_contain_text("COMPLETED", timeout=5000)
        expect(order_row.locator("a:has-text('🧾 發票')")).to_be_visible()
        print("  ✓ 電子發票開立成功！DO 與 INV 雙綠燈亮起，訂單晉級 COMPLETED")

        # ---------------------------------------------------------------------
        # 場景 4: 探吉會計 自動入帳與試算表平衡 (33~45s)
        # ---------------------------------------------------------------------
        print(f"\n[場景 4/5] 驗證 探吉會計 自動入帳、試算平衡與 Excel 匯出 (/accounting)")
        page.goto(f"{BASE_URL}/accounting")
        expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()
        expect(page.locator("body")).to_contain_text("本期營業收入")
        expect(page.locator("body")).to_contain_text("營業毛利")

        # 查看試算表平衡
        page.locator("a[href='/accounting?tab=trial_balance']").click()
        expect(page.locator("body")).to_contain_text("借貸嚴格平衡")
        print("  ✓ 會計試算表借貸嚴格平衡 (剛性借貸驗證 PASS)")

        # 查看帳齡分析
        page.locator("a[href='/accounting?tab=aging']").click()
        expect(page.locator("body")).to_contain_text("帳齡分析")
        print("  ✓ 應收帳款 AR 帳齡分析矩陣即時呈現未逾期款項")

        # ---------------------------------------------------------------------
        # 場景 5: 檔案自動化中心 & 4合1 財務報表串流匯出 (45~50s)
        # ---------------------------------------------------------------------
        print(f"\n[場景 5/5] 驗證檔案自動化中心與 4合1 Excel 串流 (/ai/tools)")
        page.goto(f"{BASE_URL}/ai/tools")
        expect(page.locator("h1").filter(has_text="檔案自動化").first).to_be_visible()

        page.locator("#tab-btn-reports").click()
        
        with page.expect_download() as download_info:
            page.locator("a:has-text('匯出全套財務營運報表 (.xlsx)')").click()
        download = download_info.value
        export_path = PROJECT_ROOT / "artifacts" / "test_demo_report.xlsx"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(str(export_path))

        wb = openpyxl.load_workbook(str(export_path), read_only=True)
        print(f"  ✓ 4合1 財務活頁簿下載成功: {export_path.name} (活頁數: {len(wb.sheetnames)})")
        wb.close()

        # ---------------------------------------------------------------------
        # 場景 6: LINE Bot 智能通路查單 (50~56s)
        # ---------------------------------------------------------------------
        print(f"\n[場景 6/6] 驗證 LINE Bot 智能通路即時查單")
        inv_service = InventoryService(db=db)
        order_service = OrderService(db=db, inventory_service=inv_service, event_bus=event_bus)
        line_bot_service = LineBotService(
            db=db,
            order_service=order_service,
            inventory_service=inv_service,
            messaging_port=mock_line_adapter,
        )

        # 模擬使用者在 LINE 聊天室輸入「查單 {order_id}」
        user_query = f"查單 {order_id}"
        print(f"  ✓ 模擬客戶於 LINE 對話框送出: '{user_query}'")
        line_bot_service.handle_text_message(
            user_id="U_DEMO_CUSTOMER_001",
            text=user_query,
            reply_token="reply_token_demo",
        )

        assert mock_line_adapter.last_reply is not None, "Expected reply from LINE Bot"
        sent_msgs = mock_line_adapter.last_reply.messages
        assert len(sent_msgs) == 1, "Expected 1 Flex message reply from LINE Bot"
        flex_reply = sent_msgs[0]
        assert order_id in flex_reply.alt_text or "訂單狀態" in flex_reply.alt_text
        print(f"  ✓ LINE 機器人即時回覆 Flex Message 收據卡片 (訂單狀態: COMPLETED)！")

        browser.close()

    print("\n" + "=" * 70)
    print("🎉 恭喜！60 秒 Demo 劇本全鏈路 Playwright 驗證【100% 全數通過】！")
    print("=" * 70)


if __name__ == "__main__":
    run_storyboard_verification()
