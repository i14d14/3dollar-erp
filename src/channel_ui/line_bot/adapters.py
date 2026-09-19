from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
)

from src.channel_ui.line_bot.ports import LineMessagingPort


@dataclass
class SentReplyRecord:
    reply_token: str
    messages: List[Any]


@dataclass
class SentPushRecord:
    to: str
    messages: List[Any]


import time
from linebot.v3.oauth import ChannelAccessToken

class RealLineMessagingAdapter(LineMessagingPort):
    """Real adapter that delivers messages via LINE Messaging API, supporting Stateless Token v3."""

    def __init__(
        self,
        channel_access_token: Optional[str] = None,
        channel_id: Optional[str] = None,
        channel_secret: Optional[str] = None,
    ) -> None:
        self.channel_access_token = channel_access_token
        self.channel_id = channel_id
        self.channel_secret = channel_secret
        self._cached_token: Optional[str] = channel_access_token
        self._token_expires_at: float = float("inf") if channel_access_token else 0.0

    def _get_active_token(self) -> str:
        """Retrieve static token or auto-issue Stateless Token v3 (15-min) using Channel ID and Secret."""
        if self.channel_access_token:
            return self.channel_access_token

        now = time.time()
        if self._cached_token and now < self._token_expires_at - 60:
            return self._cached_token

        if not self.channel_id or not self.channel_secret:
            raise ValueError(
                "必須提供 LINE_CHANNEL_ID 與 LINE_CHANNEL_SECRET，或直接提供 LINE_CHANNEL_ACCESS_TOKEN"
            )

        oauth_client = ChannelAccessToken()
        res = oauth_client.issue_stateless_channel_token_by_client_secret(
            client_id=str(self.channel_id),
            client_secret=str(self.channel_secret),
        )
        self._cached_token = res.access_token
        self._token_expires_at = now + res.expires_in
        return self._cached_token

    def reply_message(self, reply_token: str, messages: List[Any]) -> None:
        token = self._get_active_token()
        config = Configuration(access_token=token)
        with ApiClient(config) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=messages,
                )
            )

    def push_message(self, to: str, messages: List[Any]) -> None:
        token = self._get_active_token()
        config = Configuration(access_token=token)
        with ApiClient(config) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(
                PushMessageRequest(
                    to=to,
                    messages=messages,
                )
            )


class MockLineMessagingAdapter(LineMessagingPort):
    """In-memory mock adapter for offline automated tests without external network or credentials."""

    def __init__(self) -> None:
        self.sent_replies: List[SentReplyRecord] = []
        self.sent_pushes: List[SentPushRecord] = []

    def reply_message(self, reply_token: str, messages: List[Any]) -> None:
        self.sent_replies.append(SentReplyRecord(reply_token=reply_token, messages=messages))

    def push_message(self, to: str, messages: List[Any]) -> None:
        self.sent_pushes.append(SentPushRecord(to=to, messages=messages))

    def clear(self) -> None:
        self.sent_replies.clear()
        self.sent_pushes.clear()

    @property
    def last_reply(self) -> Optional[SentReplyRecord]:
        return self.sent_replies[-1] if self.sent_replies else None

    @property
    def last_push(self) -> Optional[SentPushRecord]:
        return self.sent_pushes[-1] if self.sent_pushes else None
