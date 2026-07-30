# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH).resolve().parents[1]

hiddenimports = [
    "yt_dlp",
    "yt_dlp.extractor",
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
]

datas = [
    (str(project_root / "browser_extension"), "browser_extension"),
    (str(project_root / "plugins"), "plugins"),
    (str(project_root / "VERSION"), "."),
    (str(project_root / "README.md"), "."),
    (str(project_root / "CHANGELOG.md"), "."),
    (str(project_root / "BROWSER_SETUP_AR.md"), "."),
    (str(project_root / "Tools"), "Tools"),
]

icon_path = project_root / "browser_extension" / "icons" / "icon.ico"
icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SDM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=str(project_root / "packaging" / "windows" / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SDM",
)
