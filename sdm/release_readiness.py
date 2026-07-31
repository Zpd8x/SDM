from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import compileall
import json
import shutil

from sdm.config import APP_VERSION


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    status: str
    detail: str
    required: bool = True

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


REQUIRED_FILES = (
    "main.py",
    "VERSION",
    "README.md",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
    "requirements.txt",
    "LICENSE.txt",
)


def _version_check(root: Path) -> ReleaseCheck:
    version_file = root / "VERSION"
    try:
        disk_version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return ReleaseCheck("Version sync", "FAIL", str(exc))
    if disk_version != APP_VERSION:
        return ReleaseCheck(
            "Version sync",
            "FAIL",
            f"VERSION={disk_version!r}, APP_VERSION={APP_VERSION!r}",
        )
    return ReleaseCheck("Version sync", "PASS", APP_VERSION)


def _required_files_check(root: Path) -> ReleaseCheck:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        return ReleaseCheck("Required release files", "FAIL", ", ".join(missing))
    return ReleaseCheck("Required release files", "PASS", f"{len(REQUIRED_FILES)} files present")


def _compile_check(root: Path) -> ReleaseCheck:
    targets = [root / "main.py", root / "sdm", root / "browser_host"]
    ok = True
    for target in targets:
        if target.is_dir():
            ok = compileall.compile_dir(str(target), quiet=1, force=True) and ok
        elif target.is_file():
            ok = compileall.compile_file(str(target), quiet=1, force=True) and ok
    return ReleaseCheck(
        "Python compilation",
        "PASS" if ok else "FAIL",
        "main.py, sdm, browser_host",
    )


def _tool_check(name: str) -> ReleaseCheck:
    located = shutil.which(name)
    return ReleaseCheck(
        f"Optional tool: {name}",
        "PASS" if located else "WARN",
        located or "Not found in PATH or bundled Tools directory",
        required=False,
    )


def run_release_checks(root: Path) -> list[ReleaseCheck]:
    root = root.resolve()
    checks = [
        _required_files_check(root),
        _version_check(root),
        _compile_check(root),
    ]
    checks.extend(_tool_check(name) for name in ("ffmpeg", "ffprobe", "ffplay", "yt-dlp"))
    return checks


def release_check_exit_code(checks: list[ReleaseCheck]) -> int:
    return 0 if all(check.passed for check in checks if check.required) else 1


def format_release_report(checks: list[ReleaseCheck]) -> str:
    lines = [f"SDM {APP_VERSION} Release Readiness", "=" * 52]
    for check in checks:
        lines.append(f"[{check.status:4}] {check.name}: {check.detail}")
    required_passed = sum(1 for check in checks if check.required and check.passed)
    required_total = sum(1 for check in checks if check.required)
    warnings = sum(1 for check in checks if check.status == "WARN")
    lines.extend(
        [
            "-" * 52,
            f"Required checks: {required_passed}/{required_total}",
            f"Warnings: {warnings}",
            "READY" if release_check_exit_code(checks) == 0 else "NOT READY",
        ]
    )
    return "\n".join(lines)


def write_release_report(root: Path, checks: list[ReleaseCheck]) -> Path:
    report_path = root / "release_readiness.json"
    payload = {
        "version": APP_VERSION,
        "ready": release_check_exit_code(checks) == 0,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
                "required": check.required,
            }
            for check in checks
        ],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path
