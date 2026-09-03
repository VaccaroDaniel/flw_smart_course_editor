# S7 Report

Gate: S7 — Batch import + Course/Unit-Section mapping preview + Progress/Resume/Idempotency  
Created: 2026-08-24

## S7 STATUS

```text
PASS
```

## Summary

S7 implements batch import around the frozen Moodle architecture:

```text
FLW World + Deployment Stage -> Moodle Stage Course
FLW Unit -> Moodle Unit Section
1 FLW Unit -> 1 current multi-SCO SCORM 1.2 activity
```

The Unit editor was not redesigned. Moodle core was not modified. S8 clear/rebuild behavior was not started.

## Implemented

- Batch grouping by World + Deployment Stage.
- Direct language-root selection stays scoped to that language.
- Top SmartCourses root with `All Available Units` enumerates all available configured language Units.
- Batch mapping preview labelled as Moodle Course / Unit-Section preview.
- Package-aware dry-run for SCORM create/update/unchanged decisions.
- Batch Overwrite upsert using S3/S4/S5 target services.
- Batch Add New Unit collision handling with `UNIT_ALREADY_EXISTS`.
- S7 rejection of `Clear and Add`.
- Full catalog validation counts for expected, available, selected, missing, and extra Units.
- Persisted batch progress, cancel, and resume.
- Resume reuse of already-exported packages.
- Real batch import scoped locks.
- Async PHP output spooling to avoid batch job deadlock.

## Real Moodle result

REW-U019 through REW-U036 was imported as one Stage Course group:

```text
REW:A2 -> FLW_REW_A2
18 Unit Sections
1 current Unit SCORM per Unit Section
```

The first real run had one transient Moodle file-pool failure for REW-U023, while 17 neighboring Units succeeded. Retry recovered REW-U023. Exact repeat returned:

```text
18 UNCHANGED
publicStatus: UNCHANGED
```

This verifies failure isolation and idempotency.

## Full catalog result

Full catalog dry-run selected all available source Units:

```text
expectedTotal: 660
availableValidTotal: 601
selectedTotal: 601
missingOrInvalidTotal: 60
extraAvailableTotal: 1
spanishSourcePresent: false
```

The dry-run exported 601 packages and reported:

```text
RESOLVED: 345
STAGE_UNRESOLVED: 256
blockedForRealImport: true
```

This is correct S7 behavior: unresolved Stage mappings are visible blockers, not silent skips.

## Files changed

- `server.py`
- `static/index.html`
- `static/app.js`
- `scripts/import_scorm_pilot_to_moodle.php`
- `scripts/smoke_test.py`
- `flw_moodle_stage_course_map.json`
- `flw_moodle_unit_section_map.json`
- `flw_moodle_unit_scorm_map.json`
- `docs/moodle-export-v2/S7_BATCH_ARCHITECTURE.md`
- `docs/moodle-export-v2/S7_GROUPING_RULES.md`
- `docs/moodle-export-v2/S7_BATCH_PREVIEW.md`
- `docs/moodle-export-v2/S7_PROGRESS_RESUME.md`
- `docs/moodle-export-v2/S7_BATCH_STATUS_CONTRACT.md`
- `docs/moodle-export-v2/S7_FULL_CATALOG_VALIDATION.md`
- `docs/moodle-export-v2/S7_TEST_REPORT.md`
- `docs/moodle-export-v2/S7_REPORT.md`
- `docs/moodle-export-v2/S7_MANIFEST.json`

## Tests run

- `python -m py_compile server.py scripts\smoke_test.py`
- `node --check static\app.js`
- `php -l scripts\import_scorm_pilot_to_moodle.php`
- PHP lint sweep over `scripts/*.php`
- `python scripts\smoke_test.py`
- REW U019-U036 package-aware dry-run
- REW U019-U036 real Overwrite
- REW U019-U036 retry after transient Moodle file-pool failure
- REW U019-U036 exact repeat idempotency check
- REW U017-U020 mixed-stage dry-run
- top SmartCourses U001 multi-world planning
- batch Add New Unit collision dry-run
- full-catalog mapping preview
- full-catalog package-aware dry-run
- async batch cancel/resume job check

## Risks

- Full production all-catalog import is blocked until 256 Units receive resolvable Deployment Stage metadata.
- Spanish is expected by the S7 catalog contract but the actual Spanish source root is not present.
- German has 60 available valid Units against an expected 72.
- Chinese has 133 available valid Units against an expected 132; the extra Unit needs source-owner confirmation.
- Full dry-run artifacts occupy about 18.1 GB.
- The first real REW A2 run exposed a transient Moodle local file-pool write failure; retry succeeded, but Moodle dataroot/disk health should still be watched before massive real imports.

## GO / NO-GO FOR S8

```text
GO
```

S8 was not started. The GO is for implementing the next gate. It is not approval to perform full production all-catalog mutation while the catalog/stage-data blockers remain unresolved.

