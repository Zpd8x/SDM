from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sdm.duplicate_intelligence import DuplicateCandidate, DuplicateMatch, find_duplicate
from sdm.models import DownloadRecord
from sdm.remote_metadata import inspect_download_url
from sdm.site_adapters import build_adapter_plan
from sdm.smart_strategy import DownloadStrategy, choose_download_strategy
from sdm.utils import guess_filename


@dataclass(frozen=True, slots=True)
class LinkAnalysis:
    url: str
    final_url: str
    platform: str
    link_kind: str
    filename: str
    total_bytes: int
    mime_type: str
    connection_limit: int
    requires_auth: bool
    strategy: DownloadStrategy
    duplicate: DuplicateMatch | None = None
    warning: str = ""

    @property
    def downloadable(self) -> bool:
        return not bool(self.warning)


def analyze_link(
    url: str,
    *,
    filename: str = "",
    folder: str = "",
    records: list[DownloadRecord] | tuple[DownloadRecord, ...] = (),
    timeout: float = 6.0,
) -> LinkAnalysis:
    selected = str(url or "").strip()
    plan = build_adapter_plan(selected)
    parsed = urlsplit(selected)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()

    link_kind = "Direct file"
    if "playlist" in parsed.query.casefold() or "/playlist" in path:
        link_kind = "Playlist / collection"
    elif any(name in host for name in ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com")):
        link_kind = "Media page"
    elif path.endswith((".m3u8", ".mpd")):
        link_kind = "Streaming manifest"

    metadata = inspect_download_url(selected, timeout=timeout)
    resolved_name = Path(metadata.filename).name or Path(filename).name or guess_filename(metadata.final_url or selected)
    final_url = metadata.final_url or selected
    platform = plan.label
    if plan.adapter == "direct" and host:
        platform = host.removeprefix("www.")

    duplicate = None
    if records and folder and resolved_name:
        duplicate = find_duplicate(
            records,
            DuplicateCandidate(
                url=selected,
                filename=resolved_name,
                folder=folder,
                source_url=plan.source_url,
                total_bytes=metadata.total_bytes,
            ),
        )

    requires_auth = plan.adapter == "chatgpt"
    warning = ""
    if not parsed.scheme or parsed.scheme.casefold() not in {"http", "https"}:
        warning = "Only HTTP and HTTPS links are supported."

    strategy = choose_download_strategy(
        url=final_url,
        total_bytes=metadata.total_bytes,
        mime_type=metadata.mime_type,
        connection_limit=plan.connection_limit,
        accept_ranges=metadata.accept_ranges,
        latency_ms=metadata.latency_ms,
        requires_auth=requires_auth,
    )

    return LinkAnalysis(
        url=selected,
        final_url=final_url,
        platform=platform or "Direct link",
        link_kind=link_kind,
        filename=resolved_name,
        total_bytes=metadata.total_bytes,
        mime_type=metadata.mime_type,
        connection_limit=plan.connection_limit,
        requires_auth=requires_auth,
        duplicate=duplicate,
        strategy=strategy,
        warning=warning,
    )
