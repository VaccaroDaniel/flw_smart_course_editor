# Gate S5 — Grade and Completion Behavior

Status: PASS

## In-place update

For safe package updates, S5 uses `scorm_update_instance()` and preserves:

- cmid
- scorm instance id
- grade item identity
- existing `scorm_attempt` rows
- existing `scorm_scoes_value` rows when SCO identifiers are stable

Observed after tracking seed and safe updates:

- cmid/scorm id: `2094` / `71`
- grade item id: `565`
- learner grade row id: `209`
- final/raw grade: `95`
- completion row: none configured for this fixture

Evidence:

- `s5_tracking_after_update_snapshot.json`
- `s5_tracking_after_reorder_snapshot.json`
- `s5_tracking_after_add_sco_snapshot.json`

## Supersession

When S5 supersedes, Moodle creates a new grade item for the new current SCORM. Historical grade and tracking remain attached to the hidden historical cmid.

Unsafe-removal evidence:

- historical cmid/scorm id: `2094` / `71`
- historical grade item id: `565`
- historical grade grade id: `209`
- historical final/raw grade: `95`
- new current cmid/scorm id: `2095` / `72`
- new current grade item id: `566`
- new current grade has no final/raw grade until the learner attempts the new current package

Forced-supersession evidence:

- new current cmid/scorm id: `2097` / `73`
- new current grade item id: `567`
- new current grade remains empty for the learner fixture

This is the desired behavior: supersession preserves old learner history but gives the new current package a clean grade/tracking space.
