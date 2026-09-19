import base64
import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from linebot.v3.messaging import FlexMessage, TextMessage

from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter
from src.channel_ui.web.app import create_app
from src.core.domain.order import OrderChannel, OrderStatus
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.shared.database import Database
from src.shared.event_bus import EventBus


def make_signed_payload(secret: str, events: list) -> tuple[str, str]:
    """Build a valid LINE v3 Webhook payload JSON string and its HMAC-SHA256 signature."""
    payload_dict = {
        "destination": "U3dollar_erp_bot",
        "events": events,
    }
    body_str = json.dumps(payload_dict, ensure_ascii=False)
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body_str.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return body_str, signature


import tempfile
from pathlib import Path

@pytest.fixture
def line_test_env():
    """Setup isolated test database, mock messaging adapter, and FastAPI TestClient."""
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_line_bot.db"
    db = Database(db_path)
    db.init_db()
    event_bus = EventBus()
    mock_adapter = MockLineMessagingAdapter()
    test_secret = "test_webhook_secret_key_888"

    app = create_app(
        db=db,
        event_bus=event_bus,
        line_messaging_port=mock_adapter,
        line_channel_secret=test_secret,
    )
    client = TestClient(app)

    # Initialize order and inventory services
    inv_service = InventoryService(db=db)
    order_service = OrderService(db=db, event_bus=event_bus, inventory_service=inv_service)
    invoice_service = InvoiceService(db=db, event_bus=event_bus)

    yield {
        "db": db,
        "event_bus": event_bus,
        "mock_adapter": mock_adapter,
        "secret": test_secret,
        "client": client,
        "inv_service": inv_service,
        "order_service": order_service,
        "invoice_service": invoice_service,
    }

    temp_dir.cleanup()


def test_webhook_missing_and_invalid_signature(line_test_env):
    client = line_test_env["client"]

    # 1. Missing signature
    resp = client.post("/api/line/webhook", content="{}", headers={})
    assert resp.status_code == 400
    assert "缺少 X-Line-Signature" in resp.json()["detail"]

    # 2. Invalid signature
    resp2 = client.post(
        "/api/line/webhook",
        content="{}",
        headers={"X-Line-Signature": "invalid_sig_value"},
    )
    assert resp2.status_code == 400
    assert "數位簽名驗證失敗" in resp2.json()["detail"]


def test_browse_catalog_flow(line_test_env):
    client = line_test_env["client"]
    secret = line_test_env["secret"]
    mock_adapter = line_test_env["mock_adapter"]

    event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000000,
        "webhookEventId": "evt-001",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Utestuser12345"},
        "replyToken": "token_catalog_01",
        "message": {
            "id": "msg-001",
            "type": "text",
            "text": "我想看商品型錄",
            "quoteToken": "q_token_1",
        },
    }

    body, sig = make_signed_payload(secret, [event])
    resp = client.post(
        "/api/line/webhook",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed_events"] == 1

    # Check mock adapter received the catalog FlexMessage
    assert len(mock_adapter.sent_replies) == 1
    reply = mock_adapter.last_reply
    assert reply.reply_token == "token_catalog_01"
    assert len(reply.messages) == 1

    flex_msg = reply.messages[0]
    assert isinstance(flex_msg, FlexMessage)
    assert flex_msg.alt_text == "3Dollar ERP 商品型錄"

    contents_dict = flex_msg.contents.to_dict()
    assert contents_dict["type"] == "carousel"
    assert len(contents_dict["contents"]) >= 3  # Seed data contains 3 items


def test_one_click_order_and_status_query_flow(line_test_env):
    client = line_test_env["client"]
    secret = line_test_env["secret"]
    mock_adapter = line_test_env["mock_adapter"]
    db = line_test_env["db"]

    # 1. Place order via Postback
    order_event = {
        "type": "postback",
        "mode": "active",
        "timestamp": 1700000000001,
        "webhookEventId": "evt-002",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Ucustomer8888"},
        "replyToken": "token_order_01",
        "postback": {
            "data": "action=order&sku=SKU-PRO-01&qty=2",
        },
    }

    body, sig = make_signed_payload(secret, [order_event])
    resp = client.post(
        "/api/line/webhook",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    # Verify receipt sent
    assert len(mock_adapter.sent_replies) == 1
    receipt_reply = mock_adapter.last_reply
    assert receipt_reply.reply_token == "token_order_01"
    receipt_flex = receipt_reply.messages[0]
    assert isinstance(receipt_flex, FlexMessage)
    assert "訂單成立通知" in receipt_flex.alt_text

    # Verify database state
    with db.transaction() as conn:
        order_row = conn.execute(
            "SELECT order_id, channel, status, total_amount FROM sales_orders WHERE channel = 'LINE' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        assert order_row is not None
        order_id = order_row["order_id"]
        assert order_row["channel"] == OrderChannel.LINE.value
        assert order_row["status"] == OrderStatus.CONFIRMED.value
        assert Decimal(str(order_row["total_amount"])) == Decimal("5000.0")  # 2500 * 2

        # Verify stock lock acquired
        lock_row = conn.execute(
            "SELECT sku, locked_qty, warehouse_id FROM stock_locks WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        assert lock_row is not None
        assert lock_row["sku"] == "SKU-PRO-01"
        assert Decimal(str(lock_row["locked_qty"])) == Decimal("2.0")

    mock_adapter.clear()

    # 2. Query order status via Text message
    query_event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000002,
        "webhookEventId": "evt-003",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Ucustomer8888"},
        "replyToken": "token_query_01",
        "message": {
            "id": "msg-002",
            "type": "text",
            "text": f"查單 {order_id}",
            "quoteToken": "q_token_2",
        },
    }

    body2, sig2 = make_signed_payload(secret, [query_event])
    resp2 = client.post(
        "/api/line/webhook",
        content=body2,
        headers={"X-Line-Signature": sig2, "Content-Type": "application/json"},
    )
    assert resp2.status_code == 200

    assert len(mock_adapter.sent_replies) == 1
    status_reply = mock_adapter.last_reply
    status_flex = status_reply.messages[0]
    assert isinstance(status_flex, FlexMessage)
    status_json = json.dumps(status_flex.contents.to_dict(), ensure_ascii=False)
    assert order_id in status_json
    assert "已確認（備貨鎖庫中）" in status_json

    mock_adapter.clear()

    # 3. Ship and issue invoice, then query again to check tracking and invoice info
    order_service = line_test_env["order_service"]
    invoice_service = line_test_env["invoice_service"]

    # Ship
    order_service.ship_order(
        order_id=order_id,
        warehouse_id="WH-MAIN",
        recipient_name="王小明",
        recipient_phone="0912345678",
        shipping_address="台北市信義區信義路五段7號",
        tracking_number="TRK-LINE-9988",
    )
    # Issue invoice
    invoice, _, _ = invoice_service.issue_invoice_for_order(
        order_id=order_id,
        buyer_name="王小明",
    )

    query_shipped_event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000003,
        "webhookEventId": "evt-004",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Ucustomer8888"},
        "replyToken": "token_query_shipped_01",
        "message": {
            "id": "msg-003",
            "type": "text",
            "text": f"查詢 {order_id}",
            "quoteToken": "q_token_3",
        },
    }

    body3, sig3 = make_signed_payload(secret, [query_shipped_event])
    client.post(
        "/api/line/webhook",
        content=body3,
        headers={"X-Line-Signature": sig3, "Content-Type": "application/json"},
    )
    assert len(mock_adapter.sent_replies) == 1
    shipped_reply = mock_adapter.last_reply
    shipped_json = json.dumps(shipped_reply.messages[0].contents.to_dict(), ensure_ascii=False)
    assert "TRK-LINE-9988" in shipped_json
    assert invoice.invoice_number in shipped_json
    assert "已出貨（物流配送中）" in shipped_json


def test_insufficient_stock_rejection(line_test_env):
    client = line_test_env["client"]
    secret = line_test_env["secret"]
    mock_adapter = line_test_env["mock_adapter"]
    db = line_test_env["db"]

    oversell_event = {
        "type": "postback",
        "mode": "active",
        "timestamp": 1700000000004,
        "webhookEventId": "evt-005",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Ugreedycustomer"},
        "replyToken": "token_oversell_01",
        "postback": {
            "data": "action=order&sku=SKU-PRO-01&qty=99999",
        },
    }

    body, sig = make_signed_payload(secret, [oversell_event])
    resp = client.post(
        "/api/line/webhook",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    # Assert user receives friendly warning
    assert len(mock_adapter.sent_replies) == 1
    reply = mock_adapter.last_reply
    msg = reply.messages[0]
    assert isinstance(msg, TextMessage)
    assert "庫存不足" in msg.text
    assert "SKU-PRO-01" in msg.text

    # Assert no confirmed order for 99999 in DB
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM sales_orders WHERE channel = 'LINE' AND status = 'CONFIRMED' AND total_amount > 1000000"
        ).fetchone()
        assert row[0] == 0


def test_help_and_fallback_messages(line_test_env):
    client = line_test_env["client"]
    secret = line_test_env["secret"]
    mock_adapter = line_test_env["mock_adapter"]

    # 1. Help keyword
    help_event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000005,
        "webhookEventId": "evt-006",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Utestuser1"},
        "replyToken": "token_help_01",
        "message": {
            "id": "msg-004",
            "type": "text",
            "text": "客服說明",
            "quoteToken": "q_token_4",
        },
    }
    body, sig = make_signed_payload(secret, [help_event])
    client.post(
        "/api/line/webhook",
        content=body,
        headers={"X-Line-Signature": sig, "Content-Type": "application/json"},
    )
    assert len(mock_adapter.sent_replies) == 1
    assert "歡迎使用 3Dollar ERP 智能通路助手" in mock_adapter.last_reply.messages[0].text

    mock_adapter.clear()

    # 2. Fallback text
    fallback_event = {
        "type": "message",
        "mode": "active",
        "timestamp": 1700000000006,
        "webhookEventId": "evt-007",
        "deliveryContext": {"isRedelivery": False},
        "source": {"type": "user", "userId": "Utestuser1"},
        "replyToken": "token_fallback_01",
        "message": {
            "id": "msg-005",
            "type": "text",
            "text": "今天天氣很好",
            "quoteToken": "q_token_5",
        },
    }
    body2, sig2 = make_signed_payload(secret, [fallback_event])
    client.post(
        "/api/line/webhook",
        content=body2,
        headers={"X-Line-Signature": sig2, "Content-Type": "application/json"},
    )
    assert len(mock_adapter.sent_replies) == 1
    assert "收到您的訊息：「今天天氣很好」" in mock_adapter.last_reply.messages[0].text
