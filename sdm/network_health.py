from __future__ import annotations

import socket
import time
import urllib.error
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class NetworkQuality(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    OFFLINE = "Offline"


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    online: bool
    latency_ms: float | None
    quality: NetworkQuality
    checked_at: float
    error: str = ""


def classify_network_quality(online: bool, latency_ms: float | None) -> NetworkQuality:
    if not online:
        return NetworkQuality.OFFLINE
    if latency_ms is None:
        return NetworkQuality.FAIR
    if latency_ms <= 80:
        return NetworkQuality.EXCELLENT
    if latency_ms <= 180:
        return NetworkQuality.GOOD
    if latency_ms <= 400:
        return NetworkQuality.FAIR
    return NetworkQuality.POOR


def probe_network(
    host: str = "1.1.1.1",
    port: int = 53,
    timeout: float = 2.0,
    *,
    connector: Callable[..., object] = socket.create_connection,
) -> NetworkSnapshot:
    started = time.monotonic()
    try:
        connection = connector((host, port), timeout=timeout)
        close = getattr(connection, "close", None)
        if callable(close):
            close()
    except OSError as error:
        return NetworkSnapshot(
            online=False,
            latency_ms=None,
            quality=NetworkQuality.OFFLINE,
            checked_at=time.time(),
            error=str(error),
        )
    latency_ms = max(0.0, (time.monotonic() - started) * 1000.0)
    return NetworkSnapshot(
        online=True,
        latency_ms=latency_ms,
        quality=classify_network_quality(True, latency_ms),
        checked_at=time.time(),
    )


def classify_network_error(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 429:
            return "rate_limited"
        if error.code == 503:
            return "service_unavailable"
        if 500 <= error.code <= 599:
            return "server_error"
        return "http_error"
    if isinstance(error, socket.gaierror):
        return "dns_error"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    text = str(error).lower()
    if "ssl" in text or "certificate" in text:
        return "ssl_error"
    if "reset" in text:
        return "connection_reset"
    if "network is unreachable" in text or "not connected" in text:
        return "offline"
    return "network_error"
