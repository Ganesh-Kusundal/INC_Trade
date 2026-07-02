"""Canonical serialization for the TradeXV2 platform.

Provides standardized JSON (and optional MsgPack) serialization that handles
dataclasses, datetime, Decimal, enums, bytes, and sets. Use the module-level
``json_serializer`` singleton for convenience.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime
import enum
import json
from decimal import Decimal
from typing import Any


class _TradeXEncoder(json.JSONEncoder):
    """JSON encoder that handles domain-specific types."""

    def default(self, o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        if isinstance(o, datetime.date):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, enum.Enum):
            return o.value
        if isinstance(o, bytes):
            return {"__bytes_b64__": base64.b64encode(o).decode("ascii")}
        if isinstance(o, set):
            return sorted(o, key=str)
        return str(o)


class JsonSerializer:
    """JSON serializer that handles dataclasses, datetime, Decimal, enums, bytes, sets."""

    def dumps(self, obj: Any) -> str:
        return json.dumps(obj, cls=_TradeXEncoder, ensure_ascii=False)

    def loads(self, data: str) -> Any:
        return json.loads(data, object_hook=_object_hook)

    def to_dict(self, obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return _make_dict(obj)
        return obj

    def from_dict(self, data: dict, cls: type) -> Any:
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"{cls!r} is not a dataclass")
        return _from_dict(data, cls)


def _make_dict(obj: Any) -> Any:
    """Recursively convert a dataclass to dict, handling nested types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in dataclasses.fields(obj):
            val = getattr(obj, f.name)
            result[f.name] = _make_dict(val)
        return result
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, bytes):
        return {"__bytes_b64__": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, set):
        return sorted(obj, key=str)
    if isinstance(obj, list):
        return [_make_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _make_dict(v) for k, v in obj.items()}
    return obj


def _from_dict(data: dict, cls: type) -> Any:
    """Reconstruct a dataclass from a dict."""
    import typing

    if not dataclasses.is_dataclass(cls):
        return data

    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = {f.name: f.type for f in dataclasses.fields(cls)}

    kwargs = {}

    for fname, ftype in hints.items():
        if fname not in data:
            continue
        raw = data[fname]
        kwargs[fname] = _coerce(raw, ftype)

    return cls(**kwargs)


def _coerce(value: Any, target_type: Any) -> Any:
    """Coerce a primitive/dict/list value to target_type."""
    import typing

    if value is None:
        return None

    # Resolve Optional[X] -> X
    origin = getattr(target_type, "__origin__", None)
    if origin is typing.Union:
        args = typing.get_args(target_type)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            target_type = non_none[0]
            origin = getattr(target_type, "__origin__", None)

    # Dataclass from dict
    if dataclasses.is_dataclass(target_type) and isinstance(value, dict):
        return _from_dict(value, target_type)

    # Primitives
    if target_type is datetime.datetime and isinstance(value, str):
        return datetime.datetime.fromisoformat(value)
    if target_type is datetime.date and isinstance(value, str):
        return datetime.date.fromisoformat(value)
    if target_type is Decimal and isinstance(value, str):
        return Decimal(value)

    # Enums
    if isinstance(target_type, type) and issubclass(target_type, enum.Enum):
        if isinstance(value, str):
            return target_type(value)
        if isinstance(value, int):
            return target_type(value)

    # Bytes
    if target_type is bytes and isinstance(value, dict) and "__bytes_b64__" in value:
        return base64.b64decode(value["__bytes_b64__"])

    # Set (with optional generic arg)
    if origin is set and isinstance(value, list):
        return set(value)

    # List (with optional generic arg)
    if origin is list and isinstance(value, list):
        args = typing.get_args(target_type)
        if args:
            return [_coerce(v, args[0]) for v in value]

    return value


def _object_hook(d: Any) -> Any:
    """Decode bytes objects during loads."""
    if isinstance(d, dict) and "__bytes_b64__" in d and len(d) == 1:
        return base64.b64decode(d["__bytes_b64__"])
    return d


class MsgPackSerializer:
    """MsgPack serializer with the same interface as JsonSerializer.

    Falls back to JSON if msgpack is not installed.
    """

    def __init__(self) -> None:
        try:
            import msgpack as _msgpack

            self._msgpack = _msgpack
            self._use_msgpack = True
        except ImportError:
            self._msgpack = None
            self._use_msgpack = False
            self._json = JsonSerializer()

    def dumps(self, obj: Any) -> bytes:
        if self._use_msgpack:
            return self._msgpack.packb(obj, default=_msgpack_default)
        return self._json.dumps(obj).encode("utf-8")

    def loads(self, data: bytes) -> Any:
        if self._use_msgpack:
            return self._msgpack.unpackb(data, raw=False)
        return self._json.loads(data.decode("utf-8"))


def _msgpack_default(obj: Any) -> Any:
    """Fallback encoder for msgpack when it encounters unknown types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, bytes):
        return {"__bytes_b64__": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, set):
        return sorted(obj, key=str)
    return str(obj)


json_serializer = JsonSerializer()
