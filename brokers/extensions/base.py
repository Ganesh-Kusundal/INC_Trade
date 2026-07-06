"""Base extension protocol that all extensions should satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Extension(Protocol):
    """Marker protocol for all broker extensions.

    Every extension should satisfy this protocol so callers can use
    ``isinstance(obj, Extension)`` to verify they got an extension.
    """

    @property
    def extension_id(self) -> str:
        """Unique identifier for this extension (e.g. ``"depth_20"``)."""
        ...
