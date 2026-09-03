# Program-2 Learning / Grade History Handoff

Status: HANDOFF ONLY  
Program-2 implementation: NOT STARTED  
Source gate: S9

## Purpose

Program-2 can use the Program-1 deployment contract to resolve Moodle learning events into stable FLW identity. This document describes the handoff only; it does not implement Learning History, Grade History, dashboards, analytics, or adaptive decisions.

## Required source path

Moodle SCORM tracking event:

```text
cmid
stable SCO identifier
```

resolves through Program-1 to:

```text
ComponentActivityID
UnitID
WorldCode
DeploymentStageCode
deployment revision
current or superseded deployment state
```

Use:

```text
resolve_activity_from_cmid_and_sco(cmid, scoIdentifier)
resolve_unit_from_cmid(cmid)
resolve_content_revision_for_deployment(cmid=cmid)
```

## Moodle 5.1 tracking source

The verified local Moodle version stores SCORM 1.2 tracking in:

```text
scorm_attempt
scorm_scoes_value
scorm_element
```

Program-2 should resolve the Moodle course module ID (`cmid`) and SCO identifier from the Moodle event context, then call the Program-1 contract. It should not infer FLW identity from lesson titles, section names, or Moodle SCORM tree labels.

## Example: historical tracking row

S8/S9 disposable fixture:

```text
cmid: 2116
scoIdentifier: FLW_S8T_S80824151148_U001_OVERVIEW
```

resolves to:

```text
ComponentActivityID: S8T-S80824151148-U001-OVERVIEW
UnitID: S8T-S80824151148-U001
WorldCode: S8T
DeploymentStageCode: A1
status: SUPERSEDED
```

The historical learner tracking remains attached to cmid `2116`. Program-2 must not rewrite it to the new current cmid `2123`.

## Example: current tracking row

```text
cmid: 2123
scoIdentifier: FLW_S8T_S80824151148_U001_WATCH
```

resolves to:

```text
ComponentActivityID: S8T-S80824151148-U001-WATCH
UnitID: S8T-S80824151148-U001
UnitSCORMActivityID: S8T-S80824151148-U001-UNITSCORM
status: CURRENT
```

## Grades and completion

For grade or completion records where the event is attached to a Moodle activity:

```text
cmid → resolve_unit_from_cmid(cmid)
```

Then join to:

```text
UnitID
UnitSCORMActivityID
WorldCode
DeploymentStageCode
deploymentRevision
status
```

Grade history and completion state must remain associated with the Moodle cmid/scorm instance that produced them.

## Resume behavior

Program-2 should store stable FLW component identity, not raw Moodle launch order. A resume event should resolve to the last meaningful stable `ComponentActivityID`. If a component is reordered but keeps the same stable ComponentID/SCO identifier, Program-2 history remains valid.

## Deferred to Program-2

- Learning History storage schema.
- Grade History storage schema.
- reporting views;
- analytics rollups;
- retention and privacy rules;
- adaptive interpretation of evidence.

## Evidence

- `docs\moodle-export-v2\S2B_REPORT.md`
- `docs\moodle-export-v2\S5_REPORT.md`
- `docs\moodle-export-v2\S8_REPORT.md`
- `verification_exports\s9_final_qa\s9_contract_check_report.json`

