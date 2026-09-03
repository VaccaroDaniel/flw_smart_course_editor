# S6 Single Import Architecture

Gate: S6 — Single Import Modes + Single-Unit Moodle Export UI  
Created: 2026-08-24

## Scope

S6 wires the existing single-unit Smart Course Editor export flow to the production architecture:

```text
FLW World + Deployment Stage -> Moodle Stage Course
FLW Unit -> Moodle Unit Section
1 FLW Unit -> 1 current SCORM 1.2 activity/package
substantial component -> 1 SCO
micro-activities -> parent SCO
```

Batch production import behavior is intentionally not redesigned in S6.

## Single import pipeline

For one selected FLW Unit:

1. Build the SCORM package with the existing exporter.
2. Build a direct FLW manifest with stable identifiers:
   - `worldCode`
   - `deploymentStageCode`
   - `unitId`
   - `courseExternalKey`
   - `unitExternalKey`
   - `scormActivityExternalKey`
   - package hashes.
3. Reuse the S3 Stage Course resolver.
4. Reuse the S4 Unit Section resolver.
5. Reuse the S5 Unit SCORM resolver/upsert service.
6. Return a structured S6 single-import report.

## Reused services

- S3: `stage_course_definition()` and `resolve_stage_course_group()`
- S4: `unit_section_definition()` and `resolve_unit_section()`
- S5: `unit_scorm_definition()`, `resolve_current_unit_scorm()`, and `deploy_unit_scorm_activity()`

No course/section/SCORM resolution is duplicated in frontend code.

## Mutation guardrails

Single Overwrite never calls:

- `clear_course_for_overwrite()`
- `clear_courses_above_id()`
- `reset_course_id_sequence()`

The normal single path has an explicit `destructivePathGuard` report block and smoke-test assertions proving those functions are not reachable from `import_by_language()`.

## Concurrency

Python-side single import locking is scoped by:

```text
WorldCode:DeploymentStageCode:UnitID
```

Example:

```text
REW:A2:REW-U023
```

A second simultaneous import for the same key is rejected with:

```text
IMPORT_ALREADY_RUNNING
```

