# S6 Error / Status Contract

Gate: S6 — Error and Status Contract  
Created: 2026-08-24

## Public statuses

S6 reports one of:

- `SUCCESS`
- `SUCCESS_WITH_WARNINGS`
- `UNCHANGED`
- `CONFLICT`
- `BLOCKED`
- `FAILED`

## Important action/status codes

- `CREATE_STAGE_COURSE`
- `REUSE_STAGE_COURSE`
- `CREATE_SECTION`
- `REUSE_SECTION`
- `UPDATE_SECTION`
- `CREATE_SCORM`
- `UPDATE_SCORM`
- `UNCHANGED`
- `SUPERSEDE_SCORM`
- `UNIT_ALREADY_EXISTS`
- `STAGE_UNRESOLVED`
- `STAGE_CONFLICT`
- `COURSE_IDNUMBER_CONFLICT`
- `UNIT_SECTION_DUPLICATE`
- `UNIT_STAGE_MOVE_REQUIRED`
- `SCORM_DUPLICATE`
- `SCORM_UPDATE_UNSAFE`
- `PERMISSION_DENIED`
- `PREVIEW_STALE`
- `IMPORT_ALREADY_RUNNING`

## Actionable messages

Examples:

- `UNIT_ALREADY_EXISTS`: tells the user to use Copy Unit first.
- `PREVIEW_STALE`: tells the user to run Preview Moodle destination again.
- `PERMISSION_DENIED`: reports the missing Moodle capability area without mutating.

## Non-destructive single Overwrite

Single Overwrite reports:

```json
{
  "destructivePathGuard": {
    "singleOverwriteClearsStageCourse": false,
    "clear_course_for_overwrite_reachable": false,
    "clear_courses_above_id_reachable": false,
    "reset_course_id_sequence_reachable": false
  }
}
```

