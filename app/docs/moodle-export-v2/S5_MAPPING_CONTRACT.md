# Gate S5 — Mapping Contract

Status: PASS

## Local map

Default map path:

`flw_moodle_unit_scorm_map.json`

S5 verification map path:

`verification_exports/s5_unit_scorm_tests/s5_unit_scorm_map.json`

## Key

`unitScormActivities[UnitSCORMActivityID]`

Example:

`unitScormActivities["REW-U023-UNITSCORM"]`

## Current entry fields

- `UnitID`
- `UnitSCORMActivityID`
- `WorldCode`
- `DeploymentStageCode`
- `courseExternalKey`
- `moodleCourseId`
- `moodleSectionId`
- `moodleSectionNumber`
- `stableCmidNumber`
- `scormManifestIdentifier`
- `currentRevision`
- `currentCmid`
- `currentScormId`
- `packageSha1`
- `packageSha256`
- `componentScoIdentifiers`
- `status`
- `lastAction`
- `createdAt`
- `updatedAt`
- `history`

## Statuses

Implemented/actioned statuses include:

- `CREATE_SCORM`
- `UPDATE_SCORM`
- `UNCHANGED`
- `SUPERSEDE_SCORM`
- `SCORM_TARGET_MISSING`
- `SCORM_DUPLICATE`
- `SCORM_IDENTITY_CONFLICT`
- `SCORM_PACKAGE_INVALID`
- `SCORM_UPDATE_UNSAFE`
- `SCORM_ATTEMPTS_PRESENT`
- `SECTION_NOT_RESOLVED`
- `COURSE_NOT_RESOLVED`
- `PERMISSION_DENIED`
- `SCORM_CREATE_FAILED`
- `SCORM_UPDATE_FAILED`
- `SCORM_SUPERSEDE_FAILED`

`MANUAL_CONTENT_PRESERVED` is represented in S5 verification reports by the manual Page fixture snapshots rather than as a per-unit SCORM action.

## Resolution contract

S5 resolves a target SCORM by:

1. existing Unit SCORM map current cmid;
2. exact stable cmidnumber in the Moodle Course;
3. a single safe adoption candidate in the resolved Unit Section whose parsed SCORM manifest identifier matches;
4. create new SCORM.

Map conflicts block rather than silently adopting a different activity.

If a mapped cmid is missing because the resolved Stage Course was demonstrably
recreated after the mapping timestamp, the old cmid mapping is stale rather
than conflicting. S5 then resolves by stable cmidnumber/adoption or creates a
new SCORM and replaces the stale current mapping. Missing targets in the same
course generation continue to block as `SCORM_TARGET_MISSING`.

## Current state after S5 verification

For `REW-U023-UNITSCORM`:

- current cmid: `2097`
- current scorm id: `73`
- stable cmidnumber: `FLW_REW_U023_UNITSCORM`
- current package SHA-256: `ea312f8e5d9941e9d792337a800ab6c7b95b31c48609f70fc7033fef07db2582`
- historical cmids preserved: `2094`, `2095`
