from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sdm.categories import categorize_filename, normalize_category
from sdm.checksum import normalize_sha256
from sdm.adaptive_connections import (
    ServerConnectionProfile,
    initial_connection_count,
    normalize_connection_count,
    server_key,
)
from sdm.duplicate_intelligence import canonical_download_identity
from sdm.models import DownloadRecord, DownloadStatus
from sdm.schedule import normalize_scheduled_at
from sdm.session_auth import delete_all_session_auth, delete_session_auth
from sdm.site_adapters import build_adapter_plan


SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    filename TEXT NOT NULL,
    folder TEXT NOT NULL,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    etag TEXT NOT NULL DEFAULT '',
    last_modified TEXT NOT NULL DEFAULT '',
    connections INTEGER NOT NULL DEFAULT 4,
    adaptive_connections INTEGER NOT NULL DEFAULT 4,
    adaptive_reason TEXT NOT NULL DEFAULT '',
    transfer_mode TEXT NOT NULL DEFAULT 'Auto',
    source TEXT NOT NULL DEFAULT 'manual',
    auto_start INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'Other',
    scheduled_at TEXT NOT NULL DEFAULT '',
    checksum_sha256 TEXT NOT NULL DEFAULT '',
    checksum_actual TEXT NOT NULL DEFAULT '',
    checksum_status TEXT NOT NULL DEFAULT 'Not set',
    description TEXT NOT NULL DEFAULT '',
    capture_pending INTEGER NOT NULL DEFAULT 0,
    media_kind TEXT NOT NULL DEFAULT 'direct',
    mime_type TEXT NOT NULL DEFAULT '',
    referer TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    site_adapter TEXT NOT NULL DEFAULT 'direct',
    adapter_status TEXT NOT NULL DEFAULT '',
    resolved_at TEXT NOT NULL DEFAULT '',
    identity_key TEXT NOT NULL DEFAULT '',
    rule_id TEXT NOT NULL DEFAULT '',
    rule_reason TEXT NOT NULL DEFAULT '',
    content_sha256 TEXT NOT NULL DEFAULT '',
    content_fingerprint_status TEXT NOT NULL DEFAULT 'Pending',
    duplicate_of_id TEXT NOT NULL DEFAULT '',
    media_format TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_downloads_created_at
    ON downloads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_status
    ON downloads(status);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS network_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_network_events_created_at
    ON network_events(created_at DESC);
CREATE TABLE IF NOT EXISTS server_profiles (
    server_key TEXT PRIMARY KEY,
    preferred_connections INTEGER NOT NULL DEFAULT 4,
    rate_limit_events INTEGER NOT NULL DEFAULT 0,
    success_streak INTEGER NOT NULL DEFAULT 0,
    last_status TEXT NOT NULL DEFAULT '',
    cooldown_until TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


UPDATABLE_FIELDS = {
    "url",
    "filename",
    "folder",
    "total_bytes",
    "downloaded_bytes",
    "status",
    "error",
    "etag",
    "last_modified",
    "connections",
    "adaptive_connections",
    "adaptive_reason",
    "transfer_mode",
    "source",
    "auto_start",
    "category",
    "scheduled_at",
    "checksum_sha256",
    "checksum_actual",
    "checksum_status",
    "description",
    "capture_pending",
    "media_kind",
    "mime_type",
    "referer",
    "source_url",
    "site_adapter",
    "adapter_status",
    "resolved_at",
    "identity_key",
    "rule_id",
    "rule_reason",
    "content_sha256",
    "content_fingerprint_status",
    "duplicate_of_id",
    "media_format",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DownloadRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._initialize()
        self.recover_interrupted_downloads()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            self._migrate_download_columns(connection)

    @staticmethod
    def _migrate_download_columns(connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
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
            "content_sha256": (
                "ALTER TABLE downloads "
                "ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''"
            ),
            "content_fingerprint_status": (
                "ALTER TABLE downloads "
                "ADD COLUMN content_fingerprint_status TEXT NOT NULL DEFAULT 'Pending'"
            ),
            "duplicate_of_id": (
                "ALTER TABLE downloads "
                "ADD COLUMN duplicate_of_id TEXT NOT NULL DEFAULT ''"
            ),
            "media_format": (
                "ALTER TABLE downloads "
                "ADD COLUMN media_format TEXT NOT NULL DEFAULT ''"
            ),
        }
        for column, statement in migrations.items():
            if column not in existing_columns:
                connection.execute(statement)
        rows = connection.execute(
            """
            SELECT id, filename, category, url, source_url, site_adapter,
                   referer, identity_key
            FROM downloads
            """
        ).fetchall()
        for row in rows:
            detected = categorize_filename(str(row["filename"]))
            current = str(row["category"] or "")
            if detected != "Other" and current in {"", "Other"}:
                connection.execute(
                    "UPDATE downloads SET category = ? WHERE id = ?",
                    (detected, str(row["id"])),
                )
            if not str(row["source_url"] or "").strip():
                plan = build_adapter_plan(str(row["url"] or ""))
                connection.execute(
                    """
                    UPDATE downloads
                    SET source_url = ?, site_adapter = ?, adapter_status = ?
                    WHERE id = ?
                    """,
                    (
                        plan.source_url,
                        plan.adapter,
                        "Migrated",
                        str(row["id"]),
                    ),
                )
            if not str(row["identity_key"] or "").strip():
                connection.execute(
                    "UPDATE downloads SET identity_key = ? WHERE id = ?",
                    (
                        canonical_download_identity(
                            str(row["url"] or ""),
                            source_url=str(row["source_url"] or ""),
                            page_url=str(row["referer"] or ""),
                        ),
                        str(row["id"]),
                    ),
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_downloads_identity "
            "ON downloads(identity_key)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_downloads_content_sha256 "
            "ON downloads(content_sha256)"
        )

    def create_download(
        self,
        *,
        url: str,
        filename: str,
        folder: str,
        connections: int = 4,
        source: str = "manual",
        auto_start: bool = False,
        start_immediately: bool = True,
        category: str = "Auto",
        scheduled_at: str = "",
        checksum_sha256: str = "",
        description: str = "",
        capture_pending: bool = False,
        media_kind: str = "direct",
        mime_type: str = "",
        referer: str = "",
        source_url: str = "",
        site_adapter: str = "",
        rule_id: str = "",
        rule_reason: str = "",
        media_format: str = "",
    ) -> DownloadRecord:
        timestamp = utc_now()
        normalized_schedule = normalize_scheduled_at(scheduled_at)
        expected_checksum = normalize_sha256(checksum_sha256)
        if normalized_schedule:
            initial_status = DownloadStatus.SCHEDULED
        elif start_immediately:
            initial_status = DownloadStatus.QUEUED
        else:
            initial_status = DownloadStatus.PAUSED
        adapter_plan = build_adapter_plan(
            url,
            source_url=source_url,
            page_url=referer,
        )
        record = DownloadRecord(
            id=str(uuid.uuid4()),
            url=url,
            filename=filename,
            folder=folder,
            status=initial_status,
            created_at=timestamp,
            updated_at=timestamp,
            connections=max(
                1,
                min(
                    16,
                    adapter_plan.connection_limit,
                    int(connections),
                ),
            ),
            source=source,
            auto_start=bool(auto_start),
            category=normalize_category(category, filename),
            scheduled_at=normalized_schedule,
            checksum_sha256=expected_checksum,
            checksum_status="Pending" if expected_checksum else "Not set",
            description=str(description).strip(),
            capture_pending=bool(capture_pending),
            media_kind=normalize_media_kind(media_kind),
            mime_type=str(mime_type).strip()[:255],
            referer=str(referer).strip()[:8192],
            source_url=adapter_plan.source_url,
            site_adapter=site_adapter or adapter_plan.adapter,
            identity_key=canonical_download_identity(
                url,
                source_url=adapter_plan.source_url,
                page_url=referer,
            ),
            rule_id=str(rule_id).strip()[:128],
            rule_reason=str(rule_reason).strip()[:1000],
            media_format=str(media_format).strip()[:128],
        )
        record.adaptive_connections = record.connections
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO downloads (
                    id, url, filename, folder, total_bytes, downloaded_bytes,
                    status, created_at, updated_at, error, etag, last_modified,
                    connections, adaptive_connections, adaptive_reason,
                    transfer_mode, source, auto_start, category,
                    scheduled_at, checksum_sha256, checksum_actual,
                    checksum_status, description, capture_pending, media_kind,
                    mime_type, referer, source_url, site_adapter,
                    adapter_status, resolved_at, identity_key, rule_id,
                    rule_reason, content_sha256, content_fingerprint_status,
                    duplicate_of_id, media_format
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.url,
                    record.filename,
                    record.folder,
                    record.total_bytes,
                    record.downloaded_bytes,
                    record.status.value,
                    record.created_at,
                    record.updated_at,
                    record.error,
                    record.etag,
                    record.last_modified,
                    record.connections,
                    record.adaptive_connections,
                    record.adaptive_reason,
                    record.transfer_mode,
                    record.source,
                    int(record.auto_start),
                    record.category,
                    record.scheduled_at,
                    record.checksum_sha256,
                    record.checksum_actual,
                    record.checksum_status,
                    record.description,
                    int(record.capture_pending),
                    record.media_kind,
                    record.mime_type,
                    record.referer,
                    record.source_url,
                    record.site_adapter,
                    record.adapter_status,
                    record.resolved_at,
                    record.identity_key,
                    record.rule_id,
                    record.rule_reason,
                    record.content_sha256,
                    record.content_fingerprint_status,
                    record.duplicate_of_id,
                    record.media_format,
                ),
            )
        return record

    def get(self, record_id: str) -> DownloadRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM downloads WHERE id = ?", (record_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> list[DownloadRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM downloads ORDER BY created_at DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, record_id: str, **fields: Any) -> None:
        if not fields:
            return

        unknown = set(fields) - UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported download fields: {sorted(unknown)}")

        normalized: dict[str, Any] = {}
        for name, value in fields.items():
            if name == "status" and isinstance(value, DownloadStatus):
                normalized[name] = value.value
            else:
                normalized[name] = value
        normalized["updated_at"] = utc_now()

        assignments = ", ".join(f"{name} = ?" for name in normalized)
        values = [*normalized.values(), record_id]
        with self._write_lock, self._connect() as connection:
            connection.execute(
                f"UPDATE downloads SET {assignments} WHERE id = ?", values
            )

    def delete(self, record_id: str) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
        delete_session_auth(self.database_path, record_id)

    def delete_all(self) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM downloads")
            deleted = max(0, int(cursor.rowcount))
        delete_all_session_auth(self.database_path)
        return deleted

    def get_setting(self, key: str, default: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str | int) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )

    def get_server_profile(
        self,
        url: str,
    ) -> ServerConnectionProfile | None:
        key = server_key(url)
        if not key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM server_profiles WHERE server_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return ServerConnectionProfile(
            server_key=str(row["server_key"]),
            preferred_connections=normalize_connection_count(
                row["preferred_connections"]
            ),
            rate_limit_events=max(0, int(row["rate_limit_events"])),
            success_streak=max(0, int(row["success_streak"])),
            last_status=str(row["last_status"] or ""),
            cooldown_until=str(row["cooldown_until"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def prepare_adaptive_download(
        self,
        record_id: str,
    ) -> DownloadRecord | None:
        record = self.get(record_id)
        if record is None:
            return None
        profile = self.get_server_profile(record.url)
        effective = initial_connection_count(record.connections, profile)
        if profile is None or effective == record.connections:
            reason = "Adaptive mode: using the selected connection limit."
        else:
            reason = (
                f"Adaptive mode: this server is currently limited to "
                f"{effective} of {record.connections} connections."
            )
        self.update(
            record_id,
            adaptive_connections=effective,
            adaptive_reason=reason,
            transfer_mode=f"Adaptive {effective}/{record.connections}",
        )
        return self.get(record_id)

    def record_adaptive_feedback(
        self,
        record_id: str,
        *,
        effective: int,
        kind: str,
        reason: str,
    ) -> None:
        record = self.get(record_id)
        if record is None:
            return
        key = server_key(record.url)
        if not key:
            return
        target = normalize_connection_count(record.connections)
        record_effective = max(
            1,
            min(target, normalize_connection_count(effective)),
        )
        preferred = record_effective
        normalized_kind = (
            kind if kind in {"rate_limit", "recovery", "completed"} else "status"
        )
        timestamp = utc_now()
        with self._write_lock, self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM server_profiles WHERE server_key = ?",
                (key,),
            ).fetchone()
            rate_limit_events = (
                max(0, int(current["rate_limit_events"])) if current else 0
            )
            success_streak = (
                max(0, int(current["success_streak"])) if current else 0
            )
            if normalized_kind == "rate_limit":
                rate_limit_events += 1
                success_streak = 0
            elif normalized_kind == "recovery":
                success_streak = 0
            elif normalized_kind == "completed":
                success_streak += 1
                if success_streak >= 2 and preferred < target:
                    from sdm.adaptive_connections import raise_connection_count

                    preferred = raise_connection_count(preferred, target)
                    success_streak = 0
            connection.execute(
                """
                INSERT INTO server_profiles (
                    server_key, preferred_connections, rate_limit_events,
                    success_streak, last_status, cooldown_until, updated_at
                ) VALUES (?, ?, ?, ?, ?, '', ?)
                ON CONFLICT(server_key) DO UPDATE SET
                    preferred_connections = excluded.preferred_connections,
                    rate_limit_events = excluded.rate_limit_events,
                    success_streak = excluded.success_streak,
                    last_status = excluded.last_status,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    preferred,
                    rate_limit_events,
                    success_streak,
                    normalized_kind,
                    timestamp,
                ),
            )
        self.update(
            record_id,
            adaptive_connections=record_effective,
            adaptive_reason=str(reason).strip()[:1000],
            transfer_mode=f"Adaptive {record_effective}/{target}",
        )

    def find_completed_by_content_sha256(
        self,
        content_sha256: str,
        *,
        exclude_id: str = "",
    ) -> DownloadRecord | None:
        normalized = normalize_sha256(content_sha256)
        if not normalized:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM downloads
                WHERE content_sha256 = ?
                  AND status = ?
                  AND id != ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (normalized, DownloadStatus.COMPLETED.value, exclude_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def recover_interrupted_downloads(self) -> None:
        timestamp = utc_now()
        active_states = (
            DownloadStatus.DOWNLOADING.value,
            DownloadStatus.RETRYING.value,
            DownloadStatus.VERIFYING.value,
        )
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE downloads
                SET status = ?, updated_at = ?
                WHERE status IN (?, ?, ?)
                """,
                (
                    DownloadStatus.PAUSED.value,
                    timestamp,
                    active_states[0],
                    active_states[1],
                    active_states[2],
                ),
            )


    def record_network_event(self, download_id: str, event_type: str, message: str = "") -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO network_events(download_id, event_type, message, created_at) VALUES (?, ?, ?, ?)",
                (download_id, event_type, message, utc_now()),
            )

    def list_network_events(self, download_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
        query = "SELECT download_id, event_type, message, created_at FROM network_events"
        params: list[Any] = []
        if download_id:
            query += " WHERE download_id = ?"
            params.append(download_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DownloadRecord:
        try:
            status = DownloadStatus(row["status"])
        except ValueError:
            status = DownloadStatus.FAILED
        return DownloadRecord(
            id=row["id"],
            url=row["url"],
            filename=row["filename"],
            folder=row["folder"],
            total_bytes=int(row["total_bytes"]),
            downloaded_bytes=int(row["downloaded_bytes"]),
            status=status,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            etag=row["etag"],
            last_modified=row["last_modified"],
            connections=max(1, min(16, int(row["connections"]))),
            adaptive_connections=max(
                1,
                min(16, int(row["adaptive_connections"])),
            ),
            adaptive_reason=str(row["adaptive_reason"] or ""),
            transfer_mode=row["transfer_mode"],
            source=row["source"],
            auto_start=bool(row["auto_start"]),
            category=row["category"],
            scheduled_at=row["scheduled_at"],
            checksum_sha256=row["checksum_sha256"],
            checksum_actual=row["checksum_actual"],
            checksum_status=row["checksum_status"],
            description=row["description"],
            capture_pending=bool(row["capture_pending"]),
            media_kind=normalize_media_kind(row["media_kind"]),
            mime_type=str(row["mime_type"] or ""),
            referer=str(row["referer"] or ""),
            source_url=str(row["source_url"] or ""),
            site_adapter=str(row["site_adapter"] or "direct"),
            adapter_status=str(row["adapter_status"] or ""),
            resolved_at=str(row["resolved_at"] or ""),
            identity_key=str(row["identity_key"] or ""),
            rule_id=str(row["rule_id"] or ""),
            rule_reason=str(row["rule_reason"] or ""),
            content_sha256=str(row["content_sha256"] or ""),
            content_fingerprint_status=str(
                row["content_fingerprint_status"] or "Pending"
            ),
            duplicate_of_id=str(row["duplicate_of_id"] or ""),
            media_format=str(row["media_format"] or ""),
        )


def normalize_media_kind(value: object) -> str:
    candidate = str(value or "direct").strip().casefold()
    return candidate if candidate in {"direct", "video", "audio", "auto"} else "direct"
