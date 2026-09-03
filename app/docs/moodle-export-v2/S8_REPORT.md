# S8 Report

S8 STATUS: PASS  
VISIBLE OPERATION NAME: Rebuild Selected FLW Scope  
OLD CLEAR-ADD PATH: DISABLED FROM NORMAL PRODUCTION PATH  
SCOPE MODEL: WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID  
GO / NO-GO FOR S9: GO

Do not start S9 automatically.

## Summary

S8 replaced the old normal Clear/Add behavior with safe scoped rebuild semantics under the user-facing label Rebuild Selected FLW Scope. The internal mode value `clear_add` remains as a temporary compatibility alias, but it now means safe scoped rebuild.

The normal production path no longer deletes Moodle courses by numeric ID, resets Moodle ID sequences, clears whole Stage Courses, deletes legacy Unit Courses, or deletes teacher/manual content.

## Scope

Current production scope is 7 worlds / 600 units because the operator explicitly instructed that German U061-U072 are ignored. Spanish remains out of scope and is not an S8 blocker.

## Results requested by S8

| Area | Result |
| --- | --- |
| No-history rebuild result | PASS: U002 rebuilt in place with cmid 2117 preserved |
| History-bearing rebuild result | PASS: U001 superseded old cmid 2116 and created current cmid 2123 |
| Supersession result | PASS: old U001 hidden and retained as historical; new current has stable cmidnumber |
| Course-ID stability | PASS: U001/U002 course ID 204 preserved; U005 course ID 205 preserved |
| Section-ID stability | PASS: U001 section 2199, U002 section 2200, U005 section 2204 preserved |
| Manual content result | PASS: manual Pages remained visible and untouched |
| Learner attempt result | PASS: historical U001 retained 15 tracking rows |
| Grade history result | PASS: historical U001 retained grade 90 |
| Completion history result | PASS: historical U001 retained completion state 1 |
| Legacy course result | PASS: legacy Unit Course detected as informational and preserved |
| Failure recovery result | PASS: invalid package did not change existing current cmid; supersession code creates replacement before retirement |
| Cancel / resume result | PASS: same completed rebuild rerun skipped unchanged and created no duplicate supersession |
| Duplicate-conflict result | PASS: duplicate current SCORM blocked as `SCORM_DUPLICATE` |
| Wrong-stage result | PASS: wrong-stage mapping blocked as `UNIT_STAGE_MOVE_REQUIRED` |
| Destructive old function test | PASS: smoke asserts old helpers are unreachable from normal import body |
| Current/historical mapping result | PASS: S8 map records current cmid 2123 and historical cmid 2116 |
| Seven-world scope result | PASS: 600-unit scope retained, Spanish out of scope |
| S7 regression | PASS: overwrite dry-run unchanged for 2 production Real units |
| S2B regression | PASS: S2B prior PASS retained; navigator runtime smoke remains PASS |
| Editor regression | PASS: full smoke suite PASS |
| Moodle core | PASS: unchanged |

## Files changed

- `server.py`
- `static/index.html`
- `static/app.js`
- `scripts/import_scorm_pilot_to_moodle.php`
- `scripts/smoke_test.py`
- `scripts/s8_moodle_rebuild_probe.php`
- `scripts/s8_generate_rebuild_fixtures.py`
- `docs/moodle-export-v2/S8_REBUILD_ARCHITECTURE.md`
- `docs/moodle-export-v2/S8_SCOPE_OWNERSHIP.md`
- `docs/moodle-export-v2/S8_HISTORY_PRESERVATION.md`
- `docs/moodle-export-v2/S8_SUPERSESSION.md`
- `docs/moodle-export-v2/S8_LEGACY_PROTECTION.md`
- `docs/moodle-export-v2/S8_FAILURE_RECOVERY.md`
- `docs/moodle-export-v2/S8_TEST_REPORT.md`
- `docs/moodle-export-v2/S8_REPORT.md`
- `docs/moodle-export-v2/S8_MANIFEST.json`

## Evidence reports

- `verification_exports/s8_disposable_rebuild/s8_fixture_summary.json`
- `verification_exports/s8_disposable_rebuild/s8_seed_v1_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_u002_v2_dry_run_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_u002_v2_real_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_superseded_snapshot.json`
- `verification_exports/s8_disposable_rebuild/s8_u003_duplicate_block_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u004_wrong_stage_block_report.json`
- `verification_exports/s8_disposable_rebuild/s8_multi_stage_v2_real_report.json`
- `verification_exports/s8_disposable_rebuild/s8_legacy_detection_preview_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u005_invalid_failure_report.json`
- `verification_exports/s8_disposable_rebuild/s8_resume_idempotence_real_report.json`
- `verification_exports/s8_rebuild_tests/s8_s7_overwrite_regression_dry_run_report.json`

## Known limitations

No production-only mid-creation failure injection hook was added. The failure recovery claim is covered by code-path inspection and real invalid-package safety testing.

S8 did not start S9.

