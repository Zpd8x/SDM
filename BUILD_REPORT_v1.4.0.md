# SDM v1.4.0 Build Report

## Media Detection & Stream Inspector

- Added non-downloading media inspection through yt-dlp.
- Added stream table: format ID, media kind, resolution, FPS, container, codecs, bitrate, estimated size, protocol, HDR metadata and language.
- Added live-stream, playlist, subtitle and DRM/protection detection.
- Added user-selectable format persistence in SQLite through `media_format`.
- Added automatic migration from v1.3.0 databases.
- Added Media Inspector window and direct handoff to the SDM queue.
- Preserved automatic best-video/best-audio behavior when no format is selected.

## Validation

- 180 Python unit tests passed.
- Python compileall passed.
- Browser extension JavaScript syntax passed.
- Legacy database migration passed.

Known note: pre-existing SQLite ResourceWarning messages may appear in concurrent browser bridge tests; they do not cause test failures.
