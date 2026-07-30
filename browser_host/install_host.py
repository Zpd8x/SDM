from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


HOST_NAME = "com.zpd8x.sdm"
REGISTRY_KEYS = (
    rf"HKCU\Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}",
    rf"HKCU\Software\Microsoft\Edge\NativeMessagingHosts\{HOST_NAME}",
)


def extension_id_from_key(public_key: str) -> str:
    digest = hashlib.sha256(base64.b64decode(public_key)).digest()[:16]
    alphabet = "abcdefghijklmnop"
    return "".join(
        alphabet[nibble]
        for byte in digest
        for nibble in (byte >> 4, byte & 0x0F)
    )


def build_host_manifest(executable: Path, extension_id: str) -> dict[str, Any]:
    return {
        "name": HOST_NAME,
        "description": "SDM browser integration host",
        "path": str(executable.resolve()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def install_packaged_host(
    source_executable: Path,
    extension_manifest_path: Path,
    application_directory: Path,
) -> int:
    if os.name != "nt":
        print("[ERROR] Browser integration installation requires Windows.")
        return 1
    if not source_executable.is_file():
        print(f"[ERROR] Native host executable was not found: {source_executable}")
        return 1
    if not extension_manifest_path.is_file():
        print("[ERROR] Browser extension manifest was not found.")
        return 1

    extension_manifest = json.loads(
        extension_manifest_path.read_text(encoding="utf-8")
    )
    extension_id = extension_id_from_key(str(extension_manifest["key"]))

    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    app_root = local_app_data / "SDM"
    install_directory = app_root / "NativeHost"
    install_directory.mkdir(parents=True, exist_ok=True)

    installed_executable = install_directory / "SDMNativeHost.exe"
    shutil.copy2(source_executable, installed_executable)

    config = {
        "database_path": str(app_root / "downloads.db"),
        "heartbeat_path": str(app_root / "app.heartbeat"),
        "application_executable": str(application_directory / "SDM.exe"),
        "working_directory": str(application_directory),
    }
    (install_directory / "native_host_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    native_manifest_path = install_directory / f"{HOST_NAME}.json"
    native_manifest_path.write_text(
        json.dumps(
            build_host_manifest(installed_executable, extension_id),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    for registry_key in REGISTRY_KEYS:
        subprocess.run(
            [
                "reg", "add", registry_key, "/ve", "/t", "REG_SZ",
                "/d", str(native_manifest_path.resolve()), "/f",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    print("[SUCCESS] SDM Native Messaging host installed.")
    print(f"[INFO] Extension ID: {extension_id}")
    print(f"[INFO] Extension folder: {application_directory / 'browser_extension'}")
    return 0


def uninstall_packaged_host() -> int:
    if os.name != "nt":
        print("[ERROR] Browser integration removal requires Windows.")
        return 1
    for registry_key in REGISTRY_KEYS:
        subprocess.run(
            ["reg", "delete", registry_key, "/f"],
            check=False,
            capture_output=True,
            text=True,
        )
    install_directory = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SDM" / "NativeHost"
    if install_directory.exists():
        shutil.rmtree(install_directory)
    print("[SUCCESS] SDM Native Messaging host removed.")
    return 0


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    source_executable = project_root / "browser_host" / "dist" / "SDMNativeHost.exe"
    return install_packaged_host(
        source_executable,
        project_root / "browser_extension" / "manifest.json",
        project_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
