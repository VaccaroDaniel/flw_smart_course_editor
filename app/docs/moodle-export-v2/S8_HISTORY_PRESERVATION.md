# S8 History Preservation

Status: PASS  
Date: 2026-08-24

## Learner-history risk model

S8 treats a current Unit SCORM as history-bearing when it has learner data:

- SCORM attempts
- SCORM tracking rows
- non-empty grade grade rows
- completion rows

Blank Moodle grade items alone do not count as learner history. This was corrected during S8 because every SCORM may have a grade item even before a learner attempt exists.

## History-bearing test Unit

Fixture:

- Unit: `S8T-S80824151148-U001`
- Stage Course ID: 204
- Unit Section ID: 2199
- old current cmid: 2116
- old SCORM id: 92
- new current cmid after rebuild: 2123
- new SCORM id after rebuild: 97

Seeded learner data before rebuild:

- 15 SCORM tracking rows
- tracked SCOs: Overview, Watch, Progress Result
- `cmi.core.lesson_status`
- `cmi.core.score.raw`
- `cmi.core.lesson_location`
- `cmi.core.session_time`
- `cmi.suspend_data`
- grade: 90
- completion state: 1

## Result

Rebuild action:

- `REBUILD_WITH_SUPERSESSION`

Historical activity:

- old cmid 2116 preserved
- old cmid hidden
- old idnumber changed to `FLW_S8T_S80824151148_U001_UNITSCORM_REV1_SUPERSEDED`
- 15 tracking rows preserved
- grade 90 preserved
- completion state 1 preserved
- lesson location rows preserved
- suspend data rows preserved

Current activity:

- new cmid 2123
- stable current idnumber restored to `FLW_S8T_S80824151148_U001_UNITSCORM`
- no historical tracking rows copied into the new current SCORM

Reports:

- `verification_exports/s8_disposable_rebuild/s8_u001_seed_history_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_u002_v2_real_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_superseded_snapshot.json`
- `verification_exports/s8_disposable_rebuild/s8_u001_after_rebuild_snapshot.json`

## No-history test Unit

Fixture:

- Unit: `S8T-S80824151148-U002`
- Stage Course ID: 204
- Unit Section ID: 2200
- current cmid before/after: 2117
- SCORM id before/after: 93

Result:

- `REBUILD_IN_PLACE`
- no supersession
- cmid preserved
- Unit Section preserved
- manual Page preserved

Report:

- `verification_exports/s8_disposable_rebuild/s8_u002_after_rebuild_snapshot.json`

