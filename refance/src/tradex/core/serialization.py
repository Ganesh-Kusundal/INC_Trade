"""Serialization framework.

Provider-agnostic serialization for requests and responses.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID


class SDKEncoder(json.JSONEncoder):
    """JSON encoder that handles SDK-specific types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "value"):
            return obj.value
        return super().default(obj)


def to_json(obj: Any, indent: Optional[int] = None) -> str:
    """Serialize an object to JSON string."""
    return json.dumps(obj, cls=SDKEncoder, indent=indent, default=str)


def from_json(data: str) -> Any:
    """Deserialize a JSON string."""
    return json.loads(data)


def to_dict(obj: Any) -> dict[str, Any]:
    """Convert an object to a dictionary.

    Handles dataclasses, objects with to_dict(), and pydantic models.
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": obj}


def from_dict(data: dict[str, Any], target_type: type) -> Any:
    """Construct an object from a dictionary.

    Supports dataclasses and pydantic models.
    """
    if hasattr(target_type, "model_validate"):
        return target_type.model_validate(data)
    if hasattr(target_type, "from_dict"):
        return target_type.from_dict(data)
    if hasattr(target_type, "__dataclass_fields__"):
        return target_type(
            **{k: v for k, v in data.items() if k in target_type.__dataclass_fields__}
        )
    return target_type(data)
