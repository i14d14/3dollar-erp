from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List


class LineMessagingPort(ABC):
    """Abstract port for sending messages through LINE Messaging API."""

    @abstractmethod
    def reply_message(self, reply_token: str, messages: List[Any]) -> None:
        """Reply to an event using its reply_token."""
        pass

    @abstractmethod
    def push_message(self, to: str, messages: List[Any]) -> None:
        """Send a push message directly to a user/group."""
        pass
