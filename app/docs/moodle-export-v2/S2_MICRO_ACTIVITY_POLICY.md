# S2 Micro-Activity Policy

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## Policy

Micro-activities remain inside their parent component SCO.

Examples:

```text
REW-U023-L03-Q001
→ parentComponentId: REW-U023-L03
→ trackAsSeparateSco: false
```

No question-level, card-level, hint-level, or feedback-level SCORM SCOs are created in S2.

## Mapping field

Exports now include:

```text
microActivityMappings
```

Each mapping contains:

```json
{
  "activityId": "REW-U023-L03-Q001",
  "activityKey": "Q001",
  "activityIdSource": "source_activity_id",
  "sourceActivityId": "q001",
  "kind": "practice",
  "parentComponentId": "REW-U023-L03",
  "parentComponentKey": "L03",
  "parentScoIdentifier": "FLW_REW_U023_L03",
  "parentUnitId": "REW-U023",
  "trackAsSeparateSco": false
}
```

Mappings are emitted where IDs are available in `UNIT_DATA`, practice arrays, watch practice, or related structured metadata.

## No SCO explosion

A lesson with many practice items still creates one lesson SCO. The micro-activity list supports later Learning History / C-UP-KP mapping without increasing LMS object count.
