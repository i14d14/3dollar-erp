from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import MessageEvent, PostbackEvent, TextMessageContent

from src.channel_ui.line_bot.service import LineBotService
from src.channel_ui.web.dependencies import get_line_bot_service, get_line_channel_secret

router = APIRouter(prefix="/api/line", tags=["line-bot"])


@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(None, alias="X-Line-Signature"),
    line_bot_service: LineBotService = Depends(get_line_bot_service),
    channel_secret: str = Depends(get_line_channel_secret),
):
    """Webhook entrypoint for LINE platform callbacks with HMAC-SHA256 signature verification."""
    if not x_line_signature:
        raise HTTPException(
            status_code=400,
            detail="缺少 X-Line-Signature 請求標頭 (Missing signature header)",
        )

    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    parser = WebhookParser(channel_secret)
    try:
        events = parser.parse(body_str, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(
            status_code=400,
            detail="數位簽名驗證失敗 (Invalid LINE signature)",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"封包解析失敗: {str(e)}",
        )

    for event in events:
        if isinstance(event, MessageEvent):
            if isinstance(event.message, TextMessageContent):
                user_id = event.source.user_id if event.source else "UNKNOWN"
                line_bot_service.handle_text_message(
                    user_id=user_id,
                    text=event.message.text,
                    reply_token=event.reply_token,
                )
        elif isinstance(event, PostbackEvent):
            user_id = event.source.user_id if event.source else "UNKNOWN"
            line_bot_service.handle_postback(
                user_id=user_id,
                data=event.postback.data,
                reply_token=event.reply_token,
            )

    return {"status": "ok", "processed_events": len(events)}
