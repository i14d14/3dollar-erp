from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable
from src.shared.base_models import DomainEvent

class EventBusPort(ABC):
    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all subscribers."""
        pass

    @abstractmethod
    def subscribe(self, event_name: str, handler: Callable[[DomainEvent], None]) -> None:
        """Subscribe to a domain event by name."""
        pass
