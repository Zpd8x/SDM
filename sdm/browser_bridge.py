from __future__ import annotations

from contextlib import closing

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sdm.categories import categorize_filename
from sdm.database import (
    SCHEMA,
    DownloadRepository,
    utc_now,
)
from sdm.duplicate_intelligence import (
    DuplicateCandidate,
    DuplicateDisposition,
    canonical_download_identity,
    find_duplicate,
)
from sdm.models import DownloadStatus
from sdm.session_auth import (
    SessionAuthError,
    store_session_auth,
    validate_session_payload,
)
from sdm.site_adapters import (
    ADAPTER_CHATGPT,
    build_adapter_plan,
    detect_site_adapter,
)
from sdm.smart_capture import resolve_smart_capture
from sdm.smart_rules import (
    RULES_SETTING_KEY,
    RuleContext,
    deserialize_rules,
    evaluate_rules,
)
from sdm.utils import guess_filename, sanitize_filename, validate_download_url


ALLOWED_CONNECTIONS = frozenset({1, 2, 4, 8, 16})
MAX_URL_LENGTH = 8192


@dataclass(frozen=True, slots=True)
class BrowserEnqueueResult:
    record_id: str
    filename: str
    folder: str
    start_immediately: bool
    session_attached: bool = False
    site_adapter: str = "direct"
    adapter_label: str = "Direct link"
    capture_pending: bool = True
    duplicate: bool = False
    duplicate_action: str = ""
    rule_reason: str = ""


class BrowserRequestError(ValueError):
    pass


def enqueue_browser_download(
    database_path: str | Path,
    payload: dict[str, Any],
    *,
    default_folder: str | Path | None = None,
) -> BrowserEnqueueResult:
    decision = resolve_smart_capture(payload)
    url = decision.url
    if len(url) > MAX_URL_LENGTH:
        raise BrowserRequestError("The URL is too long.")
    valid, error = validate_download_url(url)
    if not valid:
        raise BrowserRequestError(error)

    media_kind = decision.media_kind
    captured_request_url = str(
        payload.get("request_url")
        or payload.get("source_url")
        or payload.get("original_url")
        or payload.get("url")
        or ""
    ).strip()
    page_url = str(payload.get("page_url") or "")
    adapter_plan = build_adapter_plan(
        decision.url,
        source_url=captured_request_url,
        page_url=page_url,
    )
    if adapter_plan.adapter == ADAPTER_CHATGPT:
        for candidate in (
            captured_request_url,
            str(payload.get("source_url") or "").strip(),
            decision.url,
        ):
            if (
                len(candidate) <= MAX_URL_LENGTH
                and detect_site_adapter(candidate) == ADAPTER_CHATGPT
            ):
                url = candidate
                break

    raw_filename = decision.filename or str(payload.get("filename", "")).strip()
    default_filename = (
        ("Browser audio.m4a" if media_kind == "audio" else "Browser video.mp4")
        if media_kind != "direct"
        else guess_filename(url)
    )
    requested_filename = sanitize_filename(raw_filename or default_filename)
    try:
        requested_connections = int(payload.get("connections", 4))
    except (TypeError, ValueError) as error:
        raise BrowserRequestError("Invalid connection count.") from error
    if requested_connections not in ALLOWED_CONNECTIONS:
        raise BrowserRequestError(
            "Connections must be one of: 1, 2, 4, 8, or 16."
        )
    requested_connections = min(
        requested_connections,
        adapter_plan.connection_limit,
    )
    start_immediately = bool(payload.get("start_immediately", True))
    total_bytes = decision.total_bytes or _nonnegative_int(
        payload.get("total_bytes", 0)
    )
    mime_type = decision.mime_type
    referer = decision.referer

    database = Path(database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    folder = _resolve_download_folder(database, default_folder)
    rules = _load_browser_rules(database)
    rule = evaluate_rules(
        rules,
        RuleContext(
            url=url,
            filename=requested_filename,
            source_url=adapter_plan.source_url,
            page_url=referer or page_url,
            adapter=adapter_plan.adapter,
            media_kind=media_kind,
            mime_type=mime_type,
            category=categorize_filename(requested_filename),
            total_bytes=total_bytes,
        ),
    )
    if rule.folder:
        folder = Path(rule.folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    if rule.connections:
        requested_connections = min(
            rule.connections,
            adapter_plan.connection_limit,
        )
    if rule.start_immediately is not None:
        start_immediately = rule.start_immediately
    category = rule.category or categorize_filename(requested_filename)
    identity_key = canonical_download_identity(
        url,
        source_url=adapter_plan.source_url,
        page_url=referer or page_url,
    )

    session = None
    raw_session = payload.get("session_auth")
    if isinstance(raw_session, dict) and raw_session.get("enabled"):
        if media_kind != "direct":
            raise BrowserRequestError(
                "Secure Session Bridge supports direct file downloads only."
            )
        session = validate_session_payload(raw_session)
    if adapter_plan.adapter == ADAPTER_CHATGPT and session is None:
        raise BrowserRequestError(
            "ChatGPT private files require Secure Browser Session. "
            "Enable it in the SDM extension, then capture the file again."
        )

    timestamp = utc_now()
    new_record_id = str(uuid.uuid4())
    result_record_id = new_record_id
    result_filename = requested_filename
    result_folder = str(folder)
    capture_pending = True
    duplicate = False
    duplicate_action = ""
    session_target_allowed = True

    for attempt in range(5):
        try:
            with closing(sqlite3.connect(database, timeout=15)) as connection, connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA busy_timeout = 15000")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(SCHEMA)
                _migrate_browser_columns(connection)
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")

                existing_records = [
                    DownloadRepository._from_row(row)
                    for row in connection.execute(
                        "SELECT * FROM downloads ORDER BY created_at DESC"
                    ).fetchall()
                ]
                match = find_duplicate(
                    existing_records,
                    DuplicateCandidate(
                        url=url,
                        filename=requested_filename,
                        folder=str(folder),
                        source_url=adapter_plan.source_url,
                        site_adapter=adapter_plan.adapter,
                        referer=referer,
                        total_bytes=total_bytes,
                    ),
                )
                if match is not None:
                    duplicate = True
                    existing = match.record
                    result_record_id = existing.id
                    result_filename = existing.filename
                    result_folder = existing.folder
                    if match.disposition == DuplicateDisposition.RESUMABLE:
                        duplicate_action = "resume"
                        capture_pending = True
                        connection.execute(
                            """
                            UPDATE downloads
                            SET url = ?, source_url = ?, site_adapter = ?,
                                adapter_status = 'Ready', resolved_at = '',
                                total_bytes = CASE
                                    WHEN total_bytes > 0 THEN total_bytes
                                    ELSE ?
                                END,
                                connections = ?, auto_start = ?,
                                capture_pending = 1, status = ?,
                                error = '', identity_key = ?, rule_id = ?,
                                rule_reason = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                url,
                                adapter_plan.source_url,
                                adapter_plan.adapter,
                                total_bytes,
                                requested_connections,
                                int(start_immediately),
                                (
                                    DownloadStatus.QUEUED.value
                                    if start_immediately
                                    else DownloadStatus.PAUSED.value
                                ),
                                identity_key,
                                rule.rule_id,
                                rule.reason if rule.matched else "",
                                timestamp,
                                existing.id,
                            ),
                        )
                    elif match.disposition == DuplicateDisposition.COMPLETED:
                        duplicate_action = "completed"
                        capture_pending = False
                        session_target_allowed = False
                    else:
                        duplicate_action = "active"
                        capture_pending = False
                        session_target_allowed = False
                else:
                    result_filename = _choose_available_filename(
                        connection,
                        folder,
                        requested_filename,
                    )
                    connection.execute(
                        """
                        INSERT INTO downloads (
                            id, url, filename, folder, total_bytes,
                            downloaded_bytes, status, created_at, updated_at,
                            error, etag, last_modified, connections, transfer_mode,
                            source, auto_start, category, description,
                            capture_pending, media_kind, mime_type, referer,
                            source_url, site_adapter, adapter_status, resolved_at,
                            identity_key, rule_id, rule_reason
                        ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, '', '', '', ?,
                                  'Auto', 'browser', ?, ?, '', 1, ?, ?, ?, ?,
                                  ?, 'Ready', '', ?, ?, ?)
                        """,
                        (
                            new_record_id,
                            url,
                            result_filename,
                            str(folder),
                            total_bytes,
                            (
                                DownloadStatus.QUEUED.value
                                if start_immediately
                                else DownloadStatus.PAUSED.value
                            ),
                            timestamp,
                            timestamp,
                            requested_connections,
                            int(start_immediately),
                            category,
                            media_kind,
                            mime_type,
                            referer,
                            adapter_plan.source_url,
                            adapter_plan.adapter,
                            identity_key,
                            rule.rule_id,
                            rule.reason if rule.matched else "",
                        ),
                    )
            break
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or attempt == 4:
                raise
            time.sleep(0.05 * (2**attempt))

    session_attached = False
    if session is not None and session_target_allowed:
        try:
            store_session_auth(database, result_record_id, session)
            session_attached = True
        except BaseException:
            if not duplicate:
                with closing(sqlite3.connect(database, timeout=15)) as connection, connection:
                    connection.execute(
                        "DELETE FROM downloads WHERE id = ?",
                        (result_record_id,),
                    )
            raise

    return BrowserEnqueueResult(
        record_id=result_record_id,
        filename=result_filename,
        folder=result_folder,
        start_immediately=start_immediately,
        session_attached=session_attached,
        site_adapter=adapter_plan.adapter,
        adapter_label=adapter_plan.label,
        capture_pending=capture_pending,
        duplicate=duplicate,
        duplicate_action=duplicate_action,
        rule_reason=rule.reason if rule.matched else "",
    )


def handle_native_message(
    database_path: str | Path,
    payload: Any,
    *,
    default_folder: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "The native message must be an object."}

    action = str(payload.get("action", "")).strip().lower()
    if action == "ping":
        return {"ok": True, "action": "pong"}
    if action == "browser_status":
        return _browser_status(database_path)
    if action == "batch_download":
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return {"ok": False, "error": "Batch items must be a non-empty list."}
        if len(items) > 100:
            return {"ok": False, "error": "A browser batch is limited to 100 items."}
        results: list[dict[str, Any]] = []
        accepted = 0
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                results.append({"ok": False, "index": index, "error": "Item must be an object."})
                continue
            child = dict(item)
            child["action"] = "download"
            response = handle_native_message(database_path, child, default_folder=default_folder)
            response["index"] = index
            results.append(response)
            accepted += int(bool(response.get("ok")))
        return {
            "ok": accepted == len(items),
            "partial": 0 < accepted < len(items),
            "accepted": accepted,
            "failed": len(items) - accepted,
            "results": results,
            "protocol_version": 2,
        }
    if action != "download":
        return {"ok": False, "error": "Unsupported native action."}

    try:
        result = enqueue_browser_download(
            database_path,
            payload,
            default_folder=default_folder,
        )
    except (
        BrowserRequestError,
        SessionAuthError,
        OSError,
        sqlite3.Error,
    ) as error:
        return {"ok": False, "error": str(error)}

    return {
        "ok": True,
        "record_id": result.record_id,
        "filename": result.filename,
        "folder": result.folder,
        "start_immediately": result.start_immediately,
        "capture_pending": result.capture_pending,
        "session_attached": result.session_attached,
        "site_adapter": result.site_adapter,
        "adapter_label": result.adapter_label,
        "duplicate": result.duplicate,
        "duplicate_action": result.duplicate_action,
        "rule_reason": result.rule_reason,
    }



def _browser_status(database_path: str | Path) -> dict[str, Any]:
    database = Path(database_path)
    queued = active = completed = 0
    try:
        with closing(sqlite3.connect(database, timeout=5)) as connection, connection:
            connection.executescript(SCHEMA)
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM downloads GROUP BY status"
            ).fetchall()
        counts = {str(status).casefold(): int(count) for status, count in rows}
        queued = counts.get("queued", 0) + counts.get("paused", 0)
        active = counts.get("downloading", 0)
        completed = counts.get("completed", 0)
    except sqlite3.Error:
        pass
    return {
        "ok": True,
        "action": "browser_status",
        "protocol_version": 2,
        "capabilities": [
            "download",
            "batch_download",
            "browser_status",
            "secure_session",
            "media_capture",
        ],
        "database_ready": database.exists(),
        "queued": queued,
        "active": active,
        "completed": completed,
    }

def is_application_running(
    heartbeat_path: str | Path,
    *,
    maximum_age_seconds: float = 8.0,
) -> bool:
    path = Path(heartbeat_path)
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return False
    return age <= maximum_age_seconds


def acquire_launch_guard(
    guard_path: str | Path,
    *,
    stale_after_seconds: float = 30.0,
) -> bool:
    path = Path(guard_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
    except FileExistsError:
        try:
            age = max(0.0, time.time() - path.stat().st_mtime)
        except OSError:
            return False
        if age <= stale_after_seconds:
            return False
        try:
            path.unlink()
        except OSError:
            return False
        return acquire_launch_guard(
            path,
            stale_after_seconds=stale_after_seconds,
        )
    else:
        os.close(descriptor)
        return True


def release_launch_guard(guard_path: str | Path) -> None:
    try:
        Path(guard_path).unlink(missing_ok=True)
    except OSError:
        pass


def _resolve_download_folder(
    database_path: Path,
    default_folder: str | Path | None,
) -> Path:
    if default_folder is not None:
        return Path(default_folder).expanduser()

    try:
        with closing(sqlite3.connect(database_path, timeout=15)) as connection, connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("browser_download_folder",),
            ).fetchone()
    except sqlite3.Error:
        row = None
    if row and str(row[0]).strip():
        return Path(str(row[0])).expanduser()

    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else Path.home()


def _load_browser_rules(database_path: Path):
    with closing(sqlite3.connect(database_path, timeout=15)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.executescript(SCHEMA)
        _migrate_browser_columns(connection)
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (RULES_SETTING_KEY,),
        ).fetchone()
    return deserialize_rules(str(row[0]) if row else "")


def _choose_available_filename(
    connection: sqlite3.Connection,
    folder: Path,
    requested: str,
) -> str:
    rows = connection.execute(
        "SELECT filename FROM downloads WHERE folder = ?",
        (str(folder),),
    ).fetchall()
    reserved = {str(row[0]).casefold() for row in rows}
    candidate = requested
    suffix = Path(requested).suffix
    stem = Path(requested).stem
    index = 1
    while candidate.casefold() in reserved or (folder / candidate).exists():
        candidate = sanitize_filename(f"{stem} ({index}){suffix}")
        index += 1
    return candidate


def _migrate_browser_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(downloads)").fetchall()
    }
    migrations = {
        "connections": (
            "ALTER TABLE downloads "
            "ADD COLUMN connections INTEGER NOT NULL DEFAULT 4"
        ),
        "adaptive_connections": (
            "ALTER TABLE downloads "
            "ADD COLUMN adaptive_connections INTEGER NOT NULL DEFAULT 4"
        ),
        "adaptive_reason": (
            "ALTER TABLE downloads "
            "ADD COLUMN adaptive_reason TEXT NOT NULL DEFAULT ''"
        ),
        "transfer_mode": (
            "ALTER TABLE downloads "
            "ADD COLUMN transfer_mode TEXT NOT NULL DEFAULT 'Auto'"
        ),
        "source": (
            "ALTER TABLE downloads "
            "ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        ),
        "auto_start": (
            "ALTER TABLE downloads "
            "ADD COLUMN auto_start INTEGER NOT NULL DEFAULT 0"
        ),
        "category": (
            "ALTER TABLE downloads "
            "ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'"
        ),
        "scheduled_at": (
            "ALTER TABLE downloads "
            "ADD COLUMN scheduled_at TEXT NOT NULL DEFAULT ''"
        ),
        "checksum_sha256": (
            "ALTER TABLE downloads "
            "ADD COLUMN checksum_sha256 TEXT NOT NULL DEFAULT ''"
        ),
        "checksum_actual": (
            "ALTER TABLE downloads "
            "ADD COLUMN checksum_actual TEXT NOT NULL DEFAULT ''"
        ),
        "checksum_status": (
            "ALTER TABLE downloads "
            "ADD COLUMN checksum_status TEXT NOT NULL DEFAULT 'Not set'"
        ),
        "description": (
            "ALTER TABLE downloads "
            "ADD COLUMN description TEXT NOT NULL DEFAULT ''"
        ),
        "capture_pending": (
            "ALTER TABLE downloads "
            "ADD COLUMN capture_pending INTEGER NOT NULL DEFAULT 0"
        ),
        "media_kind": (
            "ALTER TABLE downloads "
            "ADD COLUMN media_kind TEXT NOT NULL DEFAULT 'direct'"
        ),
        "mime_type": (
            "ALTER TABLE downloads "
            "ADD COLUMN mime_type TEXT NOT NULL DEFAULT ''"
        ),
        "referer": (
            "ALTER TABLE downloads "
            "ADD COLUMN referer TEXT NOT NULL DEFAULT ''"
        ),
        "source_url": (
            "ALTER TABLE downloads "
            "ADD COLUMN source_url TEXT NOT NULL DEFAULT ''"
        ),
        "site_adapter": (
            "ALTER TABLE downloads "
            "ADD COLUMN site_adapter TEXT NOT NULL DEFAULT 'direct'"
        ),
        "adapter_status": (
            "ALTER TABLE downloads "
            "ADD COLUMN adapter_status TEXT NOT NULL DEFAULT ''"
        ),
        "resolved_at": (
            "ALTER TABLE downloads "
            "ADD COLUMN resolved_at TEXT NOT NULL DEFAULT ''"
        ),
        "identity_key": (
            "ALTER TABLE downloads "
            "ADD COLUMN identity_key TEXT NOT NULL DEFAULT ''"
        ),
        "rule_id": (
            "ALTER TABLE downloads "
            "ADD COLUMN rule_id TEXT NOT NULL DEFAULT ''"
        ),
        "rule_reason": (
            "ALTER TABLE downloads "
            "ADD COLUMN rule_reason TEXT NOT NULL DEFAULT ''"
        ),
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_downloads_identity "
        "ON downloads(identity_key)"
    )


def _nonnegative_int(value: object) -> int:
    try:
        return min(2**63 - 1, max(0, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 0
