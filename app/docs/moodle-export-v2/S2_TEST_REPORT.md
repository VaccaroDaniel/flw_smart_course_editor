# S2 Test Report

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## Pre-S2 baseline

Command:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe scripts\smoke_test.py
```

Result:

```text
PASS
```

## Final commands

Python compile:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m py_compile server.py moodle_import_support.py scorm_gui_support.py scripts\smoke_test.py scripts\pilot_export_scorm.py scripts\verify_scorm_display_consistency.py
```

Smoke:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe scripts\smoke_test.py
```

Node:

```text
node --check static\app.js
```

PHP:

```text
php -l scripts\import_scorm_pilot_to_moodle.php
```

JSON:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m json.tool flw_moodle_course_map.json
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m json.tool docs\moodle-export-v2\S1_MANIFEST.json
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m json.tool docs\moodle-export-v2\S2_MANIFEST.json
```

## S2 cases

| Case | Result |
|---|---|
| Deterministic rebuild keeps same package identifier, activity key, SCO IDs, component map | PASS |
| Title change keeps same component/SCO IDs | PASS |
| Lesson reorder keeps same identities and changes display order only | PASS |
| Micro-activity add/reorder keeps parent lesson as one SCO | PASS |
| Watch component uses stable identity | PASS |
| Project component gets one stable SCO when detected | PASS |
| Result/checkpoint component uses stable identity | PASS |
| Giant-SCO prevention for normal 7-lesson unit | PASS |
| SCO explosion prevention for lesson with 20 practice items | PASS |
| Content change keeps stable identity and changes package content hash | PASS |
| Existing editor smoke suite | PASS |

## Smoke output

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
  "s1DeploymentMetadata": "PASS",
  "s2ScormIdentity": "PASS",
  "copyFolder": "PASS",
  "copyZip": "PASS",
  "visualRuntimeJs": "PASS",
  "frontendJs": "PASS",
  "directFlwUi": "PASS"
}
```
