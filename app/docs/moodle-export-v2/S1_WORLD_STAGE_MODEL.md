# S1 World + Deployment Stage Model

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## Target identity model

S1 adds metadata for the frozen target architecture without implementing the later Moodle deployment changes:

```text
FLW World + Deployment Stage
→ Moodle Course

FLW Unit
→ Moodle Section

1 FLW Unit
→ 1 SCORM 1.2 package
```

This gate does not create Moodle stage courses, Moodle sections, or final Unit SCORM activities.

## Stable world codes

The selected codes reuse existing repository/importer/package naming where it was already visible during S0/S1, with version numbers removed from the stable code.

| Source root code | World code | World title | Language code | Reason |
|---|---:|---|---:|---|
| `01-adventure` | `AEW` | Adventure English World | `en` | Existing AEW/AEW2 naming |
| `02-real` | `REW` | Real English World | `en` | Existing REW/REW2 naming |
| `03-russian` | `RUW` | Russian World | `ru` | Existing `RUW2_U...` packages |
| `04-chinese` | `CHW` | Chinese World | `zh` | Existing CHW/CW naming |
| `05-german` | `GEW` | German World | `de` | Existing GEW/GW3 naming |
| `06-japanese` | `JPW` | Japanese World | `ja` | Existing JPW/JW3 naming |
| `07-spanish` | `SW` | Spanish World | `es` | Configured for future Spanish source; local source root absent in S0/S1 |
| `08-french` | `FW` | French World | `fr` | Existing FW/FW_U naming |

## Stable keys produced by S1

For a resolved Real English Unit 023:

```text
WorldCode: REW
DeploymentStageCode: A2
Course external key: FLW_REW_A2
UnitID: REW-U023
Unit external key: REW-U023
Future Unit SCORM activity key: REW-U023-UNITSCORM
```

Keys intentionally exclude:

- timestamps;
- Moodle numeric course IDs;
- section positions;
- titles;
- random UUIDs.

## Status

The model is implemented in:

```text
flw_moodle_course_map.json
server.py
moodle_import_support.py
```

The current Unit editor behavior remains frozen; S1 only adds deployment metadata and manifest/preflight fields.
