from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "SDM - Smart Download Manager"
APP_VERSION = "2.0.0"
DEFAULT_CONNECTIONS_PER_DOWNLOAD = 4
DEFAULT_MAX_ACTIVE_DOWNLOADS = 2
USER_AGENT = f"SDM/{APP_VERSION} (Windows; Smart Download Manager)"
NATIVE_HOST_NAME = "com.zpd8x.sdm"


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    heartbeat: Path
    show_manager_request: Path
    plugins: Path


def app_data_root() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "SDM"
        return Path.home() / "AppData" / "Local" / "SDM"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "sdm"
    return Path.home() / ".local" / "share" / "sdm"


def ensure_app_directories() -> AppPaths:
    root = app_data_root()
    logs = root / "logs"
    root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return AppPaths(
        root=root,
        database=root / "downloads.db",
        logs=logs,
        heartbeat=root / "app.heartbeat",
        show_manager_request=root / "show_manager.request",
        plugins=root / "plugins",
    )


def default_download_folder() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.exists() else Path.home()
