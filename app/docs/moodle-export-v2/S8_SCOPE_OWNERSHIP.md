# S8 Scope and Ownership

Status: PASS  
Date: 2026-08-24

## Production scope

Current controlling scope:

- Adventure English: 72 units
- Real English: 108 units
- Russian: 120 units
- Chinese: 132 valid units
- German: 60 units, with U061-U072 intentionally ignored
- Japanese: 60 units
- French: 48 units

Total: 600 units

Spanish remains out of scope and is not an S8 blocker.

## Selected FLW scope

Rebuild Selected FLW Scope acts only on selected FLW identities:

- World
- Deployment Stage
- Unit
- Unit SCORM activity

Examples verified in S8:

- Single stage, two Units: `S8T-S80824151148-U001`, `S8T-S80824151148-U002`
- Multi-stage scope: `S8T-S80824151148-U002` in A1 and `S8T-S80824151148-U005` in A2
- Wrong-stage block: `S8T-S80824151148-U004` created in A1 and attempted against A2

## Importer-owned objects

Importer-owned objects are identified by stable S3-S5 identity:

- canonical FLW Unit SCORM cmidnumber, for example `FLW_S8T_S80824151148_U001_UNITSCORM`
- superseded FLW Unit SCORM cmidnumber suffix, for example `_REV1_SUPERSEDED`
- pending/failed rebuild suffix, for failure recovery
- Unit Section marker block in section summary

Manual teacher content is not importer-owned.

## Manual content policy

Inside a Unit Section, S8 preserves non-FLW Moodle activities/resources.

Real test:

- U001 manual Page: `S8_MANUAL_PAGE_S80824151148_U001`
- U002 manual Page: `S8_MANUAL_PAGE_S80824151148_U002`
- After rebuild, both Pages remained visible in their original Unit Sections.

Reports:

- `verification_exports/s8_disposable_rebuild/s8_u001_after_rebuild_snapshot.json`
- `verification_exports/s8_disposable_rebuild/s8_u002_after_rebuild_snapshot.json`

## Conflict policy

S8 blocks instead of guessing when ownership or stage identity is unsafe.

Verified blockers:

- duplicate current SCORM -> `SCORM_DUPLICATE` / `BLOCKED_MAPPING_CONFLICT`
- wrong stage -> `UNIT_STAGE_MOVE_REQUIRED` / `BLOCKED_STAGE_CONFLICT`

Reports:

- `verification_exports/s8_disposable_rebuild/s8_u003_duplicate_block_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u004_wrong_stage_block_report.json`

