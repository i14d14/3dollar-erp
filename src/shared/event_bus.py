from __future__ import annotations
from collections import defaultdict
from typing import Callable, Dict, List
from src.shared.base_models import DomainEvent

EventHandler = Callable[[DomainEvent], None]

class EventBus:
    """In-memory lightweight domain event bus to decouple layers."""
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)

    def publish(self, event: DomainEvent) -> None:
        handlers = self._subscribers.get(event.event_name, [])
        for handler in handlers:
            handler(event)

    def clear(self) -> None:
        self._subscribers.clear()

# Global default event bus instance
default_event_bus = EventBus()
InMemoryEventBus = EventBus

