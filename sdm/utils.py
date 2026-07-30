from __future__ import annotations

import math
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_download_url(url: str) -> tuple[bool, str]:
    candidate = url.strip()
    if not candidate:
        return False, "Enter a download URL."

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "Only HTTP and HTTPS URLs are supported in this version."
    if not parsed.netloc:
        return False, "The URL does not contain a valid host."
    return True, ""


def sanitize_filename(filename: str, fallback: str = "download.bin") -> str:
    cleaned = unquote(filename).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(" .")

    if not cleaned:
        cleaned = fallback

    stem = Path(cleaned).stem.upper()
    if stem in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    if len(cleaned) > 180:
        suffix = Path(cleaned).suffix[:20]
        stem_length = max(1, 180 - len(suffix))
        cleaned = f"{Path(cleaned).stem[:stem_length]}{suffix}"

    return cleaned


def guess_filename(url: str) -> str:
    parsed = urlparse(url.strip())
    candidate = Path(unquote(parsed.path)).name
    return sanitize_filename(candidate or "download.bin")


def format_bytes(value: int | float) -> str:
    number = max(0.0, float(value))
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while number >= 1024 and unit_index < len(units) - 1:
        number /= 1024
        unit_index += 1
    precision = 0 if unit_index == 0 else 2
    return f"{number:.{precision}f} {units[unit_index]}"


def format_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return "—"
    return f"{format_bytes(bytes_per_second)}/s"


def format_eta(seconds: int | float | None) -> str:
    if seconds is None or seconds < 0 or math.isinf(float(seconds)):
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
