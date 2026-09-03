# S8 Rebuild Architecture

Status: PASS  
Date: 2026-08-24  
Gate: S8 only

## Scope note

The S8 master prompt text still references 612 units. The later controlling operator instruction is to ignore German U061-U072. Therefore the current production readiness scope is 7 worlds / 600 units, with Spanish out of scope.

## Visible operation

The user-facing operation is:

Rebuild Selected FLW Scope

The internal compatibility value remains `clear_add`, but the normal production semantics are now safe scoped rebuild, not global deletion or numeric-ID reset.

## Architecture

S8 keeps the S3-S7 architecture:

FLW World + Deployment Stage -> Moodle Course  
FLW Unit -> Moodle Section  
1 FLW Unit -> 1 current SCORM 1.2 activity/package  
substantial component -> 1 SCO  
micro-activities -> remain inside parent SCO

Rebuild resolves only:

- `WorldCode`
- `DeploymentStageCode`
- `UnitID`
- `UnitSCORMActivityID`
- stable Moodle `course_modules.idnumber`

It does not scope by Moodle numeric course ID, course creation date, title prefix alone, section number, or section position.

## Rebuild execution model

For each selected Unit:

1. Resolve canonical Stage Course.
2. Resolve canonical Unit Section from the local map and FLW marker.
3. Resolve the importer-owned current Unit SCORM from the local map and stable cmidnumber.
4. Detect duplicate current SCORMs, wrong-stage mappings, manual content, legacy Unit Courses, learner attempts/tracking, grade history, and completion rows.
5. Produce a read-only preview plan.
6. Require the preview hash before real rebuild.
7. Execute one of:
   - `SKIP_UNCHANGED`
   - `REBUILD_IN_PLACE`
   - `REBUILD_WITH_SUPERSESSION`
   - `BLOCK`
   - `FAILED`

## Destructive legacy behavior

The old destructive operations remain only as isolated legacy helper functions in `scripts/import_scorm_pilot_to_moodle.php`:

- `clear_course_for_overwrite()`
- `clear_courses_above_id()`
- `reset_course_id_sequence()`

They are not called by `import_by_language()` or `preview_course_map()`. Regression smoke tests assert they are unreachable from normal production modes: single Overwrite, single Add New, batch Overwrite, batch Add New, and Rebuild Selected FLW Scope.

The S8 report exposes `destructivePathGuard` values showing these helpers are not reachable from the normal import path.

## Preview requirement

Real S8 rebuild is blocked unless a package-aware dry-run preview hash is supplied.

Real test:

- Report: `verification_exports/s8_disposable_rebuild/s8_preview_required_guard_report.json`
- Result: `PREVIEW_REQUIRED`
- Public status: `BLOCKED`

