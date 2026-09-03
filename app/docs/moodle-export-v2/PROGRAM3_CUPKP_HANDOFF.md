# Program-3 C-UP-KP Handoff

Status: HANDOFF ONLY  
Program-3 implementation: NOT STARTED  
Source gate: S9

## Purpose

C-UP-KP can use the Program-1 deployment contract to locate FLW Unit, lesson/component, and micro-activity identity without parsing learner-facing text or Moodle ordering. This document describes the identity handoff only; it does not implement mastery, evidence interpretation, recommendations, or adaptive learning.

## Identity layers

| Layer | Example | Program-1 mapping |
|---|---|---|
| Unit | `REW-U023` | Unit Section + Unit SCORM deployment |
| Component | `REW-U023-L02` | stable SCO identifier inside the Unit SCORM |
| Micro-activity | `REW-U023-L02-Q003` | parent `ComponentActivityID` |

Micro-activities do not require separate Moodle SCOs. They remain inside the parent component SCO unless a later contract explicitly changes that policy.

## Required lookup path

For micro evidence:

```text
MicroActivityID
→ resolve_micro_activity_parent(activityId)
→ parent ComponentActivityID
→ UnitID
→ resolve_current_unit_deployment(UnitID)
→ current Moodle cmid/scorm instance
```

For historical evidence:

```text
MicroActivityID
→ parent ComponentActivityID
→ UnitID
→ resolve_historical_unit_deployment(UnitID, cmid)
```

## Verified S9 example

S9 adds a micro-activity fixture:

```text
MicroActivityID: S8T-S80824151148-U001-WATCH-Q001
parent ComponentActivityID: S8T-S80824151148-U001-WATCH
UnitID: S8T-S80824151148-U001
UnitSCORMActivityID: S8T-S80824151148-U001-UNITSCORM
```

The parent component resolves to stable SCO identifier:

```text
FLW_S8T_S80824151148_U001_WATCH
```

and the current deployment resolves to cmid:

```text
2123
```

The historical deployment for the same Unit remains resolvable at cmid:

```text
2116
```

## C-UP-KP must not parse

C-UP-KP should not derive identity from:

- Moodle course title;
- Moodle section name;
- Moodle section number;
- Moodle activity display name;
- SCORM native TOC label;
- lesson text;
- button text;
- DOM order.

Those values may change without changing the stable Program-1 identity.

## Deferred to Program-3

- Knowledge-point schema.
- mastery calculation.
- evidence scoring.
- recommendation logic.
- adaptive sequencing.
- UI/dashboard integration.

## Evidence

- `verification_exports\s9_final_qa\s9_micro_activity_contract_fixture.json`
- `verification_exports\s9_final_qa\s9_contract_check_report.json`
- `docs\moodle-export-v2\P1_CONTENT_DEPLOYMENT_CONTRACT_V1.md`

