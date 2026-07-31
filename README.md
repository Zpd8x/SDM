# SDM 3.2.0 — Smart Download Manager

SDM is a Windows desktop download manager focused on fast, reliable and understandable downloads. It combines segmented transfers, adaptive connections, recovery, media analysis, duplicate detection, browser capture and a compact dark-green workspace.

## Highlights

- Adaptive segmented downloads with pause, resume, cancel and recovery.
- Smart link analysis, strategy selection and download health scoring.
- Media Inspector with General, Connections, Chunks, Headers and More views.
- Activity Center for download, browser, error and system events.
- Browser integration for Chrome and Edge through Native Messaging.
- Duplicate intelligence, SHA-256 verification, smart rules and sessions.
- Performance event buffering for smoother updates during parallel downloads.

## Run from source

1. Install Python 3.10 or newer.
2. Run `START_SDM.bat`.
3. The launcher creates `.venv` once and installs only missing requirements.

After the first successful setup, SDM can start offline when its requirements are already installed.

## Build the Windows release

Run:

```bat
packaging\windows\build_release.bat
```

The Windows build computer needs Python 3, Inno Setup 6 and Internet access for build dependencies. The script creates the Setup EXE, Portable ZIP, browser-extension ZIP and SHA-256 checksums in `release`.

## Browser integration

Run `INSTALL_BROWSER_INTEGRATION.bat`, then load the `browser_extension` directory as an unpacked extension when developing from source. Installed builds can register the native host through the installer.

## User data

SDM stores its database and persistent settings under `%LOCALAPPDATA%\SDM`. Installing or extracting a newer program build does not require deleting this folder.

## Release

Version: `3.2.0`  
Channel: Stable  
Platform: Windows x64
