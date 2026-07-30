# SDM v2.0.0 Final Build Report

## Release scope

SDM v2.0.0 consolidates the v1.x engines into a stable final architecture and adds a fault-isolated local plugin API plus the System Center diagnostics interface.

## New architecture

- Plugin API v1 with manifest validation, enable/disable persistence and startup isolation.
- System Center with database integrity, Python, OS, yt-dlp, FFmpeg tools, extension and Native Host checks.
- JSON diagnostic report export.
- Final UI identity and v2.0.0 browser-extension protocol packaging.
- Browser Bridge SQLite connections are explicitly closed after transaction completion.

## Validation

- 190 Python tests passed.
- Python compileall passed.
- Browser JavaScript syntax passed.
- Browser manifest JSON passed.
- ZIP integrity passed.
- Upgrade path from v1.5.0 uses the existing database without destructive migration.

## Known note

Four ResourceWarning messages can appear under Python 3.13 from legacy test helper connections. Production repository and Browser Bridge connection paths close their connections explicitly.
