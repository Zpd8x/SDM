# SDM v2.0.0 Final

SDM is a Windows Smart Download Manager with segmented downloads, reliable resume, browser capture, media inspection, adaptive connections, recovery, duplicate intelligence and smart rules.

## Final v2 features

- **System Center**: database integrity, tool versions, extension/native-host status and exportable diagnostics.
- **Plugin API v1**: local plugins with manifest validation, enable/disable persistence and crash isolation.
- **Browser Capture 2.0**: persistent Native Messaging, batch queue, context actions and secure session metadata.
- **Media Inspector**: yt-dlp format analysis, audio/video selection, subtitles, HDR, playlists and live detection.
- **Self-healing downloads**: network classification, backoff, resume validation, mirrors and event history.
- **Storage intelligence**: SHA-256 fingerprints, duplicate groups and safe hard-link optimization.

## Start

Run `START_SDM.bat`.

For browser integration, run `INSTALL_BROWSER_INTEGRATION.bat`, then load the `browser_extension` folder as an unpacked extension.

## Upgrade

Use a new program folder. SDM continues to use the existing user database under `%LOCALAPPDATA%\\SDM` and migrates compatible fields automatically.

## Validation

190 Python tests passed for this release.
