from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon


@lru_cache(maxsize=1)
def application_icon() -> QIcon:
    """Return the shared SDM icon used by the app and its dialogs."""
    project_root = Path(__file__).resolve().parents[2]
    icon_directory = project_root / "browser_extension" / "icons"
    for filename in ("icon128.png", "icon48.png", "icon32.png", "icon16.png"):
        candidate = icon_directory / filename
        if candidate.is_file():
            return QIcon(str(candidate))
    return QIcon()
