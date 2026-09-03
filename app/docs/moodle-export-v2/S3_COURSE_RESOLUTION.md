# S3 Course Resolution

Created: 2026-08-24

## Resolver input

The resolver consumes the normalized S1 target metadata already present in direct/batch manifests:

- `worldCode`
- `worldTitle`
- `languageCode`
- `sourceStage`
- `deploymentStageCode`
- `courseExternalKey`
- `courseShortname`
- `courseIdnumber`
- `moodleCategory`

S3 does not rediscover stage from Moodle titles or duplicate the S1 stage-resolution rules.

## Resolution order

Implemented order:

1. existing FLW Program-1 framework mapping, when `flwcupkp_framework.courseid` is present for matching World+Stage;
2. exact Moodle `course.idnumber` match;
3. explicit legacy Unit Course candidate reporting via `LEGACY_UNIT_COURSE_FOUND`;
4. create a new Stage Moodle Course when authorized and no conflict exists.

Fuzzy title matching is not canonical resolution.

## Machine-readable statuses

Supported S3 statuses:

- `REUSE_STAGE_COURSE`
- `CREATE_STAGE_COURSE`
- `COURSE_IDNUMBER_CONFLICT`
- `CATEGORY_MISSING`
- `STAGE_UNRESOLVED`
- `STAGE_CONFLICT`
- `LEGACY_UNIT_COURSE_FOUND`
- `PERMISSION_DENIED`
- `COURSE_CREATE_FAILED`

## Grouping

Batch preview/import groups selected Units by:

```text
WorldCode + DeploymentStageCode
```

Example:

```text
REW U019
REW U020
REW U023
REW U036
→ one resolver call for REW:A2
→ one Moodle Stage Course FLW_REW_A2
→ 4 Unit Sections planned for S4
```

The S3 preview/report uses:

```text
futureUnitAction = UNIT_SECTION_PENDING_S4
unitSectionsCreated = 0
scormActivitiesImported = 0
```

