from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FlushStats:
    accepted: int
    replaced: int
    flushed: int
    pending: int


class LatestValueBuffer(Generic[T]):
    """Thread-safe last-value-wins buffer for high-frequency UI events.

    Download workers can emit progress many times per second. Rendering every
    signal wastes CPU and makes Qt tables repaint excessively. This buffer keeps
    only the newest value for each key, allowing the UI to flush at a controlled
    frame rate without losing the latest state.
    """

    def __init__(self) -> None:
        self._values: dict[str, T] = {}
        self._lock = RLock()
        self._accepted = 0
        self._replaced = 0
        self._flushed = 0
        self._last_flush = monotonic()

    def put(self, key: str, value: T) -> None:
        with self._lock:
            if key in self._values:
                self._replaced += 1
            self._values[key] = value
            self._accepted += 1

    def drain(self) -> dict[str, T]:
        with self._lock:
            values = self._values
            self._values = {}
            self._flushed += len(values)
            self._last_flush = monotonic()
            return values

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def stats(self) -> FlushStats:
        with self._lock:
            return FlushStats(
                accepted=self._accepted,
                replaced=self._replaced,
                flushed=self._flushed,
                pending=len(self._values),
            )

    @property
    def seconds_since_flush(self) -> float:
        with self._lock:
            return max(0.0, monotonic() - self._last_flush)
