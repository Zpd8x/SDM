from __future__ import annotations

import hashlib
import re
from pathlib import Path


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def normalize_sha256(value: str) -> str:
    return str(value or "").strip().lower()


def is_valid_sha256(value: str) -> bool:
    normalized = normalize_sha256(value)
    return not normalized or SHA256_PATTERN.fullmatch(normalized) is not None


def compute_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
