# S6 Test Report

Gate: S6 — Single Import Modes + Single-Unit Moodle Export UI  
Created: 2026-08-24

## Syntax and regression checks

| Check | Result |
|---|---|
| `python -m py_compile server.py scripts\smoke_test.py` | PASS |
| `node --check static\app.js` | PASS |
| `php -l scripts\import_scorm_pilot_to_moodle.php` | PASS |
| `python scripts\smoke_test.py` | PASS |

Smoke output included:

```text
s1DeploymentMetadata PASS
s3StageCourseResolver PASS
s4UnitSectionResolver PASS
s2bNavigatorRuntimeJs PASS
s2ScormIdentity PASS
directFlwUi PASS
```

## Real Moodle checks

Moodle URL:

```text
https://main.flw.com
```

### A/B/C — Single Overwrite

REW-U023 preview:

```text
REUSE_STAGE_COURSE -> UPDATE_SECTION -> UPDATE_SCORM
```

Real Overwrite:

```text
PASS
course id 200
section id 2175
current cmid 2097
```

Exact repeat after deterministic content-hash map backfill:

```text
REUSE_STAGE_COURSE -> REUSE_SECTION -> UNCHANGED
```

The S6 fix avoids unnecessary package updates when the exported ZIP byte hash changes but the deterministic package content hash is unchanged.

### D — Add New unique Unit

REW-U001 Add New Unit dry-run:

```text
CREATE_STAGE_COURSE -> CREATE_SECTION -> CREATE_SCORM
```

Real result:

```text
SUCCESS
Stage Course: FLW_REW_A1
course id: 203
Unit Section: U001
SCORM cmid: 2098
```

### E — Add New collision

REW-U023 Add New Unit:

```text
UNIT_ALREADY_EXISTS
CONFLICT
```

No duplicate Unit Section or Unit SCORM was created. The message tells the user to use Copy Unit first.

### I — Preview / actual match and stale preview

Valid preview hash allowed real import.

Invalid preview hash returned:

```text
PREVIEW_STALE
BLOCKED
```

### J — Manual content

Teacher-authored Page remained in REW-U023 section:

```text
cmid 2096
idnumber S5_TEACHER_PAGE_REW_U023
status PASS
```

### L — Destructive path unreachable

Smoke assertions confirm normal single import does not call:

- `clear_course_for_overwrite`
- `clear_courses_above_id`
- `reset_course_id_sequence`

### M — S2B regression

S6 did not change SCORM navigation/player architecture. Existing S2B browser result remains PASS, and `s2bNavigatorRuntimeJs` remains PASS in smoke.

### O — Permission

Guest user test against existing REW-U023:

```text
PERMISSION_DENIED
BLOCKED
```

No SCORM import occurred.

## Verification artifacts

Directory:

```text
verification_exports/s6_single_import_tests
```

Key reports:

- `REW-U023-Real-English-World-Unit-23-Healthy-Choices-SCORM12-20260824_021313.flw_import_report.json`
- `s6_backfill_content_hash_report.json`
- `REW-U023-Real-English-World-Unit-23-Healthy-Choices-SCORM12-20260824_021435.flw_import_report.json`
- `REW-U023-Real-English-World-Unit-23-Healthy-Choices-SCORM12-20260824_021454.flw_import_report.json`
- `REW-U001-Real-English-World-Unit-1-Hello-and-Name-SCORM12-20260824_021527.flw_import_report.json`
- `REW-U023-Real-English-World-Unit-23-Healthy-Choices-SCORM12-20260824_021544.flw_import_report.json`
- `s6_permission_guest_report.json`
- `s6_manual_content_snapshot.json`

