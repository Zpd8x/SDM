# SDM v2.1.0 — Product UI/UX Phase 2

## Download Workspace

- Added instant search across filename, URL, category and destination folder.
- Added status filters: Active, Waiting, Completed, Failed and Paused.
- Combined search, category and status filters without changing download logic.
- Added a filtered-result counter in the workspace header.
- Preserved the green square progress bars and existing queue actions.

## Package cleanup

The distributable source package no longer contains:

- automated test sources
- Python bytecode caches
- temporary files
- old build reports and one-time repair notes

Tests were run before cleanup: 199 passed, plus 31 subtests.
