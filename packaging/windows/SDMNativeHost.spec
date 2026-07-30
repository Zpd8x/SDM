# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
project_root = Path(SPECPATH).resolve().parents[1]

a = Analysis(
    [str(project_root / "browser_host" / "native_host.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=["sdm.browser_bridge", "sdm.database", "sdm.models"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "tkinter"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SDMNativeHost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
