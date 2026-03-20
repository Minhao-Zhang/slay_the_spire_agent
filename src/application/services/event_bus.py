from __future__ import annotations

from collections import defaultdict
from typing import Callable


EventHandler = Callable[[object], None]


class EventBus:
    """Small in-process event bus for the v2 application layer."""

    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event: object) -> None:
        event_type = getattr(event, "event_type", event.__class__.__name__)
        for handler in self._subscribers.get(event_type, []):
            handler(event)
