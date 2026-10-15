from __future__ import annotations
from decimal import Decimal
import os
import re
from pathlib import Path
import fitz
import pytest
from playwright.sync_api import Page, expect

from src.core.domain.order import OrderChannel
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import InMemoryEventBus

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


def test_batch1_playwright_full_ui_flow(page: Page, tmp_path: Path):
    """Playwright E2E verification for Full Expansion Batch 1 UI features:
    1. A4 2x2 Multi-Label Sticker Sheet Streaming and Dimension Verification.
    2. Partial Shipment (1:N Fulfillment) UI Modal, Input Validation & Overshipment Error Handling.
    3. State Machine Progression: CONFIRMED -> PARTIALLY_SHIPPED -> SHIPPED -> COMPLETED.
    4. Multi-Module Navigation and Dual-Engine Stability Check across all core tabs.
    """

    # Setup a dedicated multi-item test order directly in DB
    db = Database()
    event_bus = InMemoryEventBus()
    inv_service = InventoryService(db=db)
    order_service = OrderService(db=db, inventory_service=inv_service, event_bus=event_bus)

    # Ensure stock is available
    inv_service.adjust_stock("WH-MAIN", "SKU-PRO-01", Decimal("20.0"), Decimal("1500.0"), "TEST-BATCH1", "Test stock")
    inv_service.adjust_stock("WH-MAIN", "SKU-ACC-02", Decimal("20.0"), Decimal("300.0"), "TEST-BATCH1", "Test stock")

    test_order = order_service.create_order(
        customer_id="CUST-PLAYWRIGHT-TEST",
        items=[
            ("SKU-PRO-01", Decimal("3.0"), Decimal("2500.0")),
            ("SKU-ACC-02", Decimal("2.0"), Decimal("650.0")),
        ],
        channel=OrderChannel.DIRECT,
    )
    order_service.confirm_order(test_order.order_id, "WH-MAIN")

    try:
        # -------------------------------------------------------------------------
        # 1. Orders Page Load & Initial State Verification
        # -------------------------------------------------------------------------
        page.goto(f"{BASE_URL}/orders")
        expect(page.locator("h1").filter(has_text="訂單與出貨作業中心").first).to_be_visible()

        target_row = page.locator(f"#order-row-{test_order.order_id}")
        expect(target_row).to_be_visible()
        expect(target_row).to_contain_text("CONFIRMED")
        expect(target_row.locator("button:has-text('拆批出貨')")).to_be_visible()

        # -------------------------------------------------------------------------
        # 2. 1:N Partial Shipment UI Modal & Overshipment Error Handling
        # -------------------------------------------------------------------------
        # Click "拆批出貨" to open the modal
        target_row.locator("button:has-text('拆批出貨')").click()
        modal = page.locator("#partial-ship-modal")
        expect(modal).to_be_visible()
        expect(modal).to_contain_text("拆批出貨 (Partial Fulfillment)")
        expect(modal).to_contain_text("SKU-PRO-01")
        expect(modal).to_contain_text("SKU-ACC-02")

        # Test Case 2-A: Overshipment Error (submit qty 99 > remaining 3)
        input_item1 = modal.locator("input[name^='qty_']").first
        input_item1.fill("99")
        modal.locator("button:has-text('確認拆批出貨')").click()

        # Verify Toast error appears
        toast = page.locator("#toast-container")
        expect(toast).to_contain_text("超過剩餘未出量", timeout=5000)
        expect(modal).to_be_visible()  # Modal remains open

        # Test Case 2-B: Valid Partial Shipment (ship 1 unit of SKU-PRO-01, 0 of SKU-ACC-02)
        inputs = modal.locator("input[name^='qty_']").all()
        inputs[0].fill("1")
        if len(inputs) > 1:
            inputs[1].fill("0")
        modal.locator("button:has-text('確認拆批出貨')").click()

        # Verify modal is closed and row updated via HTMX to PARTIALLY_SHIPPED
        expect(modal).not_to_be_visible()
        expect(target_row.locator("span:text-is('PARTIALLY_SHIPPED')")).to_be_visible(timeout=5000)
        expect(target_row.locator("button:has-text('拆批出貨')")).to_be_visible()
        expect(target_row.locator("button:has-text('一鍵出貨 (扣庫)')")).to_be_visible()
        expect(target_row.locator("button:has-text('📄 A4 貼紙')")).to_be_visible()

        # -------------------------------------------------------------------------
        # 3. A4 Multi-Label Starting Slot Selection Modal (2x2 Grid)
        # -------------------------------------------------------------------------
        target_row.locator("button:has-text('📄 A4 貼紙')").click()
        a4_modal = page.locator("#a4-label-modal")
        expect(a4_modal).to_be_visible()
        expect(a4_modal).to_contain_text("A4 標籤紙起印設定 (2x2 多格貼紙)")
        expect(a4_modal).to_contain_text("第 1 格")
        expect(a4_modal).to_contain_text("第 2 格")
        expect(a4_modal).to_contain_text("第 3 格")
        expect(a4_modal).to_contain_text("第 4 格")

        # Select Slot 3 (左下)
        a4_modal.locator("label:has-text('第 3 格')").click()

        # Submit form to open PDF popup
        with page.expect_popup() as popup_info:
            a4_modal.locator("button:has-text('產生並開啟 A4 貼紙 PDF')").click()
        popup = popup_info.value
        popup.wait_for_url(re.compile(r"start_pos=3"), timeout=5000)
        popup_url = popup.url
        popup.close()

        # Verify requested start_pos was passed and PDF dimensions
        assert "start_pos=3" in popup_url
        pdf_resp = page.request.get(popup_url)
        assert pdf_resp.status == 200
        doc = fitz.open(stream=pdf_resp.body(), filetype="pdf")
        assert len(doc) >= 1
        rect = doc[0].rect
        assert round(rect.width, 1) == 595.3
        assert round(rect.height, 1) == 841.9
        doc.close()

        # Verify a4_modal automatically closes
        expect(a4_modal).not_to_be_visible(timeout=5000)

        # -------------------------------------------------------------------------
        # 4. Ship Remainder & Verify 1:N Delivery History Modal
        # -------------------------------------------------------------------------
        # Ship remaining items via 一鍵出貨
        target_row.locator("button:has-text('一鍵出貨 (扣庫)')").click()
        expect(target_row.locator("span:text-is('SHIPPED')")).to_be_visible(timeout=5000)

        # Verify DO column displays "2 批出貨歷程"
        history_btn = target_row.locator("button:has-text('2 批出貨歷程')")
        expect(history_btn).to_be_visible()

        # Open 1:N Deliveries History Modal
        history_btn.click()
        deliv_modal = page.locator("#deliveries-modal")
        expect(deliv_modal).to_be_visible()
        expect(deliv_modal).to_contain_text("出貨單紀錄與歷程 (Delivery Fulfillment History)")
        expect(deliv_modal).to_contain_text("累計出貨批次：2 批")
        expect(deliv_modal).to_contain_text("SKU-PRO-01")
        expect(deliv_modal).to_contain_text("SKU-ACC-02")
        expect(deliv_modal.locator("a:has-text('🏷️ 100x150 標籤')").first).to_be_visible()
        expect(deliv_modal.locator("button:has-text('📄 A4 貼紙 (選格位)')").first).to_be_visible()

        # Close Deliveries Modal
        deliv_modal.locator("button:has-text('關閉視窗')").click()
        expect(deliv_modal).not_to_be_visible()

        # -------------------------------------------------------------------------
        # 5. Issue Invoice & Complete Order Lifecycle
        # -------------------------------------------------------------------------
        expect(target_row.locator("button:has-text('開立發票')")).to_be_visible()
        target_row.locator("button:has-text('開立發票')").click()
        expect(target_row.locator("span:text-is('COMPLETED')")).to_be_visible(timeout=5000)
        expect(target_row.locator("a:has-text('🧾 發票')")).to_be_visible()

        # -------------------------------------------------------------------------
        # 6. Multi-Module Navigation Stability Check (Dual-Engine / UnifiedRow Verification)
        # -------------------------------------------------------------------------
        modules = [
            ("/", "營運即時儀表板"),
            ("/inventory", "多倉庫存與雙記帳流水"),
            ("/crm", "哩來 (LiLai) CRM"),
            ("/accounting", "探吉 會計與記帳系統"),
            ("/ai/tools", "檔案自動化"),
        ]
        for url, header_keyword in modules:
            page.goto(f"{BASE_URL}{url}")
            expect(page.locator("h1").filter(has_text=header_keyword).first).to_be_visible()
    finally:
        with db.transaction() as conn:
            oid = test_order.order_id
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("DELETE FROM delivery_allocations WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM delivery_orders WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM invoices WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM accounts_receivable WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM stock_locks WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM sales_order_items WHERE order_id = ?", (oid,))
            conn.execute("DELETE FROM sales_orders WHERE order_id = ?", (oid,))
            conn.execute("PRAGMA foreign_keys = ON;")
