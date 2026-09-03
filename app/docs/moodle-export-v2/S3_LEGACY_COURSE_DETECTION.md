# S3 Legacy Course Detection

Created: 2026-08-24

## Legacy pattern

Legacy Moodle courses may follow the old architecture:

```text
FLW Unit
→ Moodle Course
```

Examples:

```text
Real English World V2 Unit 023
REW2 U023
```

## S3 behavior

S3 does not treat these courses as canonical Stage Courses.

When detected, the resolver reports:

```text
LEGACY_UNIT_COURSE_FOUND
```

The canonical Stage Course is still resolved by `course.idnumber = FLW_<World>_<Stage>`.

## No mutation

S3 does not:

- delete legacy Unit Courses;
- clear legacy course contents;
- adopt a legacy Unit Course as the Stage Course;
- migrate learner history.

Legacy migration/adoption is reserved for a later explicit workflow.

