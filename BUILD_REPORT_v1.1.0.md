# SDM v1.1.0 Build Report

Stage 11 adds Duplicate Manager & Storage Intelligence on top of v1.0.0.

Key guarantees:
- Existing database is migrated in place without deleting history.
- Duplicate decisions use SHA-256 content, not filenames or URLs.
- Missing files are marked; no file is deleted automatically.
- Legacy completed downloads can be scanned in a worker thread.
- Hard-link replacement is limited to the same volume and is atomic through a temporary link.
