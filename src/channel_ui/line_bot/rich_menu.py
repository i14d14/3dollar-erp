from __future__ import annotations
from typing import Any, Dict

from linebot.v3.messaging import (
    MessageAction,
    PostbackAction,
    RichMenuArea,
    RichMenuBounds,
    RichMenuRequest,
    RichMenuSize,
)


def generate_default_rich_menu_config() -> Dict[str, Any]:
    """Generate raw JSON dictionary specification for 2500x843 compact 3-grid Rich Menu."""
    return {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "3Dollar-ERP-Customer-Menu",
        "chatBarText": "快速服務選單",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {
                    "type": "postback",
                    "label": "商品型錄",
                    "data": "action=catalog",
                    "displayText": "查看推薦商品",
                },
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
                "action": {
                    "type": "message",
                    "label": "訂單進度",
                    "text": "查單",
                },
            },
            {
                "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
                "action": {
                    "type": "message",
                    "label": "聯絡客服",
                    "text": "客服",
                },
            },
        ],
    }


def build_rich_menu_request() -> RichMenuRequest:
    """Build official Pydantic RichMenuRequest model for LINE SDK v3."""
    return RichMenuRequest(
        size=RichMenuSize(width=2500, height=843),
        selected=True,
        name="3Dollar-ERP-Customer-Menu",
        chat_bar_text="快速服務選單",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=833, height=843),
                action=PostbackAction(label="商品型錄", data="action=catalog", display_text="查看推薦商品"),
            ),
            RichMenuArea(
                bounds=RichMenuBounds(x=833, y=0, width=834, height=843),
                action=MessageAction(label="訂單進度", text="查單"),
            ),
            RichMenuArea(
                bounds=RichMenuBounds(x=1667, y=0, width=833, height=843),
                action=MessageAction(label="聯絡客服", text="客服"),
            ),
        ],
    )
