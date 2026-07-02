"""Tests for infrastructure.serialization."""

from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass, field
from decimal import Decimal

from infrastructure.serialization import (
    JsonSerializer,
    MsgPackSerializer,
    json_serializer,
)

# --- Test dataclasses --------------------------------------------------------


@dataclass(frozen=True)
class Inner:
    value: int
    label: str = "default"


@dataclass(frozen=True)
class Outer:
    inner: Inner
    items: list[int] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class Priority(enum.IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class Mixed:
    dt: datetime.datetime
    d: datetime.date
    dec: Decimal
    color: Color
    priority: Priority
    data: bytes


# --- JsonSerializer tests ---------------------------------------------------


def test_dataclass_roundtrip() -> None:
    sut = JsonSerializer()
    obj = Inner(value=42, label="hello")
    serialized = sut.dumps(obj)
    loaded = sut.loads(serialized)
    assert loaded == {"value": 42, "label": "hello"}


def test_nested_dataclass_roundtrip() -> None:
    sut = JsonSerializer()
    obj = Outer(inner=Inner(value=1), items=[1, 2, 3], tags={"a", "b"})
    serialized = sut.dumps(obj)
    loaded = sut.loads(serialized)
    assert loaded["inner"] == {"value": 1, "label": "default"}
    assert loaded["items"] == [1, 2, 3]
    assert set(loaded["tags"]) == {"a", "b"}


def test_datetime_serialization() -> None:
    sut = JsonSerializer()
    dt = datetime.datetime(2025, 6, 15, 10, 30, 0)
    result = sut.dumps({"ts": dt})
    assert "2025-06-15T10:30:00" in result
    loaded = sut.loads(result)
    assert loaded["ts"] == "2025-06-15T10:30:00"


def test_date_serialization() -> None:
    sut = JsonSerializer()
    d = datetime.date(2025, 6, 15)
    result = sut.dumps({"d": d})
    assert "2025-06-15" in result


def test_decimal_serialization() -> None:
    sut = JsonSerializer()
    dec = Decimal("123.456")
    result = sut.dumps({"price": dec})
    loaded = sut.loads(result)
    assert loaded["price"] == "123.456"


def test_enum_serialization() -> None:
    sut = JsonSerializer()
    result = sut.dumps({"color": Color.RED, "priority": Priority.HIGH})
    loaded = sut.loads(result)
    assert loaded["color"] == "red"
    assert loaded["priority"] == 3


def test_bytes_serialization() -> None:
    sut = sut = JsonSerializer()
    data = b"\x00\x01\x02\xff"
    result = sut.dumps({"data": data})
    loaded = sut.loads(result)
    assert loaded["data"] == data


def test_set_serialization() -> None:
    sut = JsonSerializer()
    result = sut.dumps({"tags": {"x", "y", "z"}})
    loaded = sut.loads(result)
    assert set(loaded["tags"]) == {"x", "y", "z"}


def test_nested_mixed_structure() -> None:
    sut = JsonSerializer()
    obj = Outer(
        inner=Inner(value=10),
        items=[1, 2],
        tags={"alpha"},
    )
    serialized = sut.dumps(obj)
    loaded = sut.loads(serialized)
    assert loaded["inner"]["value"] == 10
    assert loaded["items"] == [1, 2]
    assert "alpha" in loaded["tags"]


def test_none_value() -> None:
    sut = JsonSerializer()
    result = sut.dumps({"val": None})
    loaded = sut.loads(result)
    assert loaded["val"] is None


def test_empty_structures() -> None:
    sut = JsonSerializer()
    assert sut.loads(sut.dumps({})) == {}
    assert sut.loads(sut.dumps([])) == []
    assert sut.loads(sut.dumps("")) == ""


def test_string_fallback() -> None:
    sut = JsonSerializer()
    result = sut.dumps({"obj": object()})
    loaded = sut.loads(result)
    assert isinstance(loaded["obj"], str)


def test_to_dict_plain_object() -> None:
    sut = JsonSerializer()
    assert sut.to_dict({"a": 1}) == {"a": 1}
    assert sut.to_dict([1, 2]) == [1, 2]


def test_to_dict_dataclass() -> None:
    sut = JsonSerializer()
    obj = Outer(inner=Inner(value=7), items=[], tags=set())
    result = sut.to_dict(obj)
    assert result["inner"]["value"] == 7
    assert result["items"] == []


def test_from_dict_dataclass() -> None:
    sut = JsonSerializer()
    data = {"value": 99, "label": "ok"}
    result = sut.from_dict(data, Inner)
    assert isinstance(result, Inner)
    assert result.value == 99
    assert result.label == "ok"


def test_from_dict_nested() -> None:
    sut = JsonSerializer()
    data = {"inner": {"value": 5, "label": "nested"}, "items": [1], "tags": ["a"]}
    result = sut.from_dict(data, Outer)
    assert isinstance(result, Outer)
    assert result.inner.value == 5
    assert result.items == [1]
    assert result.tags == {"a"}


def test_from_dict_rejects_non_dataclass() -> None:
    sut = JsonSerializer()
    try:
        sut.from_dict({}, dict)
        raise AssertionError("Should have raised TypeError")
    except TypeError:
        pass


def test_decimal_from_dict() -> None:
    sut = JsonSerializer()
    data = {
        "dt": "2025-01-01T00:00:00",
        "d": "2025-01-01",
        "dec": "99.99",
        "color": "red",
        "priority": 2,
        "data": {"__bytes_b64__": "AAEC/w=="},
    }
    result = sut.from_dict(data, Mixed)
    assert result.dec == Decimal("99.99")
    assert result.color == Color.RED
    assert result.priority == Priority.MEDIUM
    assert result.data == b"\x00\x01\x02\xff"


# --- Module singleton test --------------------------------------------------


def test_singleton_exists() -> None:
    assert isinstance(json_serializer, JsonSerializer)
    result = json_serializer.dumps({"ok": True})
    assert "true" in result


# --- MsgPackSerializer tests ------------------------------------------------


def test_msgpack_fallback_to_json() -> None:
    """MsgPackSerializer should fall back to JSON when msgpack is not installed."""
    sut = MsgPackSerializer()
    if not sut._use_msgpack:
        obj = {"key": "value", "num": 42}
        serialized = sut.dumps(obj)
        assert isinstance(serialized, bytes)
        loaded = sut.loads(serialized)
        assert loaded == obj


def test_msgpack_roundtrip_with_dataclass() -> None:
    sut = MsgPackSerializer()
    obj = Inner(value=5, label="test")
    if sut._use_msgpack:
        # When msgpack is available, dataclass handling depends on _msgpack_default
        serialized = sut.dumps(obj)
        loaded = sut.loads(serialized)
        # msgpack roundtrip may return dict or reconstructed, depending on encoder
        assert loaded["value"] == 5
    else:
        serialized = sut.dumps(obj)
        loaded = sut.loads(serialized)
        assert loaded == {"value": 5, "label": "test"}


# --- Edge cases -------------------------------------------------------------


def test_deeply_nested() -> None:
    sut = JsonSerializer()
    data = {"a": {"b": {"c": [1, {"d": Decimal("3.14")}]}}}
    result = sut.dumps(data)
    loaded = sut.loads(result)
    assert loaded["a"]["b"]["c"][1]["d"] == "3.14"


def test_unicode_strings() -> None:
    sut = JsonSerializer()
    result = sut.dumps({"text": "\u4e2d\u6587\u6d4b\u8bd5"})
    loaded = sut.loads(result)
    assert loaded["text"] == "\u4e2d\u6587\u6d4b\u8bd5"


def test_custom_object_str_fallback() -> None:
    sut = JsonSerializer()

    class Custom:
        def __str__(self) -> str:
            return "custom-repr"

    result = sut.dumps({"obj": Custom()})
    loaded = sut.loads(result)
    assert loaded["obj"] == "custom-repr"
