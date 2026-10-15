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

PORT = 8024
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


def test_playwright_batch1_suite():
    """Playwright E2E UI verification for Batch 1 (Pure Front-End QOL) in HEADED mode:
    1. Inventory stock table: Merged low-stock button, no '原廠供應商' query param.
    2. Warehouse transfer: Interactive mutual exclusion and auto-swap (Vanilla JS).
    3. CRM Deal creation: Material items optional, default quantity 1, custom expected_amount.
    4. CRM Quotation: Item 1 & Item 2 default quantities reset to 1.
    5. Order Management: '標籤'/'A4貼紙' renamed to '出貨單'/'A4出貨單' in rows and modals.
    """
    test_db_path = PROJECT_ROOT / "test_batch1_playwright.db"
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
        sku="SKU-COFFEE-01",
        name="極品冠軍曼特寧濾掛咖啡",
        base_unit="BOX",
        cost_price=Decimal("120.0"),
        selling_price=Decimal("280.0"),
        safety_stock=20,
    )
    p2 = inv.create_product(
        sku="SKU-TERM-02",
        name="商用多功能智慧終端機",
        base_unit="SET",
        cost_price=Decimal("1200.0"),
        selling_price=Decimal("2500.0"),
        safety_stock=10,
    )

    # Seed initial stock: p1 is low stock (balance = 5 < safety_stock 20)
    inv.adjust_stock(
        warehouse_id="WH-MAIN",
        sku="SKU-COFFEE-01",
        qty_delta=Decimal("5.0"),
        unit_cost=Decimal("120.0"),
        reference_id="INIT-LOW-01",
        notes="低存量示範品項",
    )
    # Seed p2 in store warehouse
    inv.adjust_stock(
        warehouse_id="WH-STORE",
        sku="SKU-TERM-02",
        qty_delta=Decimal("15.0"),
        unit_cost=Decimal("1200.0"),
        reference_id="INIT-STORE-02",
        notes="門市充裕品項",
    )

    # Pre-seed Order for shipment button verification
    order_svc = OrderService(db=db, event_bus=event_bus, inventory_service=inv)
    seeded_order = order_svc.create_order(
        customer_id="CUST-ALPHA-01",
        channel=OrderChannel.DIRECT,
        items=[("SKU-TERM-02", Decimal("2"), Decimal("2500.0"))],
    )
    order_svc.confirm_order(seeded_order.order_id, "WH-STORE")
    order_svc.ship_order(
        order_id=seeded_order.order_id,
        warehouse_id="WH-STORE",
        recipient_name="黃經理",
        recipient_phone="0911-222-333",
        shipping_address="台北市中山區南京東路二段",
    )

    # Pre-seed CRM Contact & Deal
    crm = CrmService(db=db, order_service=order_svc, event_bus=event_bus)
    seeded_contact = crm.create_contact(
        company_name="宏達綠能科技股份有限公司",
        contact_name="陳總經理",
        tax_id="87654321",
        phone="02-23456789",
    )
    seeded_deal = crm.create_deal(
        contact_id=seeded_contact.contact_id,
        title="2026 辦公室設備升級規劃案",
        stage=DealStage.DISCOVERY,
        items=[("SKU-COFFEE-01", Decimal("1"), Decimal("280.0"))],
    )

    app = create_app(db=db, event_bus=event_bus)
    server = start_server_in_thread(app, PORT)
    wait_for_server(BASE_URL)
    print(f"\n[*] Playwright Headed Test Server running at {BASE_URL}")

    with sync_playwright() as p:
        # Mandatory Headed Mode with visual observation
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # =================================================================
            # SCENARIO 1: Inventory Stock Table & Low-Stock Merged Button
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 1/5] Testing Merged Low-Stock Button & URL Query String...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/inventory")
            expect(page.locator("h1").filter(has_text="多倉庫存與雙記帳流水").first).to_be_visible()

            # Locate low stock item row (SKU-COFFEE-01 in stock table)
            row = page.locator("#stock-table-container tr:has-text('SKU-COFFEE-01')").first
            expect(row).to_be_visible()

            # Verify the simplified button exists and contains '⚠️ 低於安全量'
            merged_btn = row.locator("a:has-text('低於安全量')")
            expect(merged_btn).to_be_visible()
            href = merged_btn.get_attribute("href")
            print(f"[*] Verified Merged Low-Stock Button href: {href}")
            assert "supplier_name" not in href, "URL should not contain hardcoded 'supplier_name=原廠供應商'"
            assert "sku=SKU-COFFEE-01" in href, "URL should contain target sku"

            # Click merged button to navigate to procurement
            merged_btn.click()
            page.wait_for_load_state("networkidle")
            assert "/procurement" in page.url, f"Expected /procurement in url, got {page.url}"
            expect(page.locator("h1").filter(has_text="採購與進貨作業中心").first).to_be_visible()

            # Verify supplier name input does not have '原廠供應商'
            supplier_input = page.locator("input[name='supplier_name']")
            supplier_val = supplier_input.input_value()
            print(f"[*] Verified Procurement Supplier Input value: '{supplier_val}'")
            assert supplier_val != "原廠供應商", "Supplier input must not be prefilled with '原廠供應商'"

            # =================================================================
            # SCENARIO 2: Warehouse Transfer Mutual Exclusion & Auto-Swap
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 2/5] Testing Warehouse Transfer Mutual Exclusion & Auto-Swap...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/inventory")
            expect(page.locator("#transfer-from-warehouse")).to_be_visible()
            expect(page.locator("#transfer-to-warehouse")).to_be_visible()

            from_sel = page.locator("#transfer-from-warehouse")
            to_sel = page.locator("#transfer-to-warehouse")

            # Check initial state: from is WH-MAIN, to is WH-STORE
            assert from_sel.input_value() == "WH-MAIN"
            assert to_sel.input_value() == "WH-STORE"

            # Check disabled state in to_sel for WH-MAIN
            is_main_disabled_in_to = page.evaluate("() => document.querySelector('#transfer-to-warehouse option[value=\"WH-MAIN\"]').disabled")
            print(f"[*] Initial disabled state of WH-MAIN in to_warehouse: {is_main_disabled_in_to}")
            assert is_main_disabled_in_to is True, "Selected from_warehouse should be disabled in to_warehouse"

            # Action: Change from_warehouse to WH-STORE (which matches current to_warehouse)
            print("[*] Changing from_warehouse to WH-STORE (expect auto-swap)...")
            from_sel.select_option("WH-STORE")
            time.sleep(0.5)

            # Expected Outcome: to_warehouse auto-swapped to WH-MAIN!
            new_to_val = to_sel.input_value()
            print(f"[*] After selection, to_warehouse auto-swapped to: {new_to_val}")
            assert new_to_val == "WH-MAIN", f"Expected to_warehouse to auto-swap to WH-MAIN, got {new_to_val}"

            # Verify WH-STORE is now disabled in to_warehouse
            is_store_disabled_in_to = page.evaluate("() => document.querySelector('#transfer-to-warehouse option[value=\"WH-STORE\"]').disabled")
            assert is_store_disabled_in_to is True

            # Action: Change from_warehouse back to WH-MAIN (which matches current to_warehouse)
            print("[*] Changing from_warehouse back to WH-MAIN (expect to_warehouse to auto-swap)...")
            from_sel.select_option("WH-MAIN")
            time.sleep(0.5)
            new_to_val = to_sel.input_value()
            print(f"[*] After selection, to_warehouse auto-swapped to: {new_to_val}")
            assert new_to_val == "WH-STORE", f"Expected to_warehouse to auto-swap to WH-STORE, got {new_to_val}"

            # =================================================================
            # SCENARIO 3: CRM Deal Creation - Optional Materials & Default Qty
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 3/5] Testing CRM Deal Creation with Optional Materials & Default Qty...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/crm")
            expect(page.locator("h1").filter(has_text="哩來 (LiLai) CRM 前段商機與文件中心").first).to_be_visible()

            # Click '建立新商機' button
            page.locator("button:has-text('建立新商機')").first.click()
            modal = page.locator("#modal-new-deal")
            expect(modal).to_be_visible()

            # Verify title is '商機預估物料明細 1 (選填)'
            expect(modal.locator("text=商機預估物料明細 1 (選填)")).to_be_visible()

            # Verify default values
            qty_1_val = modal.locator("#deal_qty_1").input_value()
            price_1_val = modal.locator("#deal_price_1").input_value()
            print(f"[*] Verified New Deal default qty_1: {qty_1_val}, price_1: {price_1_val}")
            assert qty_1_val == "1", f"Expected default qty_1 to be '1', got {qty_1_val}"
            assert price_1_val == "0", f"Expected default price_1 to be '0', got {price_1_val}"

            # Select customer
            modal.locator("#deal-contact-select").select_option(value=seeded_contact.contact_id)

            # Fill title
            deal_title = "2026 全雲端架構顧問諮詢專案"
            modal.locator("input[name='title']").fill(deal_title)

            # Leave sku_1 empty (select default '-- 無特定預估品項 (選填) --')
            modal.locator("select[name='sku_1']").select_option(value="")

            # Fill custom expected amount
            modal.locator("#deal-manual-expected-amount").fill("98000")
            time.sleep(0.3)

            # Verify total display updated to 98,000
            total_display = modal.locator("#deal-total-display").inner_text()
            print(f"[*] Calculated expected total display: {total_display}")
            assert "98,000" in total_display

            # Submit deal
            modal.locator("button:has-text('建立商機')").click()
            time.sleep(1.0)

            # Verify deal card appears on Kanban with custom expected amount
            new_deal_card = page.locator(f"div:has-text('{deal_title}')").first
            expect(new_deal_card).to_be_visible()
            expect(new_deal_card).to_contain_text("NT$ 98,000")
            print(f"[*] Verified Deal card successfully created without required materials!")

            # =================================================================
            # SCENARIO 4: CRM Quotation Generator - Default Quantities Reset to 1
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 4/5] Testing CRM Quotation Modal Default Quantities (Reset to 1)...")
            print("=" * 70)

            # Open quotation modal on the seeded deal
            target_deal_card = page.locator(f"#deal-card-{seeded_deal.deal_id}")
            expect(target_deal_card).to_be_visible()
            target_deal_card.locator("button:has-text('報價單')").click()

            quote_modal = page.locator("#modal-new-quote")
            expect(quote_modal).to_be_visible()

            # Verify qty_1 and qty_2 default values
            quote_qty_1 = quote_modal.locator("input[name='qty_1']").input_value()
            quote_qty_2 = quote_modal.locator("input[name='qty_2']").input_value()
            print(f"[*] Verified Quotation Modal default qty_1: '{quote_qty_1}', qty_2: '{quote_qty_2}'")
            assert quote_qty_1 == "1", f"Expected quote qty_1 to be '1', got {quote_qty_1}"
            assert quote_qty_2 == "1", f"Expected quote qty_2 to be '1', got {quote_qty_2}"

            # Cancel modal
            quote_modal.locator("button:has-text('取消')").click()
            expect(quote_modal).not_to_be_visible()

            # =================================================================
            # SCENARIO 5: Orders Management - Label to Delivery Order Renaming
            # =================================================================
            print("\n" + "=" * 70)
            print("[Scenario 5/5] Testing Orders Management Document Renaming (標籤 ➔ 出貨單)...")
            print("=" * 70)
            page.goto(f"{BASE_URL}/orders")
            expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

            # Locate seeded order row (SHIPPED)
            order_row = page.locator(f"#order-row-{seeded_order.order_id}")
            expect(order_row).to_be_visible()

            # Verify renamed action buttons
            do_btn = order_row.locator("a:has-text('🏷️ 出貨單')")
            a4_btn = order_row.locator("button:has-text('📄 A4 出貨單')")
            expect(do_btn).to_be_visible()
            expect(a4_btn).to_be_visible()
            print("[*] Verified row buttons: '🏷️ 出貨單' and '📄 A4 出貨單' are visible!")

            # Click '📄 A4 出貨單' to open A4 modal
            a4_btn.click()
            a4_modal = page.locator("#a4-label-modal")
            expect(a4_modal).to_be_visible()
            expect(a4_modal).to_contain_text("A4 出貨單起印設定 (2x2 多格出貨單)")
            expect(a4_modal).to_contain_text("標準 A4 4格出貨單")
            expect(a4_modal.locator("button:has-text('📄 產生並開啟 A4 出貨單 PDF')")).to_be_visible()
            print("[*] Verified A4 Modal titles and button text!")
            a4_modal.locator("button:has-text('取消')").click()

            # Click DO history link to open deliveries modal
            order_row.locator("button:has-text('DO-')").first.click()
            deliv_modal = page.locator("#deliveries-modal")
            expect(deliv_modal).to_be_visible()
            expect(deliv_modal.locator("a:has-text('🏷️ 100x150 出貨單')").first).to_be_visible()
            expect(deliv_modal.locator("button:has-text('📄 A4 出貨單 (選格位)')").first).to_be_visible()
            print("[*] Verified Deliveries Modal button text: '🏷️ 100x150 出貨單' and '📄 A4 出貨單 (選格位)'!")
            deliv_modal.locator("button:has-text('關閉視窗')").click()

            print("\n" + "=" * 70)
            print(">>> ALL 5 PLAYWRIGHT HEADED UI SCENARIOS PASSED WITH FULL VISUAL FIDELITY! <<<")
            print("=" * 70)

        finally:
            context.close()
            browser.close()
            if test_db_path.exists():
                try:
                    test_db_path.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    test_playwright_batch1_suite()
