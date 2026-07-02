"""Public re-exports for the event-bus package."""

from domain.events.types import EventType
from infrastructure.event_bus.dead_letter_queue import DeadLetter, DeadLetterQueue
from infrastructure.event_bus.event_bus import DomainEvent, EventBus, EventHandler
from infrastructure.event_bus.persistent_dead_letter_queue import (
    PersistentDeadLetterQueue,
    create_default_dead_letter_queue,
)
from infrastructure.event_bus.processed_trade_repository import (
    ProcessedTradeRepository,
    TradeIdKey,
)

__all__ = [
    "DeadLetter",
    "DeadLetterQueue",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "EventType",
    "PersistentDeadLetterQueue",
    "ProcessedTradeRepository",
    "TradeIdKey",
    "create_default_dead_letter_queue",
]
