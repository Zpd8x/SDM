# SDM v1.2.0 Build Report

## Feature
Smart Download Rules Engine

## Validation
- 168 Python tests: PASS
- Python compileall: PASS
- Browser JavaScript syntax: PASS
- Backward-compatible Smart Rules JSON: PASS
- Filename sanitization tests: PASS
- Filename glob and URL token matching: PASS
- Automatic subfolder and rename actions: PASS

## Main changes
- Extended `SmartRule` matching and action model.
- Extended Smart Rules editor UI.
- Applied rule-based filename changes before duplicate detection.
- Preserved first-match rule ordering and all v1.1.0 defaults.
