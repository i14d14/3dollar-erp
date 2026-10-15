from __future__ import annotations
import os
import sys
import time
import subprocess
import threading
from decimal import Decimal
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright, expect

# Ensure UTF-8 output encoding for Windows PowerShell
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.shared.database import Database
from src.shared.event_bus import EventBus
from src.core.services.inventory_service import InventoryService
from src.extended_core.crm.services.crm_service import CrmService
from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter
from src.channel_ui.web.app import create_app

PORT = 8000
BASE_URL = f"http://127.0.0.1:{PORT}"
VIDEO_DIR = PROJECT_ROOT / "artifacts" / "videos"


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


def record_demo_video():
    print("=" * 75)
    print("🎬 開始自動錄製 3Dollar ERP 60 秒展示影片 (Playwright 1080p)")
    print("=" * 75)

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

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

    print("\n[步驟 1] 準備展示資料：建立專屬 PROPOSAL 商機與報價單...")
    deal_id, deal_title = prepare_demo_data(db, event_bus)
    print(f"  ✓ 目標商機就緒: {deal_id} ({deal_title})")

    print("\n[步驟 2] 啟動背景 FastAPI 伺服器...")
    server = start_server_in_thread(app)
    wait_for_server(BASE_URL)
    print(f"  ✓ 伺服器已就緒: {BASE_URL}")

    # 2. 啟動 Playwright 錄影瀏覽器
    with sync_playwright() as p:
        print("\n[步驟 3] 啟動 Playwright 1080p 錄影環境 (slow_mo=450ms)...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # ---------------------------------------------------------------------
        # 場景 1: 營運即時儀表板 (00~06s)
        # ---------------------------------------------------------------------
        print("\n🎥 錄製場景 1：營運即時儀表板 (/)...")
        page.goto(f"{BASE_URL}/")
        expect(page.locator("h1").filter(has_text="營運即時儀表板").first).to_be_visible()
        page.wait_for_timeout(2500)

        # ---------------------------------------------------------------------
        # 場景 2: 哩來 CRM 贏單一鍵穿透轉 ERP (06~18s)
        # ---------------------------------------------------------------------
        print("🎥 錄製場景 2：哩來 CRM 商機看板一鍵轉 ERP (/crm)...")
        page.goto(f"{BASE_URL}/crm")
        expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM").first).to_be_visible()
        page.wait_for_timeout(1000)

        deal_card = page.locator(f"#deal-card-{deal_id}")
        expect(deal_card).to_be_visible()
        deal_card.hover()
        page.wait_for_timeout(1200)

        convert_btn = deal_card.locator("button:has-text('⚡ 贏單轉 ERP')")
        expect(convert_btn).to_be_visible()
        convert_btn.hover()
        page.wait_for_timeout(800)
        convert_btn.click()

        # 等待轉單完成與 Toast
        expect(page.locator("body")).to_contain_text("商機已成功拋轉為 ERP 銷售訂單", timeout=5000)
        page.wait_for_timeout(1500)

        deal_card_won = page.locator(f"#deal-card-{deal_id}")
        so_link = deal_card_won.locator("a[href='/orders']")
        expect(so_link).to_be_visible()
        order_id = so_link.inner_text().replace("➜", "").strip()
        print(f"  ✓ 贏單轉單成功: {order_id}")
        page.wait_for_timeout(1500)

        # ---------------------------------------------------------------------
        # 場景 3: Dinkoko ERP 履約扣庫、拆批出貨與發票 (18~35s)
        # ---------------------------------------------------------------------
        print("🎥 錄製場景 3：Dinkoko ERP 履約扣庫、拆批出貨與開立發票 (/orders)...")
        page.goto(f"{BASE_URL}/orders")
        expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()
        page.wait_for_timeout(1000)

        order_row = page.locator(f"#order-row-{order_id}")
        expect(order_row).to_be_visible()
        order_row.hover()
        page.wait_for_timeout(1000)

        # 步驟 3.1: 鎖庫確認
        confirm_btn = order_row.locator("button:has-text('鎖庫確認')")
        confirm_btn.hover()
        page.wait_for_timeout(600)
        confirm_btn.click()
        expect(order_row).to_contain_text("CONFIRMED", timeout=5000)
        page.wait_for_timeout(1500)

        # 步驟 3.2: 拆批出貨彈窗
        partial_ship_btn = order_row.locator("button:has-text('拆批出貨')")
        partial_ship_btn.hover()
        page.wait_for_timeout(600)
        partial_ship_btn.click()

        modal = page.locator("#partial-ship-modal")
        expect(modal).to_be_visible()
        page.wait_for_timeout(1800)

        submit_ship = modal.locator("button:has-text('確認拆批出貨')")
        submit_ship.hover()
        page.wait_for_timeout(600)
        submit_ship.click()
        expect(modal).not_to_be_visible(timeout=5000)
        expect(order_row).to_contain_text("SHIPPED", timeout=5000)
        page.wait_for_timeout(1500)

        # 步驟 3.3: A4 2x2 標籤貼紙彈窗展示
        a4_label_btn = order_row.locator("button:has-text('A4 貼紙')")
        a4_label_btn.hover()
        page.wait_for_timeout(600)
        a4_label_btn.click()

        a4_modal = page.locator("#a4-label-modal")
        expect(a4_modal).to_be_visible()
        page.wait_for_timeout(2500)
        a4_modal.locator("button:has-text('取消')").click()
        expect(a4_modal).not_to_be_visible()
        page.wait_for_timeout(1000)

        # 步驟 3.4: 開立電子發票
        invoice_btn = order_row.locator("button:has-text('開立發票')")
        invoice_btn.hover()
        page.wait_for_timeout(600)
        invoice_btn.click()
        expect(order_row).to_contain_text("COMPLETED", timeout=5000)
        page.wait_for_timeout(2000)

        # ---------------------------------------------------------------------
        # 場景 4: 探吉會計 自動入帳、試算平衡與帳齡 (35~46s)
        # ---------------------------------------------------------------------
        print("🎥 錄製場景 4：探吉會計 自動入帳傳票、試算平衡與帳齡矩陣 (/accounting)...")
        page.goto(f"{BASE_URL}/accounting")
        expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()
        page.wait_for_timeout(1800)

        # 切換至試算表
        tb_tab = page.locator("a[href='/accounting?tab=trial_balance']")
        tb_tab.click()
        expect(page.locator("body")).to_contain_text("借貸嚴格平衡")
        page.wait_for_timeout(2500)

        # 切換至帳齡分析
        aging_tab = page.locator("a[href='/accounting?tab=aging']")
        aging_tab.click()
        expect(page.locator("body")).to_contain_text("帳齡分析")
        page.wait_for_timeout(2000)

        # ---------------------------------------------------------------------
        # 場景 5: 檔案自動化中心與報表串流 (46~52s)
        # ---------------------------------------------------------------------
        print("🎥 錄製場景 5：檔案自動化與 4合1 財務活頁簿串流 (/ai/tools)...")
        page.goto(f"{BASE_URL}/ai/tools")
        expect(page.locator("h1").filter(has_text="檔案自動化").first).to_be_visible()
        page.wait_for_timeout(1500)

        page.locator("#tab-btn-reports").click()
        page.wait_for_timeout(1000)

        with page.expect_download() as download_info:
            page.locator("a:has-text('匯出全套財務營運報表 (.xlsx)')").click()
        download = download_info.value
        report_save = VIDEO_DIR / "financial_executive_report.xlsx"
        download.save_as(str(report_save))
        page.wait_for_timeout(1500)

        # ---------------------------------------------------------------------
        # 場景 6: LINE 智能通路：客戶端手機視角 (52~60s)
        # ---------------------------------------------------------------------
        print("🎥 錄製場景 6：LINE 智能通路客戶端手機視角 (/demo/line)...")
        page.goto(f"{BASE_URL}/demo/line?order_id={order_id}")
        page.wait_for_timeout(4500)

        # 關閉頁面以完成錄影存檔
        video_path = page.video.path()
        page.close()
        context.close()
        browser.close()

    print(f"\n[步驟 4] 錄影原始檔輸出完成: {video_path}")

    # 3. 使用 FFmpeg 轉檔為高品質標準 MP4
    mp4_path = VIDEO_DIR / "3dollar_erp_demo_60s.mp4"
    print(f"\n[步驟 5] 正在透過 FFmpeg 轉換為標準 H.264 MP4: {mp4_path}...")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-preset",
        "fast",
        str(mp4_path),
    ]
    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    file_size_mb = mp4_path.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 75)
    print(f"🎉 錄製與轉檔圓滿完成！")
    print(f"📁 影片輸出路徑: {mp4_path}")
    print(f"📦 檔案大小: {file_size_mb:.2f} MB")
    print("=" * 75)


if __name__ == "__main__":
    record_demo_video()
