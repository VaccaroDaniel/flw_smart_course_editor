# S1 Test Report

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## Commands run

Python compile:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m py_compile server.py moodle_import_support.py scorm_gui_support.py scripts\smoke_test.py scripts\pilot_export_scorm.py scripts\verify_scorm_display_consistency.py
```

Smoke test:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe scripts\smoke_test.py
```

Additional syntax checks are recorded in `S1_REPORT.md`.

Node syntax:

```text
node --check static\app.js
```

PHP syntax:

```text
php -l scripts\import_scorm_pilot_to_moodle.php
```

JSON syntax:

```text
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m json.tool flw_moodle_course_map.json
C:\Users\com\AppData\Local\Programs\Python\Python311\python.exe -m json.tool docs\moodle-export-v2\S1_MANIFEST.json
```

## Smoke results

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
  "copyFolder": "PASS",
  "copyZip": "PASS",
  "visualRuntimeJs": "PASS",
  "frontendJs": "PASS",
  "directFlwUi": "PASS"
}
```

## Required S1 cases covered

| Case | Result |
|---|---|
| REW U001 → REW / A1 / `FLW_REW_A1` | PASS |
| REW U023 → REW / A2 / `FLW_REW_A2` | PASS |
| REW U061 → REW / B2 / `FLW_REW_B2` | PASS |
| REW U085 → REW / C1 / `FLW_REW_C1` | PASS |
| sourceStage `A2.2` + canonical A2 unit | PASS |
| metadata says A1 but canonical map says A2 | PASS, `STAGE_CONFLICT` |
| no valid stage source | PASS, `STAGE_UNRESOLVED` |
| Spanish root discovery when present | PASS |
| all configured available source worlds represented | PASS |
| invalid config/schema | PASS, `INVALID_CONFIG` |
| existing editor smoke suite | PASS |
| Node syntax | PASS |
| PHP syntax | PASS |
| Course-map JSON syntax | PASS |
| S1 manifest JSON syntax | PASS |
