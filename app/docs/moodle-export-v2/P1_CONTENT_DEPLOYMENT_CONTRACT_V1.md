# P1 Content Deployment Contract v1.0

Status: FROZEN  
Gate: S9  
Scope: Program-1 Smart Course Editor → Moodle deployment mapping

## Purpose

This contract freezes the Program-1 identity and lookup surface used by downstream FLW systems. It describes how a deployed FLW learning object resolves from stable FLW identity to Moodle deployment identity without parsing Moodle titles, section order, learner-facing text, or native SCORM structure labels.

The implementation entrypoint is:

```text
p1_content_deployment_contract.py
```

The contract is read-only. It consumes Program-1 maps and exported manifests; it does not mutate Moodle.

## Frozen architecture

| FLW object | Moodle object |
|---|---|
| FLW World + Deployment Stage | Moodle Stage Course |
| FLW Unit | Moodle Unit Section |
| 1 FLW Unit | 1 SCORM 1.2 package/activity |
| Substantial lesson/component | Stable SCO inside the Unit SCORM |
| Micro-activity | Evidence inside parent component SCO |

Learner navigation is Moodle Course roadmap → Unit Section → FLW compact lesson/component navigator. Moodle's native SCORM TOC/structure must remain hidden or minimized so it does not become a second primary learner-facing navigator.

## Contract version

```text
P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION = 1.0
```

Version 1.0 is additive-compatible only. Downstream systems may rely on the field names and lookup behavior documented here. Future additions may add fields, but must not rename or remove v1.0 fields without a new major contract.

## Source artifacts

The contract reads these Program-1 mapping artifacts:

- `flw_moodle_stage_course_map.json`
- `flw_moodle_unit_section_map.json`
- `flw_moodle_unit_scorm_map.json`
- Smart Course Editor batch/single manifests containing `componentMappings` and, where present, `microActivityMappings`

Moodle numeric IDs are stored as deployment references only. Canonical identity is always the stable FLW key.

## Stable identities

| Identity | Canonical use |
|---|---|
| `WorldCode` | FLW World, for example `REW` |
| `DeploymentStageCode` | FLW deployment stage, for example `A2` |
| `courseExternalKey` | Stable Stage Course key, for example `FLW_REW_A2` |
| `UnitID` | Stable Unit key, for example `REW-U023` |
| `UnitSCORMActivityID` | Stable Unit SCORM key, for example `REW-U023-UNITSCORM` |
| `ComponentActivityID` | Stable component key, for example `REW-U023-L02` |
| `MicroActivityID` | Stable micro-activity key, for example `REW-U023-L02-Q003` |
| `scoIdentifier` | SCORM manifest item identifier, for example `FLW_REW_U023_L02` |

## Lookup services

The v1.0 service exposes these bounded lookups:

| Service | Required result |
|---|---|
| `resolve_world_stage_from_course(courseid)` | `WorldCode`, `DeploymentStageCode`, `courseExternalKey`, `moodleCourseId`, `moodleCourseIdnumber` |
| `resolve_unit_from_section(courseid, sectionid)` | `UnitID`, world/stage, Moodle course/section IDs, section number/name |
| `resolve_unit_from_cmid(cmid)` | current or historical Unit SCORM deployment for a Moodle course module ID |
| `resolve_activity_from_cmid_and_sco(cmid, scoIdentifier)` | `ComponentActivityID`, Unit, Unit SCORM, cmid, stable SCO identifier |
| `resolve_micro_activity_parent(activityId)` | micro-activity → parent component mapping |
| `resolve_current_unit_deployment(unitId)` | current Unit SCORM deployment |
| `resolve_historical_unit_deployment(unitId, cmid)` | superseded deployment for historical attempts/tracking |
| `resolve_content_revision_for_deployment(...)` | deployment revision, status, package hashes where available |
| `resolve_deployment_freshness(unitId, expectedPackageContentSha256)` | deployment state against expected FLW package content |

## Deployment states

The frozen state vocabulary is:

```text
CURRENT
OUTDATED
DRIFTED
CONFLICT
FAILED
SUPERSEDED
UNKNOWN
```

`CURRENT` means the Moodle deployment matches the mapped published FLW package content. `OUTDATED` means the current Moodle deployment's package content hash differs from the expected FLW package content hash. `SUPERSEDED` means a deployment remains resolvable for history but is no longer the current learner-facing Unit SCORM.

## Current and historical deployment rules

For a single `UnitSCORMActivityID`:

- exactly one `CURRENT` deployment is allowed;
- zero or more `SUPERSEDED` deployments may remain resolvable;
- old learner attempts, tracking rows, grades, and completion state must remain attached to the historical Moodle cmid/scorm instance;
- downstream systems must not rewrite historical attempts to the new cmid.

Future supersession rows preserve the retired deployment revision and known package hashes from the previous current map entry. Older rows created before this S9 hardening still resolve by cmid and stable SCO identifiers; their package hash fields may be blank if the old map did not record them.

## Consumer expectations

Downstream consumers must:

- use stable FLW IDs and `scoIdentifier`, not Moodle display titles or numeric section order;
- treat Moodle course IDs, section IDs, cmids, and SCORM instance IDs as deployment references;
- resolve historical data by the cmid/scorm instance that originally stored the learner event;
- treat `OUTDATED`, `DRIFTED`, `CONFLICT`, and `FAILED` deployments as not semantically identical to current FLW content;
- keep micro-activities inside their parent component unless a future contract explicitly promotes them to SCO-level tracking.

## Verification

S9 verification artifacts:

- `verification_exports\s8_disposable_rebuild\s9_p1_contract_self_test.json`
- `verification_exports\s9_final_qa\s9_contract_check_report.json`
- `verification_exports\s9_final_qa\s9_regression_test_report.json`

The S9 contract check proves:

- World+Stage → Course lookup;
- Unit → Section lookup;
- Unit SCORM → cmid lookup;
- Component → SCO lookup;
- micro-activity → parent lookup;
- current and historical deployment lookup;
- deployment freshness;
- Program-2 history handoff path;
- Program-3 C-UP-KP handoff path;
- mapping lookup performance without full Moodle scans.

