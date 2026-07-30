from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit


CONNECTION_STEPS = (1, 2, 4, 8, 16)


@dataclass(frozen=True, slots=True)
class ServerConnectionProfile:
    server_key: str
    preferred_connections: int = 4
    rate_limit_events: int = 0
    success_streak: int = 0
    last_status: str = ""
    cooldown_until: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class AdaptiveConnectionEvent:
    kind: str
    requested: int
    previous: int
    effective: int
    reason: str


def normalize_connection_count(value: object) -> int:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        candidate = 1
    return min(CONNECTION_STEPS, key=lambda step: abs(step - candidate))


def server_key(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    scheme = parsed.scheme.casefold() or "https"
    hostname = (parsed.hostname or "").casefold()
    if not hostname:
        return ""
    port = parsed.port
    default_port = (scheme == "https" and port == 443) or (
        scheme == "http" and port == 80
    )
    authority = hostname if port is None or default_port else f"{hostname}:{port}"
    return f"{scheme}://{authority}"


def initial_connection_count(
    requested: int,
    profile: ServerConnectionProfile | None,
) -> int:
    requested_count = normalize_connection_count(requested)
    if profile is None:
        return requested_count
    preferred = normalize_connection_count(profile.preferred_connections)
    return max(1, min(requested_count, preferred))


def lower_connection_count(current: int) -> int:
    normalized = normalize_connection_count(current)
    index = CONNECTION_STEPS.index(normalized)
    return CONNECTION_STEPS[max(0, index - 1)]


def raise_connection_count(current: int, requested: int) -> int:
    normalized = normalize_connection_count(current)
    target = normalize_connection_count(requested)
    index = CONNECTION_STEPS.index(normalized)
    return min(target, CONNECTION_STEPS[min(len(CONNECTION_STEPS) - 1, index + 1)])


class AdaptiveConnectionController:
    """Thread-safe concurrency gate that reacts to server rate limits.

    Segment boundaries never change while this controller adjusts the number of
    requests that may run at the same time. That keeps resumable part files
    valid while still reducing pressure on a rate-limited server.
    """

    def __init__(
        self,
        *,
        requested: int,
        initial: int,
        on_change=None,
        clock=time.monotonic,
        penalty_guard_seconds: float = 2.0,
        recovery_cooldown_seconds: float = 15.0,
    ) -> None:
        self.requested = normalize_connection_count(requested)
        self._limit = max(
            1,
            min(self.requested, normalize_connection_count(initial)),
        )
        self._on_change = on_change or (lambda _event: None)
        self._clock = clock
        self._penalty_guard_seconds = max(0.0, penalty_guard_seconds)
        self._recovery_cooldown_seconds = max(
            0.0,
            recovery_cooldown_seconds,
        )
        self._condition = threading.Condition()
        self._active = 0
        self._successes = 0
        self._last_penalty_at = float("-inf")
        self._cooldown_until = 0.0

    @property
    def effective(self) -> int:
        with self._condition:
            return self._limit

    @property
    def active(self) -> int:
        with self._condition:
            return self._active

    def acquire(self, wait_until_running, is_aborted) -> bool:
        while True:
            wait_until_running()
            if is_aborted():
                return False
            with self._condition:
                if self._active < self._limit:
                    self._active += 1
                    return True
                self._condition.wait(timeout=0.1)

    def release(self) -> None:
        with self._condition:
            if self._active > 0:
                self._active -= 1
            self._condition.notify_all()

    def record_rate_limit(
        self,
        *,
        status_code: int = 429,
        retry_after: float = 0.0,
    ) -> AdaptiveConnectionEvent | None:
        now = self._clock()
        event = None
        with self._condition:
            self._successes = 0
            self._cooldown_until = max(
                self._cooldown_until,
                now
                + max(
                    self._recovery_cooldown_seconds,
                    float(retry_after or 0.0),
                ),
            )
            if now - self._last_penalty_at < self._penalty_guard_seconds:
                return None
            self._last_penalty_at = now
            previous = self._limit
            self._limit = lower_connection_count(self._limit)
            if self._limit != previous:
                event = AdaptiveConnectionEvent(
                    kind="rate_limit",
                    requested=self.requested,
                    previous=previous,
                    effective=self._limit,
                    reason=(
                        f"HTTP {int(status_code)}: reduced parallel requests "
                        f"from {previous} to {self._limit}"
                    ),
                )
                self._condition.notify_all()
        if event is not None:
            self._on_change(event)
        return event

    def record_success(self) -> AdaptiveConnectionEvent | None:
        now = self._clock()
        event = None
        with self._condition:
            if now < self._cooldown_until or self._limit >= self.requested:
                return None
            self._successes += 1
            required = max(2, self._limit * 2)
            if self._successes < required:
                return None
            self._successes = 0
            previous = self._limit
            self._limit = raise_connection_count(
                self._limit,
                self.requested,
            )
            if self._limit != previous:
                event = AdaptiveConnectionEvent(
                    kind="recovery",
                    requested=self.requested,
                    previous=previous,
                    effective=self._limit,
                    reason=(
                        "Stable transfer: cautiously increased parallel "
                        f"requests from {previous} to {self._limit}"
                    ),
                )
                self._condition.notify_all()
        if event is not None:
            self._on_change(event)
        return event
