# S8 Test Report

Status: PASS  
Date: 2026-08-24

## Environment

- Repository: `C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui`
- Moodle URL: `https://main.flw.com`
- Moodle config used for real tests: `D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\config.php`
- Disposable fixture run: `S80824151148`
- Disposable fixture directory: `verification_exports/s8_disposable_rebuild`
- Moodle core source: not modified

## Real Moodle S8 tests

| Test | Result | Evidence |
| --- | --- | --- |
| Seed disposable v1 Stage Courses/Unit Sections/SCORMs | PASS | `s8_seed_v1_report.json`: 2 Stage Courses, 5 Units, 5 SCORMs created |
| Mandatory preview before real rebuild | PASS | `s8_preview_required_guard_report.json`: `PREVIEW_REQUIRED`, `BLOCKED` |
| History-bearing rebuild | PASS | U001: `SUPERSEDE_SCORM`, old cmid 2116 hidden, new current cmid 2123 |
| No-history rebuild | PASS | U002: `UPDATE_SCORM`, cmid 2117 preserved |
| Manual content preservation | PASS | U001/U002 manual Pages remained visible after rebuild |
| Learner attempts/tracking preservation | PASS | U001 old cmid retained 15 tracking rows |
| Grade history preservation | PASS | U001 old cmid retained grade 90 |
| Completion preservation | PASS | U001 old cmid retained completion state 1 |
| Current/historical mapping | PASS | S8 map records current cmid 2123 and historical cmid 2116 |
| Duplicate current SCORM conflict | PASS | U003: `SCORM_DUPLICATE`, `BLOCKED_MAPPING_CONFLICT` |
| Wrong-stage conflict | PASS | U004: `UNIT_STAGE_MOVE_REQUIRED`, `BLOCKED_STAGE_CONFLICT` |
| Multi-stage selected scope | PASS | U002 A1 unchanged, U005 A2 rebuilt in place |
| Legacy Unit Course present | PASS | Legacy course detected and reported; canonical rebuild did not modify it |
| Invalid package/failure safety | PASS | U005 current cmid stayed 2120 and remained visible |
| Resume/idempotence | PASS | Rerun of U001/U002 produced `SKIP_UNCHANGED` for both Units |
| S7 overwrite regression | PASS | `s8_s7_overwrite_regression_dry_run_report.json`: 2 Units, `UNCHANGED`, 0 failures |
| Smart Course Editor smoke suite | PASS | all 18 smoke modules PASS |

## Syntax and regression checks

Commands actually run:

- Python compile: `python -m py_compile server.py scripts/*.py`
- Node syntax: `node --check static/app.js`
- PHP lint: `php -l scripts/*.php`
- Smoke: `python scripts/smoke_test.py`

Results:

- Python py_compile: PASS, 6 files
- Node syntax: PASS, 1 file
- PHP lint: PASS, 10 files
- Smoke suite: PASS

## S2B and S7 regression

S2B navigation architecture was not changed in S8. Regression coverage:

- S2B previously PASS on normal trusted Moodle HTTPS URL.
- `s2bNavigatorRuntimeJs` smoke module remains PASS.
- S8 SCORM settings continue to hide/minimize Moodle native SCORM structure and preserve FLW compact navigation settings.

S7 batch architecture was not replaced. Regression coverage:

- S7 prior gate PASS.
- S8 representative overwrite dry-run PASS.
- S8 rebuild uses S7 grouping/background-job semantics.

## Known limitation

No production-only mid-creation failure injection hook was added. Failure recovery was verified by code path inspection plus real invalid-package safety testing. The production code creates/reloads the replacement before retiring the old current SCORM.

