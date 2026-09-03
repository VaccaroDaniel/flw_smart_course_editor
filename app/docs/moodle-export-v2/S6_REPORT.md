# S6 Report

Gate: S6 — Single Import Modes + Single-Unit Moodle Export UI  
Created: 2026-08-24

## S6 STATUS

```text
PASS
```

## Summary

S6 wires the single-unit Moodle export workflow to the production architecture:

```text
FLW World + Deployment Stage -> Moodle Stage Course
FLW Unit -> Moodle Unit Section
Unit SCORM -> one current Moodle SCORM activity inside the section
```

The Unit editor was not redesigned. Moodle core was not modified. Batch production behavior was not redesigned in S6.

## Single Overwrite semantics

Overwrite now means:

```text
Synchronize this FLW Unit with its canonical Moodle destination.
```

It is an upsert and never clears the Stage Course.

Verified:

- reused `FLW_REW_A2`;
- reused/updated Unit Section U023;
- updated current Unit SCORM cmid 2097 in-place once;
- repeat export returned `UNCHANGED`;
- teacher page cmid 2096 remained untouched;
- historical superseded SCORM cmids remained untouched.

## Add New semantics

Add New is now displayed as:

```text
Add New Unit
```

It deploys only if the FLW UnitID is unique in the canonical Stage Course.

Verified:

- REW-U001 unique Add New created `FLW_REW_A1`, U001 section, and SCORM cmid 2098.
- REW-U023 Add New collision returned `UNIT_ALREADY_EXISTS` and did not create duplicates.

## Single import pipeline

The single direct pipeline uses:

- S3 Stage Course resolver;
- S4 Unit Section resolver;
- S5 Unit SCORM create/update/unchanged/supersession service.

Frontend code does not resolve Moodle IDs itself.

## Preview UI result

The single UI now includes:

- `Preview Moodle destination`;
- Course → Section → Unit SCORM hierarchy;
- public statuses;
- preview-state hash;
- manual-content and history-safety notes.

## Real import UI result

Real deploy first runs preview/dry-run, then confirms using the preview action summary, then sends the preview hash to the backend.

## Create test

```text
REW-U001 Add New Unit
CREATE_STAGE_COURSE -> CREATE_SECTION -> CREATE_SCORM
course id 203
cmid 2098
PASS
```

## Unchanged test

```text
REW-U023 Overwrite exact repeat
REUSE_STAGE_COURSE -> REUSE_SECTION -> UNCHANGED
cmid 2097 preserved
PASS
```

## Update / supersede test

```text
REW-U023 Overwrite
REUSE_STAGE_COURSE -> UPDATE_SECTION -> UPDATE_SCORM
cmid 2097 preserved
PASS
```

Supersession behavior remains provided by S5 and was not changed in S6.

## Add New unique test

```text
REW-U001
SUCCESS
```

## Add New collision test

```text
REW-U023
UNIT_ALREADY_EXISTS
CONFLICT
No duplicate Section/SCORM
```

## Manual content result

```text
PASS
Teacher page cmid 2096 remained in U023 section 2175.
```

## Legacy course result

No legacy Unit Course conflict was detected in the S6 REW-U023 run. The S3 legacy-course warning path remains in the Stage Course resolver and S6 leaves legacy Unit Courses untouched.

## Destructive old path test

PASS.

Smoke asserts `import_by_language()` does not call:

- `clear_course_for_overwrite`
- `clear_courses_above_id`
- `reset_course_id_sequence`

## Concurrency result

PASS.

Second lock acquisition for `REW:A2:REW-U023` returns:

```text
409 IMPORT_ALREADY_RUNNING
```

## Permission result

PASS.

Guest import attempt returned:

```text
PERMISSION_DENIED
BLOCKED
```

## S2B regression

PASS.

S6 did not change the S2B navigation architecture. Prior S2B browser verification remains PASS and current smoke still passes `s2bNavigatorRuntimeJs`.

## Editor regression

PASS.

Existing Smart Course Editor smoke suite remains PASS.

## Files changed

- `server.py`
- `static/index.html`
- `static/app.js`
- `scripts/import_scorm_pilot_to_moodle.php`
- `scripts/smoke_test.py`
- `flw_moodle_stage_course_map.json`
- `flw_moodle_unit_section_map.json`
- `flw_moodle_unit_scorm_map.json`
- `docs/moodle-export-v2/S6_SINGLE_IMPORT_ARCHITECTURE.md`
- `docs/moodle-export-v2/S6_IMPORT_MODE_SEMANTICS.md`
- `docs/moodle-export-v2/S6_SINGLE_IMPORT_UI.md`
- `docs/moodle-export-v2/S6_DRY_RUN_PREVIEW.md`
- `docs/moodle-export-v2/S6_ERROR_STATUS_CONTRACT.md`
- `docs/moodle-export-v2/S6_TEST_REPORT.md`
- `docs/moodle-export-v2/S6_REPORT.md`
- `docs/moodle-export-v2/S6_MANIFEST.json`

## Tests run

- `python -m py_compile server.py scripts\smoke_test.py`
- `node --check static\app.js`
- `php -l scripts\import_scorm_pilot_to_moodle.php`
- `python scripts\smoke_test.py`
- Real Moodle REW-U023 dry-run preview
- Real Moodle REW-U023 Overwrite
- Real Moodle REW-U023 exact repeat
- Real Moodle REW-U023 Add New collision
- Real Moodle REW-U001 Add New unique create
- Real Moodle stale-preview rejection
- Real Moodle guest permission test
- Manual teacher content snapshot
- Single import concurrency lock probe

## Test results

All S6 checks passed.

## Known limitations

- S6 does not implement S7 or full batch production import changes.
- S6 does not migrate or delete legacy Unit-per-course deployments.
- Supersession remains the S5 policy and was not expanded in S6.

## GO / NO-GO FOR S7

```text
GO
```

S7 was not started.

