# S1 Course Map Schema

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## Configuration file

```text
flw_moodle_course_map.json
```

The schema is versioned:

```json
{
  "schemaVersion": 1,
  "stageNormalization": {},
  "worlds": {}
}
```

## World fields

Each world entry is keyed by `sourceRootCode` and contains:

| Field | Purpose |
|---|---|
| `sourceRootCode` | Stable source-root key such as `02-real` |
| `worldCode` | Stable FLW world identity such as `REW` |
| `worldTitle` | Human-readable world title |
| `languageCode` | ISO-like language code for planning |
| `sourceRootMarkers` | Directory/package markers used for source-root discovery |
| `category.id` | Centralized Moodle category setting from the old importer, not canonical course identity |
| `stagePolicy` | Declares allowed metadata sources for stage resolution |
| `stageRules` | Authoritative unit-range rules when already frozen |

## Real English frozen rules

Only Real English receives canonical unit-range stage rules in S1:

| Rule | Units | Course shortname | Course idnumber |
|---|---:|---|---|
| REW A1 | U001-U018 | `FLW-REW-A1` | `FLW_REW_A1` |
| REW A2 | U019-U036 | `FLW-REW-A2` | `FLW_REW_A2` |
| REW B1 | U037-U060 | `FLW-REW-B1` | `FLW_REW_B1` |
| REW B2 | U061-U084 | `FLW-REW-B2` | `FLW_REW_B2` |
| REW C1 | U085-U108 | `FLW-REW-C1` | `FLW_REW_C1` |

Other worlds do not receive invented unit-number ranges.

## Validation rules

`server.py` validates:

- schema version;
- required world fields;
- duplicate `worldCode` values;
- category type;
- stage-rule unit ranges;
- overlapping stage-rule ranges;
- non-empty course shortname/idnumber for rules;
- no Moodle numeric course ID as portable identity.

Invalid configuration resolves planning/import items as:

```text
INVALID_CONFIG
```

Real imports are blocked before PHP is launched when a manifest contains `INVALID_CONFIG`.
