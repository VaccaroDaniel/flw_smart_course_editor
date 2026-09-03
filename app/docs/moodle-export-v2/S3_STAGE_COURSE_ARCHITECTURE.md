# S3 Stage Course Architecture

Created: 2026-08-24

Gate: S3 — Moodle Stage Course Resolver

## Target implemented in S3

S3 changes only Moodle course resolution:

```text
FLW World + Deployment Stage
→ Moodle Course
```

S3 intentionally does not implement the later mappings:

```text
FLW Unit
→ Moodle Section

1 FLW Unit
→ 1 SCORM 1.2 package/activity in Moodle
```

Those remain pending S4/S5.

## Stable identity

Canonical Stage Course identity is:

```text
courseExternalKey = FLW_<WorldCode>_<DeploymentStageCode>
Moodle course.idnumber = courseExternalKey
```

Example:

```text
REW + A2
→ FLW_REW_A2
→ Moodle course.idnumber = FLW_REW_A2
```

Moodle numeric `course.id` is treated only as a deployment-local database identifier.

## Presentation fields

For resolved S1 metadata, S3 derives:

```text
fullname:  <WorldTitle> — <DeploymentStageCode>
shortname: value from S1 course map when present; otherwise FLW-<WorldCode>-<Stage>
idnumber:  courseExternalKey
category:  S1 configured Moodle category
```

Real English examples:

| World | Stage | idnumber | shortname | fullname |
|---|---:|---|---|---|
| REW | A2 | `FLW_REW_A2` | `FLW-REW-A2` | `Real English World — A2` |
| REW | B2 | `FLW_REW_B2` | `FLW-REW-B2` | `Real English World — B2` |

## S3 boundary

S3 does not:

- create Unit sections;
- create or update SCORM activities;
- clear course contents;
- delete legacy Unit Courses;
- migrate learner history;
- use numeric course IDs as semantic identity;
- start S4.

