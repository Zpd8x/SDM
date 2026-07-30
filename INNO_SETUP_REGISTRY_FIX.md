# Inno Setup Registry Quote Fix

Fixed the Windows installer compilation error on the `[Registry]` entry for SDM startup capture mode.

## Root cause

Inno Setup does not use C-style `\"` escaping inside parameter strings. A literal quotation mark must be represented by two quotation marks.

## Correct value

```iss
ValueData: """{app}\SDM.exe"" --capture-only"
```

## Build failure handling

The fatal build path now uses `exit 1`, which terminates the child `cmd.exe` process instead of returning to the next command and showing a second, misleading failure dialog.

## Validation

- 196 automated tests passed.
- Python compile check passed.
