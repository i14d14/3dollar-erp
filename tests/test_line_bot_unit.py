import base64
import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import FlexMessage, RichMenuRequest
from linebot.v3.webhook import WebhookParser

from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter
from src.channel_ui.line_bot.flex_templates import (
    build_catalog_flex,
    build_order_receipt_flex,
    build_order_status_flex,
)
from src.channel_ui.line_bot.rich_menu import (
    build_rich_menu_request,
    generate_default_rich_menu_config,
)


def compute_signature(secret: str, body: str) -> str:
    """Helper to compute HMAC-SHA256 signature encoded in base64."""
    hash_val = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(hash_val).decode("utf-8")


def test_signature_verification_success():
    secret = "my_unit_test_secret_123"
    body = json.dumps({"destination": "U12345", "events": []})
    valid_sig = compute_signature(secret, body)

    parser = WebhookParser(secret)
    events = parser.parse(body, valid_sig)
    assert events == []


def test_signature_verification_tampered_body():
    secret = "my_unit_test_secret_123"
    body = json.dumps({"destination": "U12345", "events": []})
    valid_sig = compute_signature(secret, body)

    tampered_body = json.dumps({"destination": "U12345", "events": [], "hacked": True})
    parser = WebhookParser(secret)

    with pytest.raises(InvalidSignatureError):
        parser.parse(tampered_body, valid_sig)


def test_signature_verification_wrong_secret():
    secret = "my_unit_test_secret_123"
    body = json.dumps({"destination": "U12345", "events": []})
    valid_sig = compute_signature(secret, body)

    wrong_parser = WebhookParser("wrong_secret_456")
    with pytest.raises(InvalidSignatureError):
        wrong_parser.parse(body, valid_sig)


def test_build_catalog_flex():
    products = [
        {"sku": "SKU-A", "name": "測試商品 A", "price": 1200, "stock_text": "庫存充裕"},
        {"sku": "SKU-B", "name": "測試商品 B", "price": 450, "stock_text": "少量現貨"},
    ]
    flex_msg = build_catalog_flex(products)
    assert isinstance(flex_msg, FlexMessage)
    assert flex_msg.alt_text == "3Dollar ERP 商品型錄"

    data_dict = flex_msg.contents.to_dict()
    assert data_dict["type"] == "carousel"
    assert len(data_dict["contents"]) == 2

    # Check button payload in first card
    first_bubble = data_dict["contents"][0]
    button_action = first_bubble["footer"]["contents"][0]["action"]
    assert button_action["type"] == "postback"
    assert "action=order&sku=SKU-A&qty=1" in button_action["data"]
    assert button_action["displayText"] == "我要訂購 1 份 測試商品 A"


def test_build_order_receipt_flex():
    items = [
        {"sku": "商品A (SKU-A)", "qty": 2, "subtotal": 2400.0},
        {"sku": "商品B (SKU-B)", "qty": 1, "subtotal": 450.0},
    ]
    receipt = build_order_receipt_flex(
        order_id="SO-TEST-001",
        total_amount=Decimal("2850.0"),
        items=items,
        customer_id="LINE-USER-99",
    )
    assert isinstance(receipt, FlexMessage)
    assert "SO-TEST-001" in receipt.alt_text

    data_dict = receipt.contents.to_dict()
    assert data_dict["type"] == "bubble"
    assert data_dict["header"]["contents"][0]["text"] == "訂單已成功建立"


def test_build_order_status_flex():
    items = [{"sku": "SKU-A", "qty": 1, "subtotal": 1200.0}]
    status_msg = build_order_status_flex(
        order_id="SO-TEST-002",
        status="SHIPPED",
        total_amount=1200.0,
        items=items,
        tracking_number="TRK-99998888",
        do_id="DO-777",
        invoice_number="AB-12345678",
    )
    assert isinstance(status_msg, FlexMessage)

    data_dict = status_msg.contents.to_dict()
    assert data_dict["type"] == "bubble"
    assert data_dict["header"]["contents"][0]["text"] == "訂單進度查詢結果"

    # Check that tracking number and invoice number are in body
    body_str = json.dumps(data_dict["body"], ensure_ascii=False)
    assert "TRK-99998888" in body_str
    assert "DO-777" in body_str
    assert "AB-12345678" in body_str
    assert "已出貨（物流配送中）" in body_str


def test_rich_menu_configurations():
    config = generate_default_rich_menu_config()
    assert config["size"]["width"] == 2500
    assert config["size"]["height"] == 843
    assert len(config["areas"]) == 3
    assert config["areas"][0]["action"]["data"] == "action=catalog"

    request_obj = build_rich_menu_request()
    assert isinstance(request_obj, RichMenuRequest)
    assert request_obj.size.width == 2500
    assert request_obj.size.height == 843
    assert len(request_obj.areas) == 3


def test_mock_messaging_adapter():
    adapter = MockLineMessagingAdapter()
    assert adapter.sent_replies == []
    assert adapter.sent_pushes == []

    adapter.reply_message("token_1", [{"type": "text", "text": "Hello"}])
    assert len(adapter.sent_replies) == 1
    assert adapter.last_reply.reply_token == "token_1"

    adapter.push_message("user_1", [{"type": "text", "text": "Alert"}])
    assert len(adapter.sent_pushes) == 1
    assert adapter.last_push.to == "user_1"

    adapter.clear()
    assert adapter.sent_replies == []
    assert adapter.sent_pushes == []


def test_real_adapter_stateless_token_logic():
    from unittest.mock import MagicMock, patch
    from src.channel_ui.line_bot.adapters import RealLineMessagingAdapter

    # 1. Static token provided
    adapter_static = RealLineMessagingAdapter(channel_access_token="my_static_token")
    assert adapter_static._get_active_token() == "my_static_token"

    # 2. Missing credentials raises ValueError
    adapter_empty = RealLineMessagingAdapter()
    with pytest.raises(ValueError):
        adapter_empty._get_active_token()

    # 3. Stateless Token v3 auto-issuance
    adapter_stateless = RealLineMessagingAdapter(channel_id="12345", channel_secret="secret678")
    mock_res = MagicMock()
    mock_res.access_token = "stateless_token_v3_xyz"
    mock_res.expires_in = 900  # 15 minutes

    with patch(
        "src.channel_ui.line_bot.adapters.ChannelAccessToken.issue_stateless_channel_token_by_client_secret",
        return_value=mock_res,
    ) as mock_issue:
        token = adapter_stateless._get_active_token()
        assert token == "stateless_token_v3_xyz"
        mock_issue.assert_called_once_with(client_id="12345", client_secret="secret678")

        # Second call uses cached token within valid window
        token_cached = adapter_stateless._get_active_token()
        assert token_cached == "stateless_token_v3_xyz"
        assert mock_issue.call_count == 1
