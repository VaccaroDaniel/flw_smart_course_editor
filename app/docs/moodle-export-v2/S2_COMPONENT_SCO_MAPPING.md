# S2 Component → SCO Mapping

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## Mapping field

Exports now include:

```text
componentMappings
```

Each mapping contains:

```json
{
  "componentId": "REW-U023-L01",
  "componentKey": "L01",
  "componentIdSource": "source_lesson_id",
  "kind": "lesson",
  "sourceId": "l1",
  "title": "Lesson 1: ...",
  "scoIdentifier": "FLW_REW_U023_L01",
  "itemIdentifier": "FLW_REW_U023_L01",
  "resourceIdentifier": "FLW_REW_U023_L01_RES",
  "launchFile": "scos/lesson-l01.html",
  "parentUnitId": "REW-U023",
  "trackSeparately": true,
  "displayOrder": 1,
  "displayOrderIsCanonical": false
}
```

## Component-key conventions

| Component | Key |
|---|---:|
| Lesson 1 / `l1` / `lesson1` / `lesson-01` | `L01` |
| Lesson 2 | `L02` |
| Vocabulary / vocab / vb / words / wort | `VOCAB` |
| Watch / video | `WATCH` |
| Project | `PROJECT` |
| Progress / result / results / checkpoint | `RESULT` |
| Other stable HTML/profile section IDs | sanitized source ID |

If a required component has no stable source ID, S2 uses a generated position fallback and marks:

```text
componentIdSource = generated_position_fallback
```

This fallback is documented as a risk because the source has no better identity. Existing FLW lesson IDs are used whenever present.

## Manifest XML

SCO item identifiers now use the stable SCO identifier. Resource identifiers are stable too:

```xml
<item identifier="FLW_REW_U023_L01" identifierref="FLW_REW_U023_L01_RES">
```

This is the key Moodle needs later to preserve SCO row identity across SCORM package updates.
