# S7 Batch Status Contract

Gate: S7 — Public batch statuses  
Created: 2026-08-24

## Public unit result statuses

S7 reports each selected Unit with one of these user-facing states:

- `CREATED`
- `UPDATED`
- `UNCHANGED`
- `SUPERSEDED`
- `BLOCKED`
- `CONFLICT`
- `FAILED`

## Moodle action statuses

Stage Course statuses include:

- `REUSE_STAGE_COURSE`
- `CREATE_STAGE_COURSE`
- `WOULD_CREATE_STAGE_COURSE`
- `STAGE_UNRESOLVED`
- `STAGE_CONFLICT`

Unit Section statuses include:

- `CREATE_SECTION`
- `UPDATE_SECTION`
- `REUSE_SECTION`
- `UNIT_ALREADY_EXISTS`
- `STAGE_UNRESOLVED`

SCORM statuses include:

- `CREATE_SCORM`
- `UPDATE_SCORM`
- `UNCHANGED`
- `SUPERSEDE_AND_CREATE_SCORM`
- `SCORM_DIFF_REQUIRES_PACKAGE`
- `SCORM_UPDATE_FAILED`

## Summary counters

S7 reports:

- `stageCourseCount`
- `reusedStageCourses`
- `createdStageCourses`
- `wouldCreateStageCourses`
- `legacyUnitCoursesFound`
- `unitSectionCount`
- `createdUnitSections`
- `wouldCreateUnitSections`
- `reusedUnitSections`
- `unitSectionFailures`
- `scormCreated`
- `scormUpdated`
- `scormUnchanged`
- `scormSuperseded`
- `scormDiffRequiresPackage`
- `scormFailures`
- `unitsCreated`
- `unitsUpdated`
- `unitsUnchanged`
- `unitsBlocked`
- `unitsConflict`
- `unitsFailed`
- `manualContentPreserved`
- `attemptsPreserved`

## Import mode contract

Overwrite:

```text
Upsert each selected Unit into its canonical Stage Course and Unit Section.
Do not clear Stage Courses.
Do not delete unrelated Moodle content.
```

Add New Unit:

```text
Require a unique canonical UnitID.
If the Unit already exists, return UNIT_ALREADY_EXISTS / CONFLICT.
```

Clear and Add:

```text
Rejected in S7.
Reserved for S8.
```

## Exit meaning

A batch can have a product-level `FAILED` or `CONFLICT` status while still proving correct S7 behavior if rows are deliberately blocked or conflicted and no silent wrong import occurs.

For full-catalog S7 validation, unresolved Stage metadata is expected to block affected Units.

