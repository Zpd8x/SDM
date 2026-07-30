# SDM v2.0.0 Windows Release Guide

## Requirements

- Windows 10 or Windows 11 (64-bit)
- Python 3.11–3.13 with the `py` launcher
- Inno Setup 6 to create the installer EXE
- Internet access for the first build dependency installation

## Build

Run:

```bat
packaging\windows\build_release.bat
```

The script performs the test suite, builds `SDM.exe` and `SDMNativeHost.exe`, creates the portable and extension ZIP files, compiles the Inno Setup installer when available, and generates SHA-256 checksums.

## Output

All final files are placed in `release\`.

## Important

Code signing is not included. For public distribution, sign both `SDM.exe` and the setup executable using a trusted Windows code-signing certificate before publishing.
