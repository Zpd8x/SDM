# Windows Setup Failure Detection Fix

The Windows release builder now treats a missing or failed Inno Setup build as a hard release failure.

Changes:

- Searches for `ISCC.exe` in PATH and common system/user install locations.
- Stops before packaging when Inno Setup 6 is unavailable.
- Shows a Windows error message box with the failure reason.
- Prints a clear `[FAILED]` section in the console.
- Removes an old Setup EXE before building.
- Verifies that `SDM_v2.0.0_Setup_x64.exe` exists after compilation.
- Shows a success dialog only when the complete release exists.
- Suggests the Winget command:
  `winget install --id JRSoftware.InnoSetup -e`

Validation: 194 tests passed.
