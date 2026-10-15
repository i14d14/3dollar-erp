from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List, Optional

from linebot.v3.messaging import FlexContainer, FlexMessage


def build_catalog_flex(products: List[Dict[str, Any]]) -> FlexMessage:
    """Build a Carousel Flex Message displaying available products with one-click ordering buttons."""
    bubbles = []
    for prod in products:
        sku = prod.get("sku", "")
        name = prod.get("name", "未命名商品")
        price = prod.get("price", 0)
        stock_text = prod.get("stock_text", "現貨在庫")

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#F8FAFC",
                "paddingTop": "14px",
                "paddingBottom": "14px",
                "paddingStart": "20px",
                "paddingEnd": "20px",
                "contents": [
                    {
                        "type": "text",
                        "text": "精選商品",
                        "size": "xs",
                        "color": "#64748B",
                        "weight": "bold",
                    }
                ],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": name,
                        "weight": "bold",
                        "size": "md",
                        "wrap": True,
                        "color": "#0F172A",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "xs",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "品號", "color": "#94A3B8", "size": "xs", "flex": 2},
                                    {"type": "text", "text": sku, "color": "#334155", "size": "xs", "flex": 5, "weight": "bold"},
                                ],
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "售價", "color": "#94A3B8", "size": "xs", "flex": 2},
                                    {"type": "text", "text": f"NT$ {price:,.0f}", "color": "#0284C7", "size": "sm", "flex": 5, "weight": "bold"},
                                ],
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "spacing": "sm",
                                "contents": [
                                    {"type": "text", "text": "狀態", "color": "#94A3B8", "size": "xs", "flex": 2},
                                    {"type": "text", "text": stock_text, "color": "#16A34A", "size": "xs", "flex": 5},
                                ],
                            },
                        ],
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "paddingTop": "12px",
                "paddingBottom": "16px",
                "paddingStart": "20px",
                "paddingEnd": "20px",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#06C755",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "立即購買 (1 份)",
                            "data": f"action=order&sku={sku}&qty=1",
                            "displayText": f"我要訂購 1 份 {name}",
                        },
                    }
                ],
            },
        }
        bubbles.append(bubble)

    container_dict = {
        "type": "carousel",
        "contents": bubbles,
    }
    return FlexMessage(
        alt_text="3Dollar ERP 商品型錄",
        contents=FlexContainer.from_dict(container_dict),
    )


def build_order_receipt_flex(
    order_id: str,
    total_amount: Decimal | float,
    items: List[Dict[str, Any]],
    customer_id: str = "LINE 客戶",
) -> FlexMessage:
    """Build a formal Order Confirmation Receipt Flex Message bubble."""
    item_rows = []
    for item in items:
        sku = item.get("sku", "")
        pname = item.get("product_name") or item.get("name")
        qty = item.get("qty", 1)
        subtotal = item.get("subtotal", 0)
        if pname and pname != sku and f"({sku})" not in pname:
            item_display = f"{pname} ({sku}) x {qty}"
        else:
            item_display = f"{sku} x {qty}" if sku else f"{pname} x {qty}"

        item_rows.append(
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": item_display,
                        "size": "sm",
                        "color": "#334155",
                        "flex": 6,
                    },
                    {
                        "type": "text",
                        "text": f"NT$ {subtotal:,.0f}",
                        "size": "sm",
                        "color": "#0F172A",
                        "align": "end",
                        "weight": "bold",
                        "flex": 4,
                    },
                ],
            }
        )

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#06C755",
            "paddingTop": "16px",
            "paddingBottom": "16px",
            "paddingStart": "20px",
            "paddingEnd": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "訂單已成功建立",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "baseline",
                            "spacing": "sm",
                            "contents": [
                                {"type": "text", "text": "訂單編號", "color": "#94A3B8", "size": "xs", "flex": 3},
                                {"type": "text", "text": order_id, "color": "#0F172A", "size": "xs", "flex": 7, "weight": "bold"},
                            ],
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "spacing": "sm",
                            "contents": [
                                {"type": "text", "text": "購買通路", "color": "#94A3B8", "size": "xs", "flex": 3},
                                {"type": "text", "text": "LINE 智能通路", "color": "#0284C7", "size": "xs", "flex": 7},
                            ],
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "spacing": "sm",
                            "contents": [
                                {"type": "text", "text": "目前狀態", "color": "#94A3B8", "size": "xs", "flex": 3},
                                {"type": "text", "text": "已確認（庫存已鎖定）", "color": "#16A34A", "size": "xs", "flex": 7, "weight": "bold"},
                            ],
                        },
                    ],
                },
                {"type": "separator"},
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": item_rows,
                },
                {"type": "separator"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "應付總額", "weight": "bold", "size": "sm", "color": "#0F172A", "flex": 5},
                        {
                            "type": "text",
                            "text": f"NT$ {float(total_amount):,.0f}",
                            "weight": "bold",
                            "size": "md",
                            "color": "#E11D48",
                            "align": "end",
                            "flex": 5,
                        },
                    ],
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F8FAFC",
            "paddingTop": "14px",
            "paddingBottom": "16px",
            "paddingStart": "20px",
            "paddingEnd": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "本訂單已寫入 ERP 系統，後續出貨將即時發送物流通知。",
                    "size": "xs",
                    "lineSpacing": "4px",
                    "color": "#64748B",
                    "wrap": True,
                }
            ],
        },
    }

    return FlexMessage(
        alt_text=f"訂單成立通知 ({order_id})",
        contents=FlexContainer.from_dict(bubble),
    )


def build_order_status_flex(
    order_id: str,
    status: str,
    total_amount: Decimal | float,
    items: List[Dict[str, Any]],
    tracking_number: Optional[str] = None,
    do_id: Optional[str] = None,
    invoice_number: Optional[str] = None,
) -> FlexMessage:
    """Build an Order Status Query Result Flex Message bubble."""
    status_map = {
        "DRAFT": ("草稿建立", "#64748B"),
        "CONFIRMED": ("已確認（備貨鎖庫中）", "#0284C7"),
        "SHIPPED": ("已出貨（物流配送中）", "#16A34A"),
        "COMPLETED": ("訂單已完成", "#059669"),
        "CANCELLED": ("已取消", "#E11D48"),
    }
    status_label, status_color = status_map.get(status, (status, "#334155"))

    info_rows = [
        {
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "訂單編號", "color": "#94A3B8", "size": "xs", "flex": 3},
                {"type": "text", "text": order_id, "color": "#0F172A", "size": "xs", "flex": 7, "weight": "bold"},
            ],
        },
        {
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                {"type": "text", "text": "處理進度", "color": "#94A3B8", "size": "xs", "flex": 3},
                {"type": "text", "text": status_label, "color": status_color, "size": "xs", "flex": 7, "weight": "bold"},
            ],
        },
    ]

    if do_id:
        info_rows.append(
            {
                "type": "box",
                "layout": "baseline",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "出貨單號", "color": "#94A3B8", "size": "xs", "flex": 3},
                    {"type": "text", "text": do_id, "color": "#334155", "size": "xs", "flex": 7},
                ],
            }
        )
    if tracking_number:
        info_rows.append(
            {
                "type": "box",
                "layout": "baseline",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "物流追蹤", "color": "#94A3B8", "size": "xs", "flex": 3},
                    {"type": "text", "text": tracking_number, "color": "#0284C7", "size": "xs", "flex": 7, "weight": "bold"},
                ],
            }
        )
    if invoice_number:
        info_rows.append(
            {
                "type": "box",
                "layout": "baseline",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "電子發票", "color": "#94A3B8", "size": "xs", "flex": 3},
                    {"type": "text", "text": invoice_number, "color": "#16A34A", "size": "xs", "flex": 7, "weight": "bold"},
                ],
            }
        )

    item_rows = []
    for item in items:
        sku = item.get("sku", "")
        pname = item.get("product_name") or item.get("name")
        qty = item.get("qty", 1)
        subtotal = item.get("subtotal", 0)
        if pname and pname != sku and f"({sku})" not in pname:
            item_display = f"{pname} ({sku}) x {qty}"
        else:
            item_display = f"{sku} x {qty}" if sku else f"{pname} x {qty}"

        item_rows.append(
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": item_display, "size": "xs", "color": "#475569", "flex": 6},
                    {"type": "text", "text": f"NT$ {subtotal:,.0f}", "size": "xs", "color": "#0F172A", "align": "end", "flex": 4},
                ],
            }
        )

    bubble = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0284C7",
            "paddingTop": "16px",
            "paddingBottom": "16px",
            "paddingStart": "20px",
            "paddingEnd": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "訂單進度查詢結果",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "md",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": info_rows,
                },
                {"type": "separator"},
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": item_rows,
                },
                {"type": "separator"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "訂單總計", "weight": "bold", "size": "sm", "color": "#0F172A", "flex": 5},
                        {
                            "type": "text",
                            "text": f"NT$ {float(total_amount):,.0f}",
                            "weight": "bold",
                            "size": "md",
                            "color": "#0284C7",
                            "align": "end",
                            "flex": 5,
                        },
                    ],
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F8FAFC",
            "paddingTop": "14px",
            "paddingBottom": "16px",
            "paddingStart": "20px",
            "paddingEnd": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "若對訂單狀態有任何疑問，可於聊天室直接回傳問題，將由客服為您確認。",
                    "size": "xs",
                    "lineSpacing": "4px",
                    "color": "#64748B",
                    "wrap": True,
                }
            ],
        },
    }

    return FlexMessage(
        alt_text=f"訂單狀態 ({order_id})",
        contents=FlexContainer.from_dict(bubble),
    )
