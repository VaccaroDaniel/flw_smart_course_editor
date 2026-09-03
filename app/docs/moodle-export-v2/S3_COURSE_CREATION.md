# S3 Course Creation

Created: 2026-08-24

## Moodle API

S3 creates courses through Moodle's supported course API:

```text
create_course()
```

It does not insert directly into core Moodle course tables.

## Category validation

Before course creation, S3 verifies the configured S1 Moodle category exists in `course_categories`.

Missing or invalid category returns:

```text
CATEGORY_MISSING
```

No arbitrary category hierarchy is silently created.

## Permission check

For real creation, S3 checks:

```text
moodle/course:create
context_coursecat::<configured category>
```

If the current Moodle user cannot create the course:

```text
PERMISSION_DENIED
```

Dry-run/preview remains available and reports intended action without creating the course.

## Failure safety

If creation fails, S3 returns:

```text
COURSE_CREATE_FAILED
```

The local stage-course mapping record is written only after Moodle course creation succeeds.

## Mapping record

S3 writes a minimal repository-compatible local stage-course map when a Stage Course is created or reused:

```text
flw_moodle_stage_course_map.json
```

The verification run used:

```text
verification_exports/s3_stage_course_tests/s3_stage_course_map.json
```

Fields:

- `WorldCode`
- `DeploymentStageCode`
- `courseExternalKey`
- `moodleCourseId`
- `moodleCourseIdnumber`
- `status`
- `createdAt`
- `updatedAt`

