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

    def _tool_roots(self) -> list[Path]:
        roots: list[Path] = []

        def add(path: Path) -> None:
            try:
                resolved = path.expanduser().resolve()
            except OSError:
                resolved = path.expanduser()
            if resolved not in roots:
                roots.append(resolved)

        add(self.root)
        add(Path.cwd())
        add(Path(sys.executable).resolve().parent)
        add(Path(__file__).resolve().parents[1])
        if getattr(sys, "_MEIPASS", None):
            add(Path(sys._MEIPASS))

        for root in list(roots):
            for parent in root.parents:
                add(parent)
                if len(roots) >= 20:
                    break
        return roots

    def _check_tool(self, name: str) -> DiagnosticItem:
        executable = name + (".exe" if sys.platform == "win32" else "")
        candidates: list[Path] = []

        for lookup in (name, executable):
            from_path = shutil.which(lookup)
            if from_path:
                candidates.append(Path(from_path))

        searched: list[Path] = []
        for root in self._tool_roots():
            for folder_name in ("Tools", "tools"):
                tools_root = root / folder_name
                if tools_root in searched:
                    continue
                searched.append(tools_root)
                candidates.extend([
                    tools_root / executable,
                    tools_root / name / executable,
                    tools_root / "bin" / executable,
                    tools_root / "ffmpeg" / "bin" / executable,
                ])
                if tools_root.is_dir():
                    try:
                        candidates.extend(tools_root.rglob(executable))
                    except OSError:
                        pass

        candidate = next((path for path in candidates if path.is_file()), None)
        if candidate is None:
            locations = "; ".join(str(path) for path in searched[:4])
            return DiagnosticItem(
                name,
                "MISSING",
                f"Executable not found. Checked PATH and: {locations}",
            )
        try:
            completed = subprocess.run(
                [str(candidate), "-version" if name.startswith("ff") else "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            lines = (completed.stdout or completed.stderr).splitlines()
            first = (lines[0] if lines else candidate.name)[:140]
            status = "OK" if completed.returncode == 0 else "WARNING"
            return DiagnosticItem(name, status, f"{first} | {candidate}")
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
