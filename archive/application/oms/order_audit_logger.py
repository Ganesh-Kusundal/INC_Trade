"""Order audit logger stub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AuditEntry:
    event_type: str = ""
    order_id: str = ""
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class OrderAuditLogger:
    def __init__(self, **kwargs: Any) -> None:
        pass

    def log(self, entry: AuditEntry) -> None:
        pass
