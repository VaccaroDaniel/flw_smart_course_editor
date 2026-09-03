# S7 Test Report

Gate: S7 — Batch import verification  
Created: 2026-08-24

## Syntax and regression checks

| Check | Result |
|---|---|
| `python -m py_compile server.py scripts\smoke_test.py` | PASS |
| `node --check static\app.js` | PASS |
| `php -l scripts\import_scorm_pilot_to_moodle.php` | PASS |
| PHP lint sweep over `scripts/*.php` | PASS |
| `python scripts\smoke_test.py` | PASS |

Smoke coverage includes:

```text
batchFlwPlanning
s1DeploymentMetadata
s3StageCourseResolver
s4UnitSectionResolver
s2bNavigatorRuntimeJs
s2ScormIdentity
directFlwUi
```

## Direct language range dry-run

Source:

```text
D:\WinPro.Delta\Projects\SmartCourses\02-Real
U019-U036
```

Result:

```text
items: 18
Stage groups: 1
group: REW:A2 -> FLW_REW_A2
SCORM create/update: 17 / 1
failed: 0
publicStatus: SUCCESS
```

Artifact:

```text
verification_exports/s7_batch_tests/flw_batch_20260824_084138_800742/batch_flw_import_report.json
```

## Real Moodle batch overwrite

First real run:

```text
items: 18
17 succeeded
1 failed: REW-U023 SCORM_UPDATE_FAILED
message: Cannot create local file pool file. Please verify permissions in dataroot and available disk space.
```

This proved failure isolation: the failing Unit did not stop the other 17 Units.

Retry:

```text
17 UNCHANGED
1 UPDATE_SCORM
failed: 0
publicStatus: SUCCESS
```

Exact repeat:

```text
18 UNCHANGED
failed: 0
publicStatus: UNCHANGED
```

Artifacts:

```text
verification_exports/s7_batch_tests/flw_batch_20260824_084214_054078/batch_flw_import_report.json
verification_exports/s7_batch_tests/flw_batch_20260824_084337_003044/batch_flw_import_report.json
verification_exports/s7_batch_tests/flw_batch_20260824_084409_590908/batch_flw_import_report.json
```

## Mixed-stage dry-run

Source:

```text
D:\WinPro.Delta\Projects\SmartCourses\02-Real
U017-U020
```

Result:

```text
Stage groups: 2
REW:A1 -> FLW_REW_A1 -> U017, U018
REW:A2 -> FLW_REW_A2 -> U019, U020
publicStatus: SUCCESS
```

Artifact:

```text
verification_exports/s7_batch_tests/flw_batch_20260824_084453_485001/batch_flw_import_report.json
```

## Add New Unit collision

Source:

```text
D:\WinPro.Delta\Projects\SmartCourses\02-Real
U019-U020
mode: Add New Unit
dry-run: true
```

Result:

```text
UNIT_ALREADY_EXISTS: 2
unitsConflict: 2
publicStatus: CONFLICT
```

Artifact:

```text
verification_exports/s7_batch_tests/flw_batch_20260824_084940_326468/batch_flw_import_report.json
```

## Full-catalog preview

Result:

```text
selected Units: 601
Stage groups: 26
blocked Units: 256
SCORM_DIFF_REQUIRES_PACKAGE rows: 601
```

Artifact:

```text
verification_exports/s7_full_catalog_preview/flw_preview_20260824_085934_597835/batch_course_preview_report.json
```

## Full package-aware catalog dry-run

Result:

```text
exported packages: 601
elapsed: 1714.98 seconds
artifact size: about 18.1 GB
blocked Units: 256
manual content preserved: 345
attempts preserved: 345
```

Artifacts:

```text
D:\WinPro.Delta\Projects\SmartCourses\_s7_full_catalog_dryrun_exports\flw_batch_20260824_090103_754253\batch_manifest.json
D:\WinPro.Delta\Projects\SmartCourses\_s7_full_catalog_dryrun_exports\flw_batch_20260824_090103_754253\batch_flw_import_report.json
```

## Cancel/resume

Result:

```text
jobId: 20260824_094841_8b571ede
cancel honored before Moodle mutation
resume completed
reused exported packages: 2
publicStatus: UNCHANGED
```

Artifact:

```text
verification_exports/s7_cancel_resume_job/flw_batch_job_20260824_094841_8b571ede/batch_flw_import_report.json
```

## S2B regression

S7 did not alter the SCORM learner navigation/player runtime. Existing S2B browser verification remains PASS, and current smoke still passes `s2bNavigatorRuntimeJs`.

