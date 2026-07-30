# SDM v2.0.0 Final — Windows Release

SDM 2.0.0 is the final feature release of Smart Download Manager. It combines segmented downloads, pause/resume, adaptive connections, Smart Rules, duplicate intelligence, network recovery, Media Inspector, browser capture, Plugin API v1, and System Center diagnostics.

## Windows packages

- `SDM_v2.0.0_Setup_x64.exe`: recommended installer for Windows 10/11 x64.
- `SDM_v2.0.0_Portable_x64.zip`: portable application, no installation required.
- `SDM_Browser_Extension_v2.0.0.zip`: unpacked Chromium extension package.
- `SHA256SUMS.txt`: SHA-256 checksums for release verification.

## Upgrade notes

Existing user data remains in `%LOCALAPPDATA%\SDM`. Installing v2.0.0 does not remove download history, settings, fingerprints, rules, or recovery metadata.

## Browser support

The packaged browser integration targets Google Chrome and Microsoft Edge. Brave and Opera can load the Chromium extension manually, but native host registry integration may require additional browser-specific registration.
