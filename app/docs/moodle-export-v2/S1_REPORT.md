# S1 Report

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## S1 status

```text
PASS
```

S1 is metadata/configuration/preflight only. It does not implement S2 or modify Moodle deployment architecture.

## Files changed

```text
flw_moodle_course_map.json
moodle_import_support.py
server.py
static/app.js
scripts/smoke_test.py
docs/moodle-export-v2/S1_WORLD_STAGE_MODEL.md
docs/moodle-export-v2/S1_COURSE_MAP_SCHEMA.md
docs/moodle-export-v2/S1_DEPLOYMENT_STAGE_RESOLUTION.md
docs/moodle-export-v2/S1_LANGUAGE_ROOTS.md
docs/moodle-export-v2/S1_TEST_REPORT.md
docs/moodle-export-v2/S1_REPORT.md
docs/moodle-export-v2/S1_MANIFEST.json
```

## Configuration added

```text
flw_moodle_course_map.json
```

The config is schema-versioned and centralizes:

- world identity;
- source-root markers;
- language codes;
- Moodle category settings;
- Real English deployment-stage rules;
- stage-normalization policy.

Moodle numeric course IDs are not canonical identity.

## World codes

| World | Code |
|---|---:|
| Adventure English World | AEW |
| Real English World | REW |
| Russian World | RUW |
| Chinese World | CHW |
| German World | GEW |
| Japanese World | JPW |
| Spanish World | SW |
| French World | FW |

## Stage rules

Only Real English has authoritative S1 unit-range rules:

```text
REW A1: U001-U018
REW A2: U019-U036
REW B1: U037-U060
REW B2: U061-U084
REW C1: U085-U108
```

No other-world unit-number ranges were invented.

## Manifest/preflight behavior

Direct and batch manifests now include:

```text
manifestSchemaVersion = 2
targetMetadata
worldCode
sourceStage
deploymentStageCode
unitId
courseExternalKey
unitExternalKey
scormActivityExternalKey
preflightStatus
preflight summary
```

Real Moodle import is blocked before PHP is launched when planned/exported items contain unresolved/conflicting/invalid S1 metadata.

## Unresolved / conflicting units

No conflicts were found in the real source scan.

Actual unresolved scan:

| World | Unresolved |
|---|---:|
| AEW | 3 |
| RUW | 120 |
| CHW | 133 |
| SW | source absent |

Resolved:

| World | Resolved |
|---|---:|
| AEW | 69 |
| REW | 108 |
| GEW | 60 |
| JPW | 60 |
| FW | 48 |

## Spanish root result

Spanish is configured as:

```text
sourceRootCode = 07-spanish
worldCode = SW
languageCode = es
```

The local source root is absent under:

```text
D:\WinPro.Delta\Projects\SmartCourses
```

S1 reports this explicitly as:

```text
SOURCE_ROOT_NOT_FOUND
```

## Tests run

| Check | Result |
|---|---|
| Python compile checks | PASS |
| Existing + S1 smoke test suite | PASS |
| Node syntax check on `static/app.js` | PASS |
| PHP syntax check on old importer | PASS |
| Actual SmartCourses metadata scan | PASS / documented unresolved |

## Risks

1. Russian and Chinese have no authoritative S1 deployment-stage metadata or course maps, so real all-language import remains blocked for those worlds.
2. Three Adventure review/portfolio units have blank source stage metadata and need explicit metadata or an approved map.
3. Spanish source material is not present locally; category and actual root naming must be verified before real import.
4. The old PHP importer still implements Unit→Moodle Course. It is only guarded by S1 preflight; it is not replaced until later gates.
5. S0 Moodle dataroot permission remains a later real-Moodle-test blocker.

## GO / NO-GO for S2

```text
GO for S2 design/implementation when requested.
NO-GO for real all-language Moodle import until unresolved world/stage mappings and Moodle dataroot permission are fixed.
```

STOP after Gate S1.
