# S0 Baseline Tests

Created: 2026-08-23

Gate: S0 — Current Implementation Freeze

## Runtime versions observed

```text
Python 3.11.9
Node.js v22.22.2
PHP 8.2.4 CLI
```

## Commands run

All commands were run from:

```text
C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui
```

Python compile checks:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m py_compile server.py moodle_import_support.py scorm_gui_support.py scripts\smoke_test.py scripts\pilot_export_scorm.py scripts\verify_scorm_display_consistency.py
```

Result:

```text
PASS
```

Node / JavaScript syntax check:

```text
C:\Program Files\nodejs\node.exe --check static\app.js
```

Result:

```text
PASS
```

PHP syntax check:

```text
php -l scripts\import_scorm_pilot_to_moodle.php
```

Result:

```text
No syntax errors detected in scripts\import_scorm_pilot_to_moodle.php
PASS
```

Existing smoke test:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe scripts\smoke_test.py
```

Result:

```json
{
  "missingRefs": "PASS",
  "importAsset": "PASS",
  "replaceReference": "PASS",
  "restoreBackup": "PASS",
  "scormPreview": "PASS",
  "topNavExportOption": "PASS",
  "directFlwManifest": "PASS",
  "batchFlwPlanning": "PASS",
  "copyFolder": "PASS",
  "copyZip": "PASS",
  "visualRuntimeJs": "PASS",
  "frontendJs": "PASS",
  "directFlwUi": "PASS"
}
```

## Test result summary

| Check | Result |
|---|---|
| Python compile | PASS |
| Node syntax | PASS |
| PHP syntax | PASS |
| Smoke test | PASS |

## Notes

- Running Python compile/smoke tests can create or refresh `__pycache__` files. These are generated artifacts, not production source changes.
- No production source file was intentionally modified during S0.
- S0 documentation files were added under `docs/moodle-export-v2/`.

