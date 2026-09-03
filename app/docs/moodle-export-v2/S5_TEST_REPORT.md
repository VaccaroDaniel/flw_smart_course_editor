# Gate S5 — Test Report

Status: PASS

## Fixture

Generated editor-exported SCORM 1.2 variants with:

`python scripts/s5_generate_fixtures.py`

Fixture summary:

`verification_exports/s5_unit_scorm_tests/s5_fixture_summary.json`

Target:

- Moodle URL: `https://main.flw.com`
- Stage Course: `FLW_REW_A2`
- Moodle course id: `200`
- Unit Section: `REW-U023`
- Moodle section id: `2175`

## Real Moodle deployment tests

| Test | Expected | Result | Evidence |
|---|---:|---:|---|
| Preview create | `CREATE_SCORM` | PASS | `s5_preview_create_report.json` |
| Create | cmid `2094`, scorm id `71` | PASS | `s5_create_report.json` |
| Idempotency | `UNCHANGED`, same cmid | PASS | `s5_idempotent_report.json` |
| Seed learner tracking | 1 attempt, 15 values | PASS | `s5_tracking_seed_snapshot.json` |
| Safe content update | identifiers stable | PASS | `s5_update_content_report.json` |
| Safe title update | `UPDATE_SCORM`, same cmid | PASS | `s5_update_title_report.json` |
| Safe reorder | same scoids, new order | PASS | `s5_update_reorder_report.json` |
| Add SCO | new L04 scoid, old scoids preserved | PASS | `s5_update_add_sco_report.json` |
| Unsafe remove tracked SCO | `SUPERSEDE_SCORM` | PASS | `s5_supersede_remove_tracked_report.json` |
| Manual Page preservation | Page cmid `2096` retained | PASS | `s5_manual_content_after_unchanged.json` |
| Forced supersession | `SUPERSEDE_SCORM` | PASS | `s5_force_supersede_report.json` |

## Regression and syntax checks

Commands run:

- `python scripts/smoke_test.py`
- `python -m py_compile server.py scripts/smoke_test.py scripts/s5_generate_fixtures.py`
- `php -l scripts/import_scorm_pilot_to_moodle.php`
- `php -l scripts/s5_moodle_tracking_probe.php`
- `php -l scripts/s5_moodle_manual_content_probe.php`
- `Get-ChildItem -Recurse -Filter *.php scripts | ForEach-Object { php -l $_.FullName }`
- `node --check static/app.js`

Results: PASS.

Note: an all-Python recursive compile was stopped after it entered the bundled offline runtime under `dist/`; the targeted project Python compile had already passed.

## Issues found and fixed during S5

1. Exporter cmidnumber rule emitted `REW_U023_UNITSCORM`; fixed to emit `FLW_REW_U023_UNITSCORM`.
2. Moodle draft upload could fail if the ZIP package contenthash was not pre-warmed; fixed by seeding the ZIP in `draft_file_from_path()`.
3. `update_moduleinfo()` was not safe in this CLI update path; changed S5 in-place replacement to `scorm_update_instance()` plus course-module setters.

## Final S5 state in Moodle

Unit Section 2175 contains:

- hidden historical SCORM cmid `2094`
- hidden historical SCORM cmid `2095`
- teacher Page cmid `2096`
- current visible SCORM cmid `2097`

No teacher-authored activity was removed.
