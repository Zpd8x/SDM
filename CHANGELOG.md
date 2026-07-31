# 3.2.0

- Added Universal Media Capture for direct media, HLS, DASH, images and subtitles.
- Added network, DOM, structured metadata and Resource Timing discovery.
- Added smart duplicate filtering and site profiles.
- Added popup media list with multi-select batch download.
- Updated Windows packaging, browser extension and documentation website.
- Added release validation tests for media classification and deduplication.

# Changelog

## 3.1.2 — Media Inspector & Activity Polish

- Added instant Activity Center search across type, source, message, and details.
- Improved activity event readability with icons, severity colors, tooltips, and denser rows.
- Refined Media Inspector hierarchy, selectable filenames, long-value tooltips, and Quick Actions.
- Added semantic status colors and clearer status-bar metrics.
- Preserved the download engine, database, queue, and browser-capture behavior.

## 3.1.1 — UX Polish: Primary Workspace

- Normalized toolbar control geometry, icon sizing, hover/pressed states and disabled states.
- Added concise tooltips and keyboard shortcuts for the primary download workflow.
- Improved search focus behavior and filter-toggle feedback.
- Refined table row density, selection contrast, header alignment and separators.
- Kept progress bars green, thin, rectangular and borderless.
- Preserved the existing download engine, database and browser integration behavior.

## 3.0.0

- Promoted the validated RC3 codebase to the first SDM 3 stable release.
- Finalized the documentation-site visual identity and application logo.
- Preserved the arrow-free toolbar, columns menu and row action controls.
- Added the Windows Stable packaging pipeline for Setup, Portable and browser-extension packages.
- Updated release metadata, user documentation and checksums for the stable channel.
- Kept the RC2 offline-capable Python environment bootstrap and startup fixes.

## 3.0.0-rc3

- Replaced the title-bar mark and shared application icon with the SDM documentation-site brand.
- Removed unwanted menu arrows from toolbar and row-action controls.
- Added final visual-identity polish before stable packaging.

## 3.0.0-rc2 - Windows Runtime Validation

- Reworked `START_SDM.bat` so it does not upgrade pip during normal startup.
- Added Python 3.10+ validation before creating the environment.
- Added dependency checks before any network operation.
- Added 120-second pip timeout, bounded retries, and disabled pip version checks.
- Added recovery choices for retry, offline launch, or exit after setup failure.
- Added a post-failure dependency check so partially completed installs can continue safely.
- Confirmed compatibility with the Python 3.14 startup path after the RC1.1 dataclass fix.

## 3.0.0-rc1.1 — Startup Hotfix

- Fixed `LinkAnalysis` dataclass field ordering that prevented SDM from starting on Python 3.14.
- Verified full Python compilation and direct import of `sdm.intelligent_analysis`.

## 3.0.0-rc1 — Release Candidate 1

- Froze the SDM v3 feature set for stabilization.
- Added `python main.py --release-check`.
- Added required-file, version-sync and full Python compilation checks.
- Added optional FFmpeg, FFprobe, FFplay and yt-dlp availability reporting.
- Added machine-readable `release_readiness.json` output.
- Added release-readiness automated tests and RC1 stabilization policy.

## 2.9.4 — Performance & Stability

- Added a last-value-wins progress event buffer and controlled 12 FPS UI flush.
- Batched concurrent download updates to reduce table repaint pressure.
- Debounced Activity Center refreshes during event bursts.
- Removed full status-summary work from every progress signal.
- Added SQLite memory cache, NORMAL synchronization, and in-memory temp storage.
- Added deterministic performance-buffer tests and fixed progress status handling.

## 2.9.3 — Smart Download Engine Phase 1

- Added server capability detection for byte ranges and resume support.
- Added smart transfer strategy, health score, latency measurement, and retry profile.
- Added strategy explanation and recommended connection count to Add Download.

# SDM 2.8.0 — Modern UI Rebuild Phase 1

- Content-first main window.
- Removed large dashboard metric cards.
- Compact header and toolbar.
- Collapsible filters panel.
- Expanded downloads workspace.
- Live totals moved to the status bar.

# Changelog

## 3.1.2 — Media Inspector & Activity Polish

- Added instant Activity Center search across type, source, message, and details.
- Improved activity event readability with icons, severity colors, tooltips, and denser rows.
- Refined Media Inspector hierarchy, selectable filenames, long-value tooltips, and Quick Actions.
- Added semantic status colors and clearer status-bar metrics.
- Preserved the download engine, database, queue, and browser-capture behavior.

## 2.7.0
- Added live page media counts to the browser extension badge and compact overlay.
- Added a popup Scan page action with separate audio and video totals.
- Added Download Now and Queue actions directly to the media mini panel.
- Improved hidden-audio and network-media capture feedback.
- Updated the browser integration extension to version 2.7.0.

## 2.6.1
- Added Batch Preview for multi-link analysis and selective queue insertion.
- Added duplicate-aware batch preflight.
- Added Smart Queue Optimizer with deterministic priority and size ordering.
- Added safe in-memory pending queue reordering without interrupting active transfers.

## 2.6.0
- Added Smart Link Analyzer, presets and duplicate preflight.

## 2.7.1 — Product UI/UX Polish
- Redesigned the main filter section into a responsive four-column layout.
- Removed narrow fixed-width controls that could overlap on smaller windows.
- Replaced the Tools Manager table with adaptive tool cards.
- Added wrapped/selectable tool paths, clearer status badges, and stable actions.
- Added one-column fallback for compact System Center widths.

## 2.8.3
- Rebuilt the main frame to follow the approved sketch more faithfully.
- Merged branding, system state, utility tools and window controls into one header.
- Removed the duplicated Downloads application header.
- Improved toolbar symbols, spacing, table density and Media Inspector sizing.
- Made the Activity drawer visible by default and hid secondary table columns.
