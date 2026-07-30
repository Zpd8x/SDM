from __future__ import annotations

import threading
import time
from collections.abc import Callable


WaitCallback = Callable[[], None]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class BandwidthLimiter:
    """Thread-safe aggregate pacing shared by every active connection."""

    def __init__(
        self,
        limit_bytes_per_second: int = 0,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._limit = 0
        self._next_available = self._clock()
        self._generation = 0
        self.set_limit(limit_bytes_per_second)

    @property
    def limit_bytes_per_second(self) -> int:
        with self._lock:
            return self._limit

    def set_limit(self, limit_bytes_per_second: int) -> None:
        value = int(limit_bytes_per_second)
        if value < 0:
            raise ValueError("Bandwidth limit cannot be negative.")
        with self._lock:
            self._limit = value
            self._next_available = self._clock()
            self._generation += 1

    def throttle(
        self,
        byte_count: int,
        wait_callback: WaitCallback | None = None,
    ) -> None:
        amount = int(byte_count)
        if amount <= 0:
            return

        with self._lock:
            rate = self._limit
            if rate <= 0:
                return
            generation = self._generation
            now = self._clock()
            available_at = max(now, self._next_available)
            delay = max(0.0, available_at - now)
            self._next_available = available_at + (amount / rate)

        deadline = self._clock() + delay
        while True:
            if wait_callback is not None:
                wait_callback()
            with self._lock:
                if generation != self._generation:
                    return
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            self._sleeper(min(0.1, remaining))
