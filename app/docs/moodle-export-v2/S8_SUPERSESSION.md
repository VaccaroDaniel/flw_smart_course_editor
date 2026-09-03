# S8 Supersession

Status: PASS  
Date: 2026-08-24

## Policy

If a Unit SCORM has learner attempts, tracking, grades, completion, or another history risk, S8 does not delete or rewrite it.

Instead:

1. Create the replacement SCORM with a temporary pending idnumber.
2. Reload and verify the replacement exists.
3. Retire the old current SCORM by changing its idnumber and hiding it.
4. Assign the stable current cmidnumber to the replacement.
5. Record the historical/current lineage in the Unit SCORM map.

The old deployment is not marked superseded before the replacement exists.

## Verified supersession

Unit: `S8T-S80824151148-U001`

Before:

- current cmid: 2116
- current SCORM id: 92
- stable cmidnumber: `FLW_S8T_S80824151148_U001_UNITSCORM`
- learner history present

After:

- historical cmid: 2116
- historical SCORM id: 92
- historical idnumber: `FLW_S8T_S80824151148_U001_UNITSCORM_REV1_SUPERSEDED`
- historical visible: 0
- new current cmid: 2123
- new current SCORM id: 97
- current idnumber: `FLW_S8T_S80824151148_U001_UNITSCORM`

## Mapping lineage

The S8 Unit SCORM map records:

- `currentCmid`: 2123
- `currentScormId`: 97
- one historical entry for cmid 2116 / SCORM id 92
- historical tracking summary retained on the old activity

Map:

- `verification_exports/s8_disposable_rebuild/maps/flw_moodle_unit_scorm_map.s8.json`

## Duplicate current protection

If Moodle contains two active SCORM modules with the same stable cmidnumber, S8 blocks instead of choosing one.

Verified result:

- `SCORM_DUPLICATE`
- `BLOCKED_MAPPING_CONFLICT`

Report:

- `verification_exports/s8_disposable_rebuild/s8_u003_duplicate_block_report.json`

