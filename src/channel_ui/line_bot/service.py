from __future__ import annotations
import re
import urllib.parse
from decimal import Decimal
from typing import Any, Dict, List, Optional

from linebot.v3.messaging import TextMessage

from src.channel_ui.line_bot.flex_templates import (
    build_catalog_flex,
    build_order_receipt_flex,
    build_order_status_flex,
)
from src.channel_ui.line_bot.ports import LineMessagingPort
from src.core.domain.inventory import InsufficientStockError
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.order_service import OrderService
from src.shared.database import Database


class LineBotService:
    """Core domain service for handling LINE Bot webhook interactions with Dinkoko ERP."""

    def __init__(
        self,
        db: Database,
        order_service: OrderService,
        inventory_service: InventoryService,
        messaging_port: LineMessagingPort,
        default_warehouse_id: str = "WH-MAIN",
    ) -> None:
        self.db = db
        self.order_service = order_service
        self.inventory_service = inventory_service
        self.messaging_port = messaging_port
        self.default_warehouse_id = default_warehouse_id

    def handle_text_message(self, user_id: str, text: str, reply_token: str) -> None:
        """Handle incoming text message and reply with appropriate Flex or Text message."""
        cleaned_text = text.strip()

        # 1. Catalog keywords
        if any(kw in cleaned_text.lower() for kw in ["型錄", "商品", "產品", "目錄", "catalog", "menu"]):
            self._reply_catalog(reply_token)
            return

        # 2. Order query keywords (e.g. "查單 SO-12345", "查詢 SO-12345", or bare "SO-12345")
        order_match = re.search(r"SO-[A-Za-z0-9]+", cleaned_text, re.IGNORECASE)
        if order_match or any(kw in cleaned_text for kw in ["查單", "查詢進度", "訂單狀態"]):
            if order_match:
                order_id = order_match.group(0).upper()
                self._reply_order_status(order_id, reply_token)
            else:
                self.messaging_port.reply_message(
                    reply_token,
                    [TextMessage(text="請輸入欲查詢的訂單編號（例如：查單 SO-ABC1234567）。")],
                )
            return

        # 3. Help keywords
        if any(kw in cleaned_text.lower() for kw in ["幫助", "說明", "客服", "help"]):
            help_text = (
                "👋 您好！歡迎使用 3Dollar ERP 智能通路助手：\n\n"
                "• 輸入「型錄」或「商品」：瀏覽推薦商品並可直接一鍵下單\n"
                "• 輸入「查單 SO-編號」：查詢出貨進度與電子發票\n"
                "• 輸入「客服」：由專人為您服務\n\n"
                "您也可以點擊下方選單快速操作。"
            )
            self.messaging_port.reply_message(reply_token, [TextMessage(text=help_text)])
            return

        # 4. Default fallback message
        fallback = (
            f"收到您的訊息：「{cleaned_text}」。\n\n"
            "您可以輸入「型錄」查看商品並一鍵訂購，或輸入「查單 SO-編號」即時掌握出貨進度！"
        )
        self.messaging_port.reply_message(reply_token, [TextMessage(text=fallback)])

    def handle_postback(self, user_id: str, data: str, reply_token: str) -> None:
        """Handle button postbacks (one-click order, navigation, etc.)."""
        params = urllib.parse.parse_qs(data)
        action = params.get("action", [""])[0]

        if action == "order":
            sku = params.get("sku", [""])[0]
            try:
                qty_val = Decimal(params.get("qty", ["1"])[0])
            except Exception:
                qty_val = Decimal("1")
            self._process_one_click_order(user_id, sku, qty_val, reply_token)
            return

        if action == "catalog":
            self._reply_catalog(reply_token)
            return

        if action == "status_help":
            self.messaging_port.reply_message(
                reply_token,
                [TextMessage(text="請直接於對話框輸入您的訂單編號（例如：SO-ABC1234567）以查詢出貨進度。")],
            )
            return

        # Unrecognized action fallback
        self.messaging_port.reply_message(
            reply_token,
            [TextMessage(text="無法識別該操作指令，請重新點選選單。")],
        )

    def _reply_catalog(self, reply_token: str) -> None:
        """Fetch active products and reply with interactive Flex catalog."""
        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT sku, name, selling_price, safety_stock 
                FROM products 
                ORDER BY sku ASC
                """
            ).fetchall()

        if not rows:
            self.messaging_port.reply_message(
                reply_token,
                [TextMessage(text="目前系統內尚無已上架的商品型錄。")],
            )
            return

        products = []
        for r in rows:
            products.append(
                {
                    "sku": r["sku"],
                    "name": r["name"],
                    "price": float(r["selling_price"]),
                    "stock_text": "現貨在庫",
                }
            )

        flex_msg = build_catalog_flex(products)
        self.messaging_port.reply_message(reply_token, [flex_msg])

    def _process_one_click_order(
        self,
        user_id: str,
        sku: str,
        qty: Decimal,
        reply_token: str,
    ) -> None:
        """Execute one-click order placement penetrating into Layer 1 ERP."""
        # 1. Fetch product
        prod = self.inventory_service.get_product(sku)
        if not prod:
            self.messaging_port.reply_message(
                reply_token,
                [TextMessage(text=f"⚠️ 下單失敗：查無商品品號 '{sku}'。")],
            )
            return

        customer_id = f"LINE-{user_id[-8:]}" if len(user_id) >= 8 else f"LINE-{user_id}"

        # 2. Create order in DRAFT status
        try:
            order = self.order_service.create_order(
                customer_id=customer_id,
                items=[(sku, qty, prod.selling_price)],
                channel=OrderChannel.LINE,
            )
        except Exception as e:
            self.messaging_port.reply_message(
                reply_token,
                [TextMessage(text=f"⚠️ 下單失敗：{str(e)}")],
            )
            return

        # 3. Confirm order to acquire stock locks in default warehouse
        try:
            confirmed_order = self.order_service.confirm_order(
                order_id=order.order_id,
                warehouse_id=self.default_warehouse_id,
            )
        except (ValueError, InsufficientStockError) as ve:
            # Stock insufficient or validation failure -> auto cancel draft to avoid orphan records
            try:
                self.order_service.cancel_order(order.order_id)
            except Exception:
                pass
            err_msg = str(ve)
            if "Insufficient available stock" in err_msg or "可用庫存不足" in err_msg:
                self.messaging_port.reply_message(
                    reply_token,
                    [TextMessage(text=f"⚠️ 庫存不足：商品 {prod.name} ({sku}) 目前現貨可用量不足，無法完成訂購。")],
                )
            else:
                self.messaging_port.reply_message(
                    reply_token,
                    [TextMessage(text=f"⚠️ 訂單確認未完成：{err_msg}")],
                )
            return

        # 4. Render success receipt flex
        items_summary = [
            {
                "sku": f"{prod.name} ({sku})",
                "qty": int(qty) if qty % 1 == 0 else float(qty),
                "subtotal": float(qty * prod.selling_price),
            }
        ]
        receipt_flex = build_order_receipt_flex(
            order_id=confirmed_order.order_id,
            total_amount=confirmed_order.total_amount,
            items=items_summary,
            customer_id=customer_id,
        )
        self.messaging_port.reply_message(reply_token, [receipt_flex])

    def _reply_order_status(self, order_id: str, reply_token: str) -> None:
        """Fetch order details and render status Flex message."""
        try:
            order = self.order_service.get_order(order_id)
        except Exception:
            self.messaging_port.reply_message(
                reply_token,
                [TextMessage(text=f"🔍 查無訂單編號 '{order_id}'，請確認單號是否輸入正確。")],
            )
            return

        # Check delivery orders
        tracking_number = None
        do_id = None
        with self.db.transaction() as conn:
            do_row = conn.execute(
                "SELECT do_id, tracking_number FROM delivery_orders WHERE order_id = ? ORDER BY rowid DESC LIMIT 1",
                (order_id,),
            ).fetchone()
            if do_row:
                do_id = do_row["do_id"]
                tracking_number = do_row["tracking_number"]

            # Check invoices
            inv_row = conn.execute(
                "SELECT invoice_number FROM invoices WHERE order_id = ? LIMIT 1",
                (order_id,),
            ).fetchone()
            invoice_number = inv_row["invoice_number"] if inv_row else None

        items_summary = [
            {
                "sku": it.sku,
                "qty": int(it.qty) if it.qty % 1 == 0 else float(it.qty),
                "subtotal": float(it.subtotal),
            }
            for it in order.items
        ]

        status_flex = build_order_status_flex(
            order_id=order.order_id,
            status=order.status.value,
            total_amount=order.total_amount,
            items=items_summary,
            tracking_number=tracking_number,
            do_id=do_id,
            invoice_number=invoice_number,
        )
        self.messaging_port.reply_message(reply_token, [status_flex])
