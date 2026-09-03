# Gate S5 — Attempt and Tracking Preservation

Status: PASS

## Test learner

- username: `s5_learner_rew_u023`
- user id: `25`
- course id: `200`
- initial current cmid/scorm id: `2094` / `71`

## Seeded tracking

Seeded through Moodle SCORM APIs with `scorm_insert_track()`:

- `FLW_REW_U023_L01`
- `FLW_REW_U023_L02`
- `FLW_REW_U023_WATCH`

Each tracked SCO received:

- `cmi.core.lesson_status`
- `cmi.core.score.raw`
- `cmi.core.lesson_location`
- `cmi.core.session_time`
- `cmi.suspend_data`

Evidence:

- `verification_exports/s5_unit_scorm_tests/s5_tracking_seed_snapshot.json`

## Safe in-place updates

Content/title/reorder/add-SCO updates preserved cmid `2094`, scorm id `71`, and tracked SCO row ids:

- L01 stayed `scoid=736`
- L02 stayed `scoid=737`
- WATCH stayed `scoid=739`

Evidence:

- `s5_update_title_report.json`
- `s5_update_reorder_report.json`
- `s5_update_add_sco_report.json`
- `s5_tracking_after_update_snapshot.json`
- `s5_tracking_after_reorder_snapshot.json`
- `s5_tracking_after_add_sco_snapshot.json`

## Unsafe removal

The package `remove_tracked` removed tracked identifier `FLW_REW_U023_L02`.

S5 correctly refused in-place update and superseded:

- old cmid/scorm id: `2094` / `71`
- old retired cmidnumber: `FLW_REW_U023_UNITSCORM_REV4_SUPERSEDED`
- old visibility: hidden
- new current cmid/scorm id: `2095` / `72`

The old hidden activity still owns the learner attempt, grade, and L02 tracking.

Evidence:

- `s5_supersede_remove_tracked_report.json`
- `s5_tracking_superseded_old_snapshot.json`
- `s5_tracking_current_after_supersede_snapshot.json`

## Forced supersession

`--force-supersede` was also tested.

- prior current cmid/scorm id: `2095` / `72`
- retired cmidnumber: `FLW_REW_U023_UNITSCORM_REV5_SUPERSEDED`
- new current cmid/scorm id: `2097` / `73`

Evidence:

- `s5_force_supersede_report.json`
- `s5_tracking_current_after_force_supersede_snapshot.json`
