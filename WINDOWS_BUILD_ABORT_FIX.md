# Windows Build Abort Fix

Fixed the release builder so fatal errors terminate the entire batch file immediately.

## Root cause

`exit /b 1` was executed inside the `:fatal` subroutine. In a called batch subroutine, that only returns to the caller, so the release process continued and later attempted to execute an empty Inno Setup path (`""`).

## Fix

The fatal handler now jumps to a terminal `:abort_build` label, which ends the whole script with exit code 1.

This prevents Python dependency installation, tests, PyInstaller, and installer compilation from running when Inno Setup is missing.
