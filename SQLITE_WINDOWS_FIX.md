# SDM v2.0.0 — Windows SQLite Fix

## Problem

Windows builds running Python 3.14 failed three tests with `WinError 32` because
`with sqlite3.connect(...)` commits or rolls back the transaction but does not
close the SQLite connection object.

Affected paths:

- `sdm/diagnostics.py`
- `tests/test_database.py`
- `tests/test_browser_bridge.py`
- `tests/test_diagnostics.py`

## Fix

SQLite calls that create temporary or diagnostic databases now use:

```python
with closing(sqlite3.connect(path)) as connection, connection:
    ...
```

This guarantees that the connection is closed before Windows attempts to remove
the temporary database file.

## Validation

- Python compileall: PASS
- Unit tests: 190/190 PASS
- Errors: 0
- Failures: 0
