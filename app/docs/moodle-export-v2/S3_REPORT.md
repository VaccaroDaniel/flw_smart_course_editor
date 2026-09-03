# S3 Report

Created: 2026-08-24

Gate: S3 — Moodle Stage Course Resolver

## S3 STATUS

```text
PASS
```

## MOODLE VERSION

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
wwwroot = https://main.flw.com
```

## STAGE COURSE KEY FORMAT

```text
FLW_<WorldCode>_<DeploymentStageCode>
```

Example:

```text
FLW_REW_A2
```

## COURSE IDNUMBER FORMAT

```text
course.idnumber = courseExternalKey
```

Example:

```text
course.idnumber = FLW_REW_A2
```

## COURSE RESOLUTION ORDER

1. FLW Program-1 framework mapping where a matching row has `courseid`.
2. Exact Moodle `course.idnumber`.
3. Legacy Unit Course candidate reporting.
4. Create Stage Course when authorized and conflict-free.

## COURSES CREATED

| id | idnumber | shortname | fullname |
|---:|---|---|---|
| 200 | `FLW_REW_A2` | `FLW-REW-A2` | `Real English World — A2` |
| 201 | `FLW_REW_B2` | `FLW-REW-B2` | `Real English World — B2` |

No Unit sections or SCORM activities were created.

## COURSES REUSED

REW U019, U020, U023, and U036 all reused:

```text
course id 200
idnumber FLW_REW_A2
```

## CONFLICTS FOUND

Conflict handling was verified:

```text
COURSE_IDNUMBER_CONFLICT
```

The resolver does not silently adopt or overwrite a course when the `idnumber` owner does not match the expected Stage Course definition.

## LEGACY UNIT COURSES FOUND

Temporary legacy fixture:

```text
Real English World V2 Unit 023 S3 Legacy Fixture
```

Result:

```text
LEGACY_UNIT_COURSE_FOUND
```

The resolver still reused canonical `FLW_REW_A2` and did not adopt/delete/migrate the legacy Unit Course.

## CATEGORY VALIDATION

PASS.

Invalid category fixture:

```text
999999
```

Result:

```text
CATEGORY_MISSING
```

## PERMISSION TEST

PASS.

Unprivileged user attempted real creation of missing REW C1.

Result:

```text
PERMISSION_DENIED
```

No `FLW_REW_C1` course was created.

## FILES CHANGED

```text
scripts/import_scorm_pilot_to_moodle.php
scripts/smoke_test.py
static/app.js
static/index.html
docs/moodle-export-v2/S3_STAGE_COURSE_ARCHITECTURE.md
docs/moodle-export-v2/S3_COURSE_RESOLUTION.md
docs/moodle-export-v2/S3_COURSE_CREATION.md
docs/moodle-export-v2/S3_LEGACY_COURSE_DETECTION.md
docs/moodle-export-v2/S3_TEST_REPORT.md
docs/moodle-export-v2/S3_REPORT.md
docs/moodle-export-v2/S3_MANIFEST.json
```

## TESTS RUN

```text
php -l scripts\import_scorm_pilot_to_moodle.php
python -m py_compile server.py scripts\smoke_test.py
node --check static\app.js
python scripts\smoke_test.py
real Moodle S3 preview/create/reuse/conflict/category/unresolved/legacy/permission checks
```

## TEST RESULTS

All required S3 tests A-L passed.

Final smoke output includes:

```text
s1DeploymentMetadata PASS
s3StageCourseResolver PASS
s2bNavigatorRuntimeJs PASS
s2ScormIdentity PASS
```

## REGRESSIONS

No regressions detected.

Intentional S3 behavior change:

- old by-language canonical import no longer creates one Moodle course per Unit;
- old `Clear and Add` numeric-course deletion/reset semantics are disabled in S3 canonical path;
- S3 creates/reuses Stage Courses only and reports `UNIT_SECTION_PENDING_S4`.

## GO / NO-GO FOR S4

```text
GO
```

S4 was not started.

