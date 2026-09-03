# S3 Test Report

Created: 2026-08-24

## Moodle version

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
wwwroot = https://main.flw.com
```

## Real Moodle tests

| Test | Result | Evidence |
|---|---|---|
| A — Create REW A2 | PASS | `CREATE_STAGE_COURSE`, course id `200`, idnumber `FLW_REW_A2` |
| B — Reuse REW A2 | PASS | REW U019 reused course id `200` |
| C — Multiple A2 Units | PASS | U019/U020/U023/U036 grouped into one Stage Course, course id `200` |
| D — Different Stage | PASS | REW U061 created `FLW_REW_B2`, course id `201`, different from A2 |
| E — Repeat/idempotency | PASS | repeated A2 run reused course id `200`, no duplicate A2 course |
| F — IDNUMBER conflict | PASS | mismatched expected definition for `FLW_REW_A2` returned `COURSE_IDNUMBER_CONFLICT`; no adoption/overwrite |
| G — Category missing | PASS | invalid category `999999` returned `CATEGORY_MISSING`; no course created |
| H — Stage unresolved | PASS | unresolved fixture returned `STAGE_UNRESOLVED`; no course created |
| I — Legacy Unit Course | PASS | temporary `Real English World V2 Unit 023` fixture reported `LEGACY_UNIT_COURSE_FOUND`; not adopted/deleted by resolver |
| J — Permissions | PASS | unprivileged user creation attempt for REW C1 returned `PERMISSION_DENIED`; no C1 course created |
| K — Editor regression | PASS | `python scripts/smoke_test.py` all PASS |
| L — S2/S2B regression | PASS | S2/S2B smoke guards remain PASS; no SCORM structure/navigation code changed in S3 |

## Courses created

| id | idnumber | shortname | fullname | category | Unit sections | Modules |
|---:|---|---|---|---:|---:|---:|
| 200 | `FLW_REW_A2` | `FLW-REW-A2` | `Real English World — A2` | 143 | 0 | 0 |
| 201 | `FLW_REW_B2` | `FLW-REW-B2` | `Real English World — B2` | 143 | 0 | 0 |

Moodle has the normal course section 0 only.

## Temporary fixtures cleaned

- Temporary legacy Unit Course fixture removed.
- Temporary unprivileged permission-test user soft-deleted.
- No `FLW_REW_C1` course exists after the permission test.

## Commands run

```text
php -l scripts\import_scorm_pilot_to_moodle.php
python -m py_compile server.py scripts\smoke_test.py
node --check static\app.js
python scripts\smoke_test.py
php scripts\import_scorm_pilot_to_moodle.php --preview-courses ...
php scripts\import_scorm_pilot_to_moodle.php --by-language ...
```

