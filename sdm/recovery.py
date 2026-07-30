from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from sdm.network_health import NetworkSnapshot, classify_network_error, probe_network


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    retry: bool
    delay_seconds: float
    reason: str
    wait_for_network: bool = False


_BASE_DELAYS = {
    "rate_limited": 10.0,
    "service_unavailable": 8.0,
    "server_error": 5.0,
    "timeout": 3.0,
    "dns_error": 5.0,
    "connection_reset": 2.0,
    "offline": 2.0,
    "network_error": 3.0,
    "ssl_error": 0.0,
    "http_error": 0.0,
}


def recovery_decision(error: BaseException, attempt: int, *, max_attempts: int = 6) -> RecoveryDecision:
    kind = classify_network_error(error)
    if attempt >= max_attempts or kind in {"ssl_error", "http_error"}:
        return RecoveryDecision(False, 0.0, kind)
    base = _BASE_DELAYS.get(kind, 3.0)
    delay = min(base * (2 ** max(attempt, 0)), 120.0)
    return RecoveryDecision(True, delay, kind, wait_for_network=(kind in {"offline", "dns_error"}))


def jittered_delay(delay_seconds: float, *, random_value: float | None = None) -> float:
    value = random.random() if random_value is None else random_value
    return max(0.0, delay_seconds * (0.9 + 0.2 * value))


def wait_until_online(
    *,
    probe: Callable[[], NetworkSnapshot] = probe_network,
    sleeper: Callable[[float], None] = time.sleep,
    interval_seconds: float = 2.0,
    max_checks: int = 30,
    on_snapshot: Callable[[NetworkSnapshot], None] | None = None,
) -> NetworkSnapshot:
    last = probe()
    if on_snapshot:
        on_snapshot(last)
    checks = 1
    while not last.online and checks < max_checks:
        sleeper(interval_seconds)
        last = probe()
        if on_snapshot:
            on_snapshot(last)
        checks += 1
    return last


def validate_resume_metadata(
    *,
    previous_etag: str = "",
    current_etag: str = "",
    previous_last_modified: str = "",
    current_last_modified: str = "",
    previous_size: int = 0,
    current_size: int = 0,
) -> tuple[bool, str]:
    if previous_etag and current_etag and previous_etag != current_etag:
        return False, "ETag changed"
    if previous_last_modified and current_last_modified and previous_last_modified != current_last_modified:
        return False, "Last-Modified changed"
    if previous_size > 0 and current_size > 0 and previous_size != current_size:
        return False, "Remote file size changed"
    return True, "Resume metadata is compatible"


def choose_next_mirror(current_url: str, mirrors: Iterable[str]) -> str:
    candidates = [url.strip() for url in mirrors if url and url.strip()]
    if not candidates:
        return current_url
    try:
        index = candidates.index(current_url)
    except ValueError:
        return candidates[0]
    return candidates[(index + 1) % len(candidates)]
