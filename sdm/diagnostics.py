from __future__ import annotations

import json
import platform
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from sdm.config import APP_VERSION


@dataclass(slots=True)
class DiagnosticItem:
    name: str
    status: str
    details: str = ""


class DiagnosticsService:
    def __init__(self, database_path: str | Path, root: str | Path):
        self.database_path = Path(database_path)
        self.root = Path(root)

    def collect(self) -> list[DiagnosticItem]:
        items = [
            DiagnosticItem("SDM version", "OK", APP_VERSION),
            DiagnosticItem("Python", "OK", platform.python_version()),
            DiagnosticItem("Operating system", "OK", platform.platform()),
        ]
        items.append(self._check_database())
        for tool in ("yt-dlp", "ffmpeg", "ffprobe", "ffplay"):
            items.append(self._check_tool(tool))
        items.append(self._check_browser_extension())
        items.append(self._check_native_host())
        return items

    def _check_database(self) -> DiagnosticItem:
        if not self.database_path.exists():
            return DiagnosticItem("Database", "NEW", str(self.database_path))
        try:
            with closing(sqlite3.connect(self.database_path, timeout=5)) as connection, connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
                count = connection.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
            status = "OK" if result and result[0] == "ok" else "ERROR"
            return DiagnosticItem("Database", status, f"{count} downloads; quick_check={result[0] if result else 'unknown'}")
        except (sqlite3.Error, OSError) as exc:
            return DiagnosticItem("Database", "ERROR", str(exc))

    def _check_tool(self, name: str) -> DiagnosticItem:
        candidate = shutil.which(name)
        if not candidate:
            local = self.root / "Tools" / (name + (".exe" if sys.platform == "win32" else ""))
            candidate = str(local) if local.exists() else ""
        if not candidate:
            return DiagnosticItem(name, "MISSING", "Not found in PATH or Tools")
        try:
            completed = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=5, check=False)
            first = (completed.stdout or completed.stderr).splitlines()[0][:180]
            return DiagnosticItem(name, "OK" if completed.returncode == 0 else "WARNING", first)
        except (OSError, subprocess.SubprocessError) as exc:
            return DiagnosticItem(name, "ERROR", str(exc))

    def _check_browser_extension(self) -> DiagnosticItem:
        manifest = self.root / "browser_extension" / "manifest.json"
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            return DiagnosticItem("Browser extension", "OK", f"v{payload.get('version', 'unknown')} Manifest V{payload.get('manifest_version', '?')}")
        except (OSError, ValueError) as exc:
            return DiagnosticItem("Browser extension", "ERROR", str(exc))

    def _check_native_host(self) -> DiagnosticItem:
        host = self.root / "browser_host" / "native_host.py"
        return DiagnosticItem("Native host", "OK" if host.exists() else "MISSING", str(host))

    def export(self, destination: str | Path) -> Path:
        destination = Path(destination)
        payload: dict[str, Any] = {
            "sdm_version": APP_VERSION,
            "items": [asdict(item) for item in self.collect()],
        }
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return destination
