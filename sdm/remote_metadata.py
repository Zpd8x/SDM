from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sdm.config import USER_AGENT
from sdm.utils import guess_filename


GENERIC_FILENAMES = frozenset(
    {
        "",
        "content",
        "download",
        "file",
        "open",
        "uc",
        "view",
    }
)
CONTENT_RANGE_TOTAL = re.compile(r"/(\d+|\*)\s*$")


@dataclass(frozen=True, slots=True)
class RemoteMetadata:
    final_url: str = ""
    filename: str = ""
    total_bytes: int = 0
    mime_type: str = ""


def is_generic_filename(value: object) -> bool:
    filename = Path(str(value or "").strip()).name
    return Path(filename).stem.casefold() in GENERIC_FILENAMES


def parse_content_disposition(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    message = Message()
    message["Content-Disposition"] = raw
    filename = message.get_filename() or ""
    return Path(str(filename).replace("\\", "/")).name.strip()


def inspect_download_url(
    url: str,
    *,
    timeout: float = 6.0,
) -> RemoteMetadata:
    best = RemoteMetadata(final_url=url)
    for method, extra_headers in (
        ("HEAD", {}),
        ("GET", {"Range": "bytes=0-0"}),
    ):
        request = Request(
            url,
            method=method,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                **extra_headers,
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                current = metadata_from_headers(
                    response.headers,
                    final_url=response.geturl(),
                )
        except HTTPError as error:
            current = metadata_from_headers(
                error.headers,
                final_url=error.geturl() or url,
            )
            if error.code not in {405, 416} and not (
                current.filename or current.total_bytes
            ):
                continue
        except (URLError, OSError, ValueError):
            continue

        best = merge_metadata(best, current)
        if best.filename and best.total_bytes:
            break
    return best


def metadata_from_headers(
    headers: Mapping[str, object],
    *,
    final_url: str = "",
) -> RemoteMetadata:
    disposition = _header(headers, "Content-Disposition")
    filename = parse_content_disposition(disposition)
    content_range = _header(headers, "Content-Range")
    content_length = _nonnegative_int(_header(headers, "Content-Length"))
    range_match = CONTENT_RANGE_TOTAL.search(content_range)
    total_bytes = (
        _nonnegative_int(range_match.group(1))
        if range_match and range_match.group(1) != "*"
        else content_length
    )
    content_type = _header(headers, "Content-Type").split(";", 1)[0].strip()
    return RemoteMetadata(
        final_url=str(final_url or ""),
        filename=filename,
        total_bytes=total_bytes,
        mime_type=content_type,
    )


def enrich_download_payload(
    payload: Mapping[str, Any],
    *,
    inspector=inspect_download_url,
) -> dict[str, Any]:
    enriched = dict(payload)
    if str(enriched.get("action", "")).strip().casefold() != "download":
        return enriched
    if str(enriched.get("media_kind", "direct")).casefold() != "direct":
        return enriched

    url = str(enriched.get("url", "")).strip()
    if urlparse(url).scheme.casefold() not in {"http", "https"}:
        return enriched
    current_filename = Path(str(enriched.get("filename", ""))).name
    current_total = _nonnegative_int(enriched.get("total_bytes", 0))
    current_mime = str(enriched.get("mime_type", "")).strip()
    if not url or (
        not is_generic_filename(current_filename)
        and current_total > 0
        and current_mime
    ):
        return enriched

    metadata = inspector(url)
    header_filename = Path(metadata.filename).name
    if not header_filename and metadata.final_url:
        redirected_name = guess_filename(metadata.final_url)
        if not is_generic_filename(redirected_name):
            header_filename = redirected_name
    if header_filename and (
        not current_filename or is_generic_filename(current_filename)
    ):
        enriched["filename"] = header_filename
    elif not current_filename:
        enriched["filename"] = guess_filename(metadata.final_url or url)
    if metadata.total_bytes > 0 and current_total <= 0:
        enriched["total_bytes"] = metadata.total_bytes
    if metadata.mime_type and not current_mime:
        enriched["mime_type"] = metadata.mime_type
    if metadata.final_url:
        enriched["url"] = metadata.final_url
    return enriched


def merge_metadata(
    original: RemoteMetadata,
    new: RemoteMetadata,
) -> RemoteMetadata:
    return RemoteMetadata(
        final_url=new.final_url or original.final_url,
        filename=new.filename or original.filename,
        total_bytes=new.total_bytes or original.total_bytes,
        mime_type=new.mime_type or original.mime_type,
    )


def _header(headers: Mapping[str, object], name: str) -> str:
    getter = getattr(headers, "get", None)
    return str(getter(name, "") if getter else "").strip()


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0
