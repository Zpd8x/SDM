from __future__ import annotations

import base64
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sdm.config import USER_AGENT
from sdm.session_auth import (
    BrowserSession,
    open_session_url,
    session_user_agent,
)
from sdm.utils import guess_filename


ADAPTER_DIRECT = "direct"
ADAPTER_GOOGLE_DRIVE = "google-drive"
ADAPTER_DROPBOX = "dropbox"
ADAPTER_ONEDRIVE = "onedrive"
ADAPTER_CHATGPT = "chatgpt"
ADAPTER_LABELS = {
    ADAPTER_DIRECT: "Direct link",
    ADAPTER_GOOGLE_DRIVE: "Google Drive",
    ADAPTER_DROPBOX: "Dropbox",
    ADAPTER_ONEDRIVE: "OneDrive",
    ADAPTER_CHATGPT: "ChatGPT private file",
}
EXPIRING_QUERY_KEYS = frozenset(
    {
        "x-amz-algorithm",
        "x-amz-credential",
        "x-amz-date",
        "x-amz-expires",
        "x-amz-signature",
        "x-goog-algorithm",
        "x-goog-credential",
        "x-goog-date",
        "x-goog-expires",
        "x-goog-signature",
        "signature",
        "sig",
        "token",
        "download_token",
    }
)
_DRIVE_FILE_PATH = re.compile(r"/file/d/([^/]+)")
_CHATGPT_FILE_ID = re.compile(r"^file_[A-Za-z0-9_-]{6,256}$")
_CHATGPT_FILE_PATH = re.compile(r"/(file_[A-Za-z0-9_-]{6,256})(?:/|$)")


class SiteAdapterError(RuntimeError):
    """Raised when a stable site link cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class AdapterPlan:
    adapter: str
    source_url: str
    connection_limit: int

    @property
    def label(self) -> str:
        return ADAPTER_LABELS.get(self.adapter, self.adapter)


@dataclass(frozen=True, slots=True)
class AdapterResolution:
    url: str
    adapter: str
    source_url: str
    filename: str = ""
    total_bytes: int = 0
    mime_type: str = ""
    resolved_at: int = 0


def build_adapter_plan(
    selected_url: str,
    *,
    source_url: str = "",
    page_url: str = "",
) -> AdapterPlan:
    """Preserve a stable origin for browser URLs that commonly expire."""

    selected = _http_url(selected_url)
    supplied_source = _http_url(source_url)
    page = _http_url(page_url)
    candidates = tuple(
        value for value in (supplied_source, selected, page) if value
    )
    for candidate in candidates:
        adapter = detect_site_adapter(candidate)
        if adapter != ADAPTER_DIRECT:
            stable = canonical_source_url(candidate, adapter)
            if stable:
                return AdapterPlan(
                    adapter=adapter,
                    source_url=stable,
                    connection_limit=recommended_connection_limit(adapter),
                )

    if _is_chatgpt_page(page):
        captured = supplied_source or selected
        if captured:
            return AdapterPlan(
                adapter=ADAPTER_CHATGPT,
                source_url=canonical_source_url(captured, ADAPTER_CHATGPT),
                connection_limit=recommended_connection_limit(ADAPTER_CHATGPT),
            )

    # A signed CDN URL is not a useful long-term identity. Keep a matching
    # non-signed source URL when the extension supplied one.
    if selected and has_expiring_signature(selected):
        for candidate in (supplied_source, page):
            if candidate and not has_expiring_signature(candidate):
                return AdapterPlan(
                    adapter=ADAPTER_DIRECT,
                    source_url=candidate,
                    connection_limit=16,
                )
    return AdapterPlan(
        adapter=ADAPTER_DIRECT,
        source_url=supplied_source or selected,
        connection_limit=16,
    )


def detect_site_adapter(url: str) -> str:
    parsed = urlsplit(_http_url(url))
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if host in {"drive.google.com", "drive.usercontent.google.com"}:
        return ADAPTER_GOOGLE_DRIVE
    if host == "docs.google.com" and path.startswith(("/uc", "/document/")):
        return ADAPTER_GOOGLE_DRIVE
    if host == "dropbox.com" or host.endswith(".dropbox.com"):
        return ADAPTER_DROPBOX
    if host == "dropboxusercontent.com" or host.endswith(
        ".dropboxusercontent.com"
    ):
        return ADAPTER_DROPBOX
    if host == "1drv.ms" or host == "onedrive.live.com":
        return ADAPTER_ONEDRIVE
    if host == "api.onedrive.com":
        return ADAPTER_ONEDRIVE
    if host in {"chatgpt.com", "chat.openai.com"} and (
        "/backend-api/" in path or "/files/" in path
    ):
        return ADAPTER_CHATGPT
    return ADAPTER_DIRECT


def canonical_source_url(url: str, adapter: str | None = None) -> str:
    candidate = _http_url(url)
    if not candidate:
        return ""
    kind = adapter or detect_site_adapter(candidate)
    parsed = urlsplit(candidate)
    query = parse_qs(parsed.query, keep_blank_values=True)

    if kind == ADAPTER_GOOGLE_DRIVE:
        file_id = _drive_file_id(parsed.path, query)
        if file_id:
            return (
                "https://drive.google.com/uc?"
                + urlencode({"export": "download", "id": file_id})
            )
    elif kind == ADAPTER_DROPBOX:
        normalized_query = dict(query)
        normalized_query["dl"] = ["1"]
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(normalized_query, doseq=True),
                "",
            )
        )
    elif kind == ADAPTER_ONEDRIVE:
        if (parsed.hostname or "").casefold() == "api.onedrive.com":
            return candidate
        normalized_query = dict(query)
        normalized_query["download"] = ["1"]
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(normalized_query, doseq=True),
                "",
            )
        )
    elif kind == ADAPTER_CHATGPT:
        path_match = _CHATGPT_FILE_PATH.search(parsed.path)
        file_id = (
            _first(query.get("id"))
            or _first(query.get("file_id"))
            or (path_match.group(1) if path_match else "")
        )
        if file_id and _CHATGPT_FILE_ID.fullmatch(file_id):
            origin = (
                "https://chatgpt.com"
                if (parsed.hostname or "").casefold() == "chat.openai.com"
                else f"{parsed.scheme}://{parsed.netloc}"
            )
            origin_parts = urlsplit(origin)
            stable_query = (
                urlencode({"id": file_id})
                if _first(query.get("id")) or _first(query.get("file_id"))
                else ""
            )
            return urlunsplit(
                (
                    origin_parts.scheme,
                    origin_parts.netloc,
                    parsed.path,
                    stable_query,
                    "",
                )
            )
    return candidate


def resolve_site_url(
    source_url: str,
    *,
    adapter: str = "",
    session: BrowserSession | None = None,
    preferred_url: str = "",
    timeout: float = 12.0,
) -> AdapterResolution:
    kind = adapter or detect_site_adapter(source_url)
    stable = canonical_source_url(source_url, kind)
    if not stable:
        raise SiteAdapterError("The saved source URL is invalid.")
    if kind == ADAPTER_DIRECT:
        return AdapterResolution(
            url=stable,
            adapter=kind,
            source_url=stable,
            resolved_at=int(time.time()),
        )
    if kind == ADAPTER_CHATGPT and session is None:
        raise SiteAdapterError(
            "This ChatGPT file needs Secure Browser Session. "
            "Enable it in the SDM extension and capture the file again."
        )

    targets = [stable]
    preferred = _http_url(preferred_url)
    if (
        kind == ADAPTER_CHATGPT
        and preferred
        and preferred != stable
        and _same_chatgpt_file(preferred, stable)
    ):
        # ChatGPT download endpoints can require short-lived query fields on
        # the first request. Use the exact URL captured by the browser before
        # falling back to the stable file identity.
        targets.insert(0, preferred)

    response = None
    last_http_error: urllib.error.HTTPError | None = None
    for target in targets:
        request = urllib.request.Request(
            target,
            headers={
                "User-Agent": session_user_agent(session, USER_AGENT),
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Range": "bytes=0-0",
                "Connection": "close",
                **(
                    {"Referer": "https://chatgpt.com/"}
                    if kind == ADAPTER_CHATGPT
                    else {}
                ),
            },
            method="GET",
        )
        try:
            response = open_session_url(
                request,
                session=session,
                timeout=max(1.0, timeout),
            )
            break
        except urllib.error.HTTPError as error:
            if last_http_error is not None:
                last_http_error.close()
            last_http_error = error
            if error.code in {401, 403, 404} and target != targets[-1]:
                continue
            break
        except (urllib.error.URLError, OSError, ValueError) as error:
            if last_http_error is not None:
                last_http_error.close()
            raise SiteAdapterError(
                f"Could not refresh the {ADAPTER_LABELS.get(kind, kind)} link: "
                f"{error}"
            ) from error

    if response is None:
        assert last_http_error is not None
        try:
            if last_http_error.code in {401, 403}:
                raise SiteAdapterError(
                    f"{ADAPTER_LABELS.get(kind, kind)} authorization expired. "
                    "Capture the file again with Secure Browser Session enabled."
                ) from last_http_error
            raise SiteAdapterError(
                f"{ADAPTER_LABELS.get(kind, kind)} returned HTTP "
                f"{last_http_error.code}."
            ) from last_http_error
        finally:
            last_http_error.close()
    if last_http_error is not None:
        last_http_error.close()

    try:
        headers = response.headers
        final_url = _http_url(response.geturl()) or stable
        content_type = _header(headers, "Content-Type").split(";", 1)[0].strip()
        filename = _content_disposition_filename(
            _header(headers, "Content-Disposition")
        )
        content_range = _header(headers, "Content-Range")
        total_bytes = _total_bytes(
            content_range,
            _header(headers, "Content-Length"),
        )
        if content_type.startswith("text/html") and not filename:
            # Keep the adapter URL rather than caching a login/landing redirect.
            final_url = stable
        return AdapterResolution(
            url=final_url,
            adapter=kind,
            source_url=stable,
            filename=filename or _useful_url_filename(final_url),
            total_bytes=total_bytes,
            mime_type=content_type,
            resolved_at=int(time.time()),
        )
    finally:
        response.close()


def recommended_connection_limit(adapter: str) -> int:
    if adapter == ADAPTER_CHATGPT:
        return 2
    if adapter in {
        ADAPTER_GOOGLE_DRIVE,
        ADAPTER_DROPBOX,
        ADAPTER_ONEDRIVE,
    }:
        return 4
    return 16


def has_expiring_signature(url: str) -> bool:
    query = parse_qs(urlsplit(_http_url(url)).query)
    return any(key.casefold() in EXPIRING_QUERY_KEYS for key in query)


def is_stale_link_error(error: BaseException) -> bool:
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "http error 401",
            "http error 403",
            "http error 404",
            "authorization expired",
            "access denied",
            "expiredtoken",
            "signaturedoesnotmatch",
        )
    )


def onedrive_api_content_url(share_url: str) -> str:
    """Return the official OneDrive shares API content form for diagnostics."""

    encoded = base64.urlsafe_b64encode(share_url.encode("utf-8")).decode("ascii")
    share_id = "u!" + encoded.rstrip("=")
    return f"https://api.onedrive.com/v1.0/shares/{share_id}/root/content"


def _drive_file_id(path: str, query: Mapping[str, list[str]]) -> str:
    match = _DRIVE_FILE_PATH.search(path)
    value = match.group(1) if match else _first(query.get("id"))
    return value if re.fullmatch(r"[A-Za-z0-9_-]{6,256}", value) else ""


def _first(values: list[str] | None) -> str:
    return str(values[0]).strip() if values else ""


def _http_url(value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 8192:
        return ""
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate


def _header(headers: Mapping[str, object], name: str) -> str:
    getter = getattr(headers, "get", None)
    return str(getter(name, "") if getter else "").strip()


def _content_disposition_filename(value: str) -> str:
    if not value:
        return ""
    message = Message()
    message["Content-Disposition"] = value
    return Path(str(message.get_filename() or "").replace("\\", "/")).name


def _total_bytes(content_range: str, content_length: str) -> int:
    range_match = re.search(r"/(\d+)\s*$", content_range)
    raw = range_match.group(1) if range_match else content_length
    try:
        return max(0, int(raw))
    except (TypeError, ValueError, OverflowError):
        return 0


def _useful_url_filename(url: str) -> str:
    filename = guess_filename(url)
    return "" if Path(filename).stem.casefold() in {
        "",
        "content",
        "download",
        "file",
        "uc",
    } else filename


def _same_chatgpt_file(candidate: str, stable: str) -> bool:
    candidate_kind = detect_site_adapter(candidate)
    if candidate_kind == ADAPTER_CHATGPT:
        return canonical_source_url(candidate, ADAPTER_CHATGPT) == stable
    # The browser may expose only the redirected signed object URL. It is safe
    # to try it first: the secure cookie jar remains domain-scoped and cannot
    # leak ChatGPT cookies to the storage host.
    return has_expiring_signature(candidate)


def _is_chatgpt_page(url: str) -> bool:
    host = (urlsplit(_http_url(url)).hostname or "").casefold()
    return host in {"chatgpt.com", "chat.openai.com"}
