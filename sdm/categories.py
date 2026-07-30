from __future__ import annotations

from pathlib import Path
import re


DOWNLOAD_CATEGORIES = (
    "Documents",
    "Videos",
    "Music",
    "Images",
    "Archives",
    "Programs",
    "Other",
)

_EXTENSIONS = {
    "Documents": {
        ".csv",
        ".doc",
        ".docx",
        ".epub",
        ".md",
        ".odt",
        ".pdf",
        ".ppt",
        ".pptx",
        ".rtf",
        ".txt",
        ".xls",
        ".xlsx",
    },
    "Videos": {
        ".3gp",
        ".avi",
        ".flv",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ts",
        ".webm",
        ".wmv",
    },
    "Music": {
        ".aac",
        ".aiff",
        ".alac",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
    },
    "Images": {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
    },
    "Archives": {
        ".7z",
        ".bz2",
        ".cab",
        ".gz",
        ".iso",
        ".rar",
        ".tar",
        ".tgz",
        ".xz",
        ".zip",
        ".zst",
    },
    "Programs": {
        ".apk",
        ".appx",
        ".bat",
        ".cmd",
        ".deb",
        ".dmg",
        ".exe",
        ".msi",
        ".msix",
        ".pkg",
        ".ps1",
        ".rpm",
    },
}


def categorize_filename(filename: str) -> str:
    suffix = Path(filename).suffix.casefold()
    for category, extensions in _EXTENSIONS.items():
        if suffix in extensions:
            return category
    return "Other"


def normalize_category(category: str, filename: str) -> str:
    value = str(category or "").strip()
    if not value or value.casefold() == "auto":
        return categorize_filename(filename)
    for known in DOWNLOAD_CATEGORIES:
        if value.casefold() == known.casefold():
            return known
    return "Other"


def category_folder_setting_key(category: str) -> str:
    """Return a stable settings key for a category's remembered folder."""
    normalized = normalize_category(category, "")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")
    return f"category_folder_{slug or 'other'}"
