from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, BinaryIO


if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdm.browser_bridge import (
    acquire_launch_guard,
    handle_native_message,
    is_application_running,
    release_launch_guard,
)
from sdm.config import APP_VERSION, app_data_root
from sdm.remote_metadata import enrich_download_payload


MAX_MESSAGE_BYTES = 1024 * 1024


def load_host_config() -> dict[str, str]:
    if getattr(sys, "frozen", False):
        host_directory = Path(sys.executable).resolve().parent
        project_root = host_directory
    else:
        host_directory = Path(__file__).resolve().parent
        project_root = host_directory.parent

    config_path = host_directory / "native_host_config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError, TypeError):
            pass

    data_root = app_data_root()
    return {
        "database_path": str(data_root / "downloads.db"),
        "heartbeat_path": str(data_root / "app.heartbeat"),
        "pythonw_path": str(project_root / ".venv" / "Scripts" / "pythonw.exe"),
        "main_path": str(project_root / "main.py"),
        "working_directory": str(project_root),
    }


def process_message(
    payload: Any,
    config: dict[str, str],
) -> dict[str, Any]:
    database_path = config.get(
        "database_path",
        str(app_data_root() / "downloads.db"),
    )
    has_secure_session = (
        isinstance(payload, dict)
        and isinstance(payload.get("session_auth"), dict)
        and bool(payload["session_auth"].get("enabled"))
    )
    if isinstance(payload, dict):
        original_payload = dict(payload)
        if str(original_payload.get("action", "")).casefold() == "download":
            original_payload.setdefault(
                "source_url",
                str(original_payload.get("url", "")),
            )
        action = str(original_payload.get("action", "")).casefold()
        if action == "batch_download" and isinstance(original_payload.get("items"), list):
            prepared_items = []
            for item in original_payload["items"]:
                if not isinstance(item, dict):
                    prepared_items.append(item)
                    continue
                candidate = dict(item)
                candidate.setdefault("source_url", str(candidate.get("url", "")))
                secure = isinstance(candidate.get("session_auth"), dict) and bool(candidate["session_auth"].get("enabled"))
                prepared_items.append(candidate if secure else enrich_download_payload(candidate))
            prepared_payload = {**original_payload, "items": prepared_items}
        else:
            prepared_payload = (
                original_payload
                if has_secure_session
                else enrich_download_payload(original_payload)
            )
    else:
        prepared_payload = payload
    response = handle_native_message(database_path, prepared_payload)
    response["host_version"] = APP_VERSION
    if isinstance(payload, dict) and payload.get("request_id") is not None:
        response["request_id"] = payload.get("request_id")

    if (
        response.get("ok")
        and isinstance(prepared_payload, dict)
        and str(prepared_payload.get("action", "")).lower() in {"download", "batch_download"}
        and (
            not response.get("duplicate")
            or response.get("capture_pending")
        )
    ):
        heartbeat = config.get(
            "heartbeat_path",
            str(app_data_root() / "app.heartbeat"),
        )
        running = is_application_running(heartbeat)
        response["application_running"] = running
        guard_path = str(Path(heartbeat).with_name("app.launching"))
        if running or not acquire_launch_guard(guard_path):
            response["application_started"] = False
        else:
            started = launch_application(config)
            response["application_started"] = started
            if not started:
                release_launch_guard(guard_path)
    return response


def launch_application(config: dict[str, str]) -> bool:
    if sys.platform != "win32":
        return False

    application_executable = Path(config.get("application_executable", ""))
    pythonw = Path(config.get("pythonw_path", ""))
    main_path = Path(config.get("main_path", ""))
    default_directory = (
        application_executable.parent
        if application_executable.name
        else main_path.parent
    )
    working_directory = Path(
        config.get("working_directory", str(default_directory))
    )

    if application_executable.is_file():
        command = [str(application_executable), "--capture-only"]
    elif pythonw.is_file() and main_path.is_file():
        command = [str(pythonw), str(main_path), "--capture-only"]
    else:
        return False

    creation_flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    try:
        subprocess.Popen(
            command,
            cwd=str(working_directory),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def read_native_message(stream: BinaryIO) -> Any | None:
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("Incomplete native message header.")
    length = struct.unpack("<I", header)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError("Native message exceeds the size limit.")
    body = _read_exact(stream, length)
    return json.loads(body.decode("utf-8"))


def write_native_message(stream: BinaryIO, payload: dict[str, Any]) -> None:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ValueError("Incomplete native message body.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def main() -> int:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    config = load_host_config()
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    while True:
        try:
            message = read_native_message(input_stream)
            if message is None:
                return 0
            response = process_message(message, config)
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        write_native_message(output_stream, response)


if __name__ == "__main__":
    raise SystemExit(main())
