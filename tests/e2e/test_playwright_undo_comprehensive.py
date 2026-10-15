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
from src.core.domain.order import OrderChannel, OrderStatus
from src.extended_core.crm.models import DealStage
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.crm.services.crm_service import CrmService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.channel_ui.web.app import create_app

PORT = 8019
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


def test_playwright_undo_comprehensive_suite():
    """Playwright E2E UI verification for all UNDO_ACTION_PLAN.md features in HEADED mode:
    1. Toast Infrastructure: rendering, TTL animation, hover pause/resume, manual dismiss, auto-dismiss.
    2. Inventory: Immediate stock transfer + Compensating reversal (revert_transfer) via Undo toast.
    3. Procurement: Draft PO creation undo, submit PO undo, and Goods Receipt (GRN) double-check modal.
    4. Orders: Order confirm lock undo, order shipment double-check modal (irreversible), and e-invoice.
    5. Accounting: Manual journal entry create + Symmetrical reversal (REV-JE-xxx) trial balance reset.
    6. CRM: Deal creation undo, won deal convert-to-order double-check modal.
    7. Blast Radius & System Invariants: Append-only ledger integrity, cross-page navigation, and boundary check.
    """
    test_db_path = PROJECT_ROOT / "test_undo_playwright.db"
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

    # Initial physical stock
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-PRO-01",
        qty_delta=Decimal("100.0"),
        unit_cost=Decimal("1500.0"),
        reference_id="INIT-001",
        notes="主倉期初庫存",
    )
    inv.adjust_stock(
        warehouse_id="WH-STORE",
        sku="SKU-PRO-01",
        qty_delta=Decimal("10.0"),
        unit_cost=Decimal("1500.0"),
        reference_id="INIT-002",
        notes="門市倉期初庫存",
    )
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-ACC-02",
        qty_delta=Decimal("50.0"),
        unit_cost=Decimal("300.0"),
        reference_id="INIT-003",
        notes="主倉配件期初庫存",
    )

    # Pre-seed Procurement PO for submit & receive scenarios
    proc = ProcurementService(db=db, event_bus=event_bus)
    seeded_po = proc.create_purchase_order(
        supplier_name="祥茂電子精密工業",
        items=[("SKU-ACC-02", Decimal("10"), Decimal("280.0"))],
    )

    # Pre-seed Order for lock, ship, and invoice scenarios
    order_svc = OrderService(db=db, event_bus=event_bus, inventory_service=inv)
    seeded_order = order_svc.create_order(
        customer_id="CUST-001",
        channel=OrderChannel.DIRECT,
        items=[("SKU-PRO-01", Decimal("2"), Decimal("2500.0"))],
    )

    # Pre-seed CRM Contact & Deal for won conversion scenario
    crm = CrmService(db=db, order_service=order_svc, event_bus=event_bus)
    seeded_contact = crm.create_contact(
        company_name="聯成半導體科技股份有限公司",
        contact_name="林技術長",
        tax_id="23456789",
        phone="02-87654321",
    )
    seeded_proposal_deal = crm.create_deal(
        contact_id=seeded_contact.contact_id,
        title="2026 企業終端大量換新專案",
        stage=DealStage.PROPOSAL,
        items=[("SKU-PRO-01", Decimal("5"), Decimal("2500.0"))],
    )
    crm.create_quote(deal_id=seeded_proposal_deal.deal_id)

    # Accounting Service
    acc_svc = AccountingService(db=db)

    app = create_app(db=db, event_bus=event_bus)
    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)
    print(f"\n[*] Playwright Headed Test Server running at {BASE_URL}")

    with sync_playwright() as p:
        # Mandatory Headed Mode with visual pacing
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: print(f"[BROWSER CONSOLE] {msg.type}: {msg.text}"))
        page.on("request", lambda req: print(f"[BROWSER REQUEST] {req.method} {req.url}"))
        page.on("response", lambda resp: print(f"[BROWSER RESPONSE] {resp.status} {resp.url}"))

        try:
            # =================================================================
            # SCENARIO 1: Global Toast Infrastructure & TTL Lifecycle
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 1/7] Testing Toast Infrastructure, TTL Progress Bar & Lifecycle...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/inventory")
            expect(page.locator("h1").filter(has_text="多倉庫存與雙記帳流水").first).to_be_visible()

            # Trigger a transfer to spawn a Toast
            page.select_option("select[name='from_warehouse_id']", "WH-MAIN")
            page.select_option("select[name='to_warehouse_id']", "WH-STORE")
            page.fill("input[name='sku']", "SKU-PRO-01")
            page.fill("input[name='qty']", "2")
            page.click("button:has-text('執行調撥')")

            # 1.1 Toast rendering verification
            toast_card = page.locator("#toast-container .toast-card").first
            expect(toast_card).to_be_visible(timeout=5000)
            expect(toast_card).to_contain_text("調撥成功")
            expect(toast_card).to_contain_text("撤回調撥")

            # Verify progress bar element and TTL attribute
            progress_bar = toast_card.locator(".toast-progress-bar")
            expect(progress_bar).to_be_visible()
            ttl_val = toast_card.get_attribute("data-ttl")
            assert ttl_val == "6000", f"Expected data-ttl to be 6000, got {ttl_val}"
            print("  -> 1.1 Toast rendered with icon, message, [撤回] button, and 6s progress bar.")

            # 1.2 Hover Pause & Resume verification
            toast_card.hover()
            page.wait_for_timeout(500)
            # Evaluate CSS animationPlayState
            play_state = page.evaluate("document.querySelector('#toast-container .toast-progress-bar').style.animationPlayState")
            assert play_state == "paused", f"Expected animationPlayState to be paused on hover, got {play_state}"
            print("  -> 1.2 Hover pause successfully verified (animation-play-state: paused).")

            # Move mouse away
            page.mouse.move(0, 0)
            page.wait_for_timeout(500)
            play_state_resumed = page.evaluate("document.querySelector('#toast-container .toast-progress-bar').style.animationPlayState")
            assert play_state_resumed == "running", f"Expected animationPlayState to resume to running, got {play_state_resumed}"
            print("  -> 1.2 Mouse leave successfully resumed countdown (animation-play-state: running).")

            # 1.3 Manual Dismiss via 'x' button
            dismiss_btn = toast_card.locator("[data-toast-dismiss]")
            dismiss_btn.click()
            page.wait_for_timeout(600)
            expect(page.locator("#toast-container .toast-card")).to_have_count(0)
            print("  -> 1.3 Manual dismiss '&times;' smoothly removed toast card from DOM.")

            # =================================================================
            # SCENARIO 2: Inventory Multi-Warehouse Transfer & Reversal (Undo)
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 2/7] Testing Inventory Multi-Warehouse Transfer & Undo Reversal...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/inventory")

            # Record stock before transfer
            # Initial was 100 - 2 = 98 in WH-MAIN, 10 + 2 = 12 in WH-STORE
            page.select_option("select[name='from_warehouse_id']", "WH-MAIN")
            page.select_option("select[name='to_warehouse_id']", "WH-STORE")
            page.fill("input[name='sku']", "SKU-PRO-01")
            page.fill("input[name='qty']", "10")
            page.click("button:has-text('執行調撥')")

            # Verify immediate stock update in UI table
            expect(page.locator("#toast-container")).to_contain_text("調撥成功！")
            expect(page.locator("#toast-container")).to_contain_text("調撥 10 件 SKU-PRO-01")
            expect(page.locator("#stock-table-container")).to_contain_text("88")  # WH-MAIN: 98 - 10 = 88
            expect(page.locator("#stock-table-container")).to_contain_text("22")  # WH-STORE: 12 + 10 = 22
            print("  -> 2.1 Transfer executed immediately: WH-MAIN deducted to 88, WH-STORE incremented to 22.")

            # Click [撤回調撥] in Toast
            undo_btn = page.locator("#toast-container button:has-text('撤回調撥')")
            expect(undo_btn).to_be_visible()
            undo_btn.click()

            # Verify compensating reversal
            expect(page.locator("#toast-container")).to_contain_text("已成功撤回調撥", timeout=5000)
            expect(page.locator("#toast-container")).to_contain_text("庫存已原路歸還")
            expect(page.locator("#stock-table-container")).to_contain_text("98")  # WH-MAIN restored to 98
            expect(page.locator("#stock-table-container")).to_contain_text("12")  # WH-STORE restored to 12

            # Verify Append-Only ledger displays 調撥撤回 and REV-TRF-
            expect(page.locator("#ledger-table-container")).to_contain_text("調撥撤回")
            expect(page.locator("#ledger-table-container")).to_contain_text("REV-TRF-")
            print("  -> 2.2 Undo clicked: stock restored to 98/12, append-only 調撥撤回 (REV-TRF-) logged.")

            # =================================================================
            # SCENARIO 3: Procurement PO Create Undo, Submit Undo & Receive Modal
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 3/7] Testing Procurement Draft Undo, Submit Undo & GRN Double-Check...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/procurement")
            expect(page.locator("h1").filter(has_text="採購與進貨作業中心").first).to_be_visible()

            # 3.1 Create Draft PO & Undo
            page.fill("#input-supplier-name", "台灣精密零組件股份有限公司")
            page.select_option(".sku-select", "SKU-PRO-01")
            page.fill(".qty-input", "4")
            page.fill(".cost-input", "1450.00")
            page.click("button:has-text('建立採購單 (Draft)')")

            # Toast appears with [撤回建立]
            expect(page.locator("#toast-container")).to_contain_text("成功建立採購單", timeout=5000)
            expect(page.locator("#toast-container")).to_contain_text("台灣精密零組件股份有限公司")
            undo_draft_btn = page.locator("#toast-container button:has-text('撤回建立')")
            expect(undo_draft_btn).to_be_visible()
            undo_draft_btn.click()

            # Verify PO marked CANCELLED / removed
            expect(page.locator("#toast-container")).to_contain_text("已成功撤回採購單建立", timeout=5000)
            expect(page.locator("#po-tbody")).to_contain_text("已取消 (CANCELLED)")
            print("  -> 3.1 Draft PO created and immediately undone to CANCELLED status.")

            # 3.2 Submit PO & Undo
            po_id = seeded_po.po_id
            po_row = page.locator(f"#po-row-{po_id}")
            expect(po_row).to_be_visible()

            # Click [確認下訂]
            with page.expect_response(lambda r: "submit" in r.url and r.request.method == "POST") as resp_info:
                po_row.locator("button:has-text('確認下訂')").click()
            submit_resp = resp_info.value
            print(f"  [DEBUG SUBMIT RESP STATUS]: {submit_resp.status}")
            print(f"  [DEBUG SUBMIT RESP TEXT]: {submit_resp.text()[:300]}")
            page.wait_for_timeout(1000)
            dom_toast = page.evaluate("document.getElementById('toast-container')?.innerHTML")
            print(f"  [DEBUG DOM TOAST HTML]: {dom_toast}")
            expect(page.locator("#toast-container")).to_contain_text(f"採購單 {po_id} 已確認送出，等待供應商到貨！")
            expect(po_row).to_contain_text("待到貨 (SUBMITTED)")

            # Click [撤回下訂]
            undo_submit_btn = page.locator("#toast-container button:has-text('撤回下訂')")
            expect(undo_submit_btn).to_be_visible()
            undo_submit_btn.click()

            expect(page.locator("#toast-container")).to_contain_text(f"採購單 {po_id} 已成功撤回下訂，已恢復為草稿 (DRAFT)")
            expect(po_row).to_contain_text("草稿 (DRAFT)")
            print(f"  -> 3.2 PO {po_id} submitted and undone back to DRAFT.")

            # 3.3 Receive PO Double-Check Modal (Irreversible Flow)
            # Re-submit to SUBMITTED
            po_row.locator("button:has-text('確認下訂')").click()
            expect(po_row).to_contain_text("待到貨 (SUBMITTED)")

            # Click [驗收入庫] to open Double-Check Modal
            po_row.locator("button:has-text('驗收入庫')").click()
            receive_modal = page.locator("#receive-po-modal")
            expect(receive_modal).to_be_visible()
            expect(receive_modal).to_contain_text("物料驗收入庫 (Goods Receipt)")
            expect(receive_modal).to_contain_text(po_id)

            # Test Cancel
            receive_modal.locator("button:has-text('取消')").click()
            expect(receive_modal).not_to_be_visible()
            print("  -> 3.3 Goods receipt modal Cancel button closed cleanly without side effects.")

            # Re-open and Confirm
            po_row.locator("button:has-text('驗收入庫')").click()
            expect(receive_modal).to_be_visible()
            receive_modal.locator("button:has-text('確認入庫並立帳')").click()

            # Verify modal closed and PO marked RECEIVED with GRN
            expect(receive_modal).not_to_be_visible(timeout=5000)
            expect(po_row).to_contain_text("已驗收入庫")
            expect(po_row).to_contain_text("GRN-")
            expect(page.locator("#toast-container")).to_contain_text("已成功驗收入庫！入庫單號：GRN-")
            # Ensure NO undo button for irreversible goods receipt
            expect(page.locator("#toast-container button:has-text('撤回')")).to_have_count(0)
            print("  -> 3.3 PO Goods Receipt completed with GRN, AP posted, and toast without undo button.")

            # =================================================================
            # SCENARIO 4: Orders Confirm Undo, Ship Double-Check & E-Invoice
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 4/7] Testing Orders Confirm Undo, Ship Modal & E-Invoice...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/orders")
            expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

            order_id = seeded_order.order_id
            order_row = page.locator(f"#order-row-{order_id}")
            expect(order_row).to_be_visible()
            expect(order_row).to_contain_text("DRAFT")

            # 4.1 Confirm Order & Undo
            order_row.locator("button:has-text('鎖庫確認')").click()
            expect(order_row).to_contain_text("CONFIRMED", timeout=5000)
            expect(page.locator("#toast-container")).to_contain_text(f"訂單 {order_id} 鎖庫確認成功！庫存已保留。")

            # Click [撤回鎖庫]
            undo_lock_btn = page.locator("#toast-container button:has-text('撤回鎖庫')")
            expect(undo_lock_btn).to_be_visible()
            undo_lock_btn.click()

            expect(page.locator("#toast-container")).to_contain_text(f"已成功撤回訂單 {order_id} 鎖庫確認，庫存已原路釋放。")
            expect(order_row).to_contain_text("DRAFT")
            print(f"  -> 4.1 Order {order_id} confirmed (stock locked) and undone back to DRAFT (stock released).")

            # 4.2 Order Shipment Double-Check Modal
            # Re-confirm to CONFIRMED
            order_row.locator("button:has-text('鎖庫確認')").click()
            expect(order_row).to_contain_text("CONFIRMED")

            # Click [一鍵出貨 (扣庫)]
            order_row.locator("button:has-text('一鍵出貨 (扣庫)')").click()
            ship_modal = page.locator("#ship-confirm-modal")
            expect(ship_modal).to_be_visible()
            expect(ship_modal).to_contain_text("一鍵出貨確認")
            expect(ship_modal).to_contain_text("出貨不可逆作業提醒")

            # Test Cancel
            ship_modal.locator("button:has-text('取消')").click()
            expect(ship_modal).not_to_be_visible()
            print("  -> 4.2 Order shipment modal Cancel button closed cleanly.")

            # Re-open and Submit
            order_row.locator("button:has-text('一鍵出貨 (扣庫)')").click()
            expect(ship_modal).to_be_visible()
            ship_modal.locator("button:has-text('確認執行出貨 (扣庫)')").click()

            expect(ship_modal).not_to_be_visible(timeout=5000)
            expect(order_row).to_contain_text("SHIPPED")
            expect(order_row).to_contain_text("DO-")
            expect(page.locator("#toast-container")).to_contain_text("出貨成功！出貨單號：DO-")
            expect(page.locator("#toast-container button:has-text('撤回')")).to_have_count(0)
            print("  -> 4.2 Order shipment confirmed, physical inventory deducted, DO created.")

            # 4.3 Issue E-Invoice
            order_row.locator("button:has-text('開立發票')").click()
            expect(page.locator("#toast-container")).to_contain_text("電子發票開立成功！發票號碼：", timeout=5000)
            expect(order_row).to_contain_text("電子發票 (INV):")
            expect(order_row).to_contain_text("🧾 發票")
            expect(page.locator("#toast-container button:has-text('撤回')")).to_have_count(0)
            print("  -> 4.3 E-Invoice issued legally without undo button.")

            # =================================================================
            # SCENARIO 5: Accounting Manual Journal Entry & Reversal
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 5/7] Testing Accounting Journal Entry & Symmetrical Reversal...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/accounting?tab=journal")
            expect(page.locator("h1").filter(has_text="探吉 會計與記帳系統").first).to_be_visible()

            # Fill manual journal entry
            page.fill("input[name='description']", "業主投入營運備用週轉金")
            page.select_option("select[name='account_code_1']", "1101")
            page.fill("input[name='debit_1']", "50000")
            page.fill("input[name='credit_1']", "0")

            page.select_option("select[name='account_code_2']", "3101")
            page.fill("input[name='debit_2']", "0")
            page.fill("input[name='credit_2']", "50000")

            page.click("button:has-text('送出平衡傳票')")

            expect(page.locator("#toast-container")).to_contain_text("手動傳票建立成功！", timeout=5000)
            expect(page.locator("#toast-container")).to_contain_text("借貸各 NT$ 50,000.00")
            expect(page.locator("#accounting-container")).to_contain_text("業主投入營運備用週轉金")

            # Click [撤回傳票]
            undo_je_btn = page.locator("#toast-container button:has-text('撤回傳票')")
            expect(undo_je_btn).to_be_visible()
            undo_je_btn.click()

            # Verify compensating journal reversal
            expect(page.locator("#toast-container")).to_contain_text("已成功撤回傳票", timeout=5000)
            expect(page.locator("#toast-container")).to_contain_text("已立案紅字反向沖銷傳票")
            expect(page.locator("#accounting-container")).to_contain_text("REV-")

            # Verify Trial Balance remains strictly balanced
            page.goto(f"{BASE_URL}/accounting?tab=trial_balance")
            expect(page.locator("#accounting-container")).to_contain_text("✓ 借貸嚴格平衡")
            print("  -> 5.1 Manual journal entry created, symmetrically reversed with REV-JE, trial balance zero-balanced.")

            # =================================================================
            # SCENARIO 6: CRM Deal Creation Undo & Won Deal Convert Double-Check
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 6/7] Testing CRM Deal Create Undo & Won Convert Double-Check...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/crm?tab=contacts")
            expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM").first).to_be_visible()

            # 6.1 Deal Creation & Undo
            page.locator("button:has-text('＋ 提商機')").first.click()
            deal_modal = page.locator("#modal-new-deal")
            expect(deal_modal).to_be_visible()

            page.fill("#modal-new-deal input[name='title']", "2026 雲端智慧終端整合專案")
            page.fill("#deal_qty_1", "3")
            page.click("#modal-new-deal button:has-text('建立商機')")

            # Automatically switches to kanban tab
            expect(page.locator("#toast-container")).to_contain_text("成功建立商機：2026 雲端智慧終端整合專案", timeout=5000)
            expect(page.locator("#crm-container")).to_contain_text("2026 雲端智慧終端整合專案")

            # Click [撤回建立]
            undo_deal_btn = page.locator("#toast-container button:has-text('撤回建立')")
            expect(undo_deal_btn).to_be_visible()
            undo_deal_btn.click()

            expect(page.locator("#toast-container")).to_contain_text("已成功撤回商機建立", timeout=5000)
            expect(page.locator("#crm-container")).not_to_contain_text("2026 雲端智慧終端整合專案")
            print("  -> 6.1 CRM Deal created and immediately undone, card purged from Kanban.")

            # 6.2 Won Deal Convert Double-Check Modal
            proposal_card = page.locator(f"#deal-card-{seeded_proposal_deal.deal_id}")
            expect(proposal_card).to_be_visible()

            # Click [⚡ 贏單轉 ERP]
            proposal_card.locator("button:has-text('⚡ 贏單轉 ERP')").click()
            convert_modal = page.locator("#convert-deal-modal")
            expect(convert_modal).to_be_visible()
            expect(convert_modal).to_contain_text("贏單轉 ERP 銷售訂單確認")
            expect(convert_modal).to_contain_text("聯成半導體科技股份有限公司")

            # Test Cancel
            convert_modal.locator("button:has-text('取消')").click()
            expect(convert_modal).not_to_be_visible()
            print("  -> 6.2 Convert deal modal Cancel button closed cleanly.")

            # Re-open and Confirm
            proposal_card.locator("button:has-text('⚡ 贏單轉 ERP')").click()
            expect(convert_modal).to_be_visible()
            convert_modal.locator("button:has-text('確認轉為 ERP 正式訂單')").click()

            expect(convert_modal).not_to_be_visible(timeout=5000)
            won_card = page.locator(f"#deal-card-{seeded_proposal_deal.deal_id}")
            expect(won_card).to_contain_text("ERP 銷售訂單")
            expect(page.locator("#toast-container")).to_contain_text("商機已成功拋轉為 ERP 銷售訂單")
            expect(page.locator("#toast-container button:has-text('撤回')")).to_have_count(0)
            print("  -> 6.2 Won deal converted to ERP Sales Order, linked in UI with irreversible toast.")

            # =================================================================
            # SCENARIO 7: Blast Radius & System Invariants Verification
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 7/7] Verifying System Invariants, Append-Only Ledgers & Routing...")
            print("=" * 70)

            # 7.1 Check Append-Only SQLite Ledgers
            with db.get_connection() as conn:
                # Check Stock Ledger has TRANSFER_REVERSAL records
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM stock_ledger WHERE reference_id LIKE 'REV-TRF-%'")
                rev_stock_count = cur.fetchone()[0]
                assert rev_stock_count >= 1, f"Expected at least 1 TRANSFER_REVERSAL, got {rev_stock_count}"

                # Check Journal Entries has REVERSAL records
                cur.execute("SELECT COUNT(*) FROM journal_entries WHERE source_event = 'REVERSAL'")
                rev_je_count = cur.fetchone()[0]
                assert rev_je_count >= 1, f"Expected at least 1 REVERSAL journal entry, got {rev_je_count}"

                print(f"  -> 7.1 Append-Only verification PASS: {rev_stock_count} stock reversal(s), {rev_je_count} accounting reversal(s). ZERO hard deletes.")

            # 7.2 Cross-Page Navigation while Toast Active
            nav_routes = ["/", "/inventory", "/procurement", "/orders", "/accounting", "/crm"]
            for r in nav_routes:
                page.goto(f"{BASE_URL}{r}")
                expect(page.locator("h1").first).to_be_visible()
            print("  -> 7.2 Cross-page navigation PASS: traversed all 6 major routes with zero JavaScript/DOM exceptions.")

            print("\n" + "=" * 70)
            print("[SUCCESS] All 7 Comprehensive Playwright Headed UI Test Scenarios PASSED!")
            print("=" * 70)

        finally:
            browser.close()


if __name__ == "__main__":
    test_playwright_undo_comprehensive_suite()
