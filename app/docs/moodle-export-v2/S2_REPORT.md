# S2 Report

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## S2 status

```text
PASS
```

S2 stopped after SCORM package/SCO identity and mapping work. S2B navigation was not started.

## Files changed

```text
server.py
scripts/smoke_test.py
docs/moodle-export-v2/S2_SCORM_STRUCTURE.md
docs/moodle-export-v2/S2_SCORM_IDENTITY.md
docs/moodle-export-v2/S2_COMPONENT_SCO_MAPPING.md
docs/moodle-export-v2/S2_MICRO_ACTIVITY_POLICY.md
docs/moodle-export-v2/S2_TEST_REPORT.md
docs/moodle-export-v2/S2_REPORT.md
docs/moodle-export-v2/S2_MANIFEST.json
```

## Package identifier rule

```text
FLW_<WorldCode>_U###_SCORM12
```

Example:

```text
FLW_REW_U023_SCORM12
```

## Unit SCORM activity key rule

```text
UnitID: REW-U023
Unit SCORM ActivityID: REW-U023-UNITSCORM
Future cmidnumber: FLW_REW_U023_UNITSCORM
```

## SCO identifier rule

```text
FLW_<WorldCode>_U###_<ComponentKey>
```

Examples:

```text
FLW_REW_U023_L01
FLW_REW_U023_VOCAB
FLW_REW_U023_WATCH
FLW_REW_U023_PROJECT
FLW_REW_U023_RESULT
```

## Components tracked as SCO

S2 tracks substantial detected components as SCOs:

- vocabulary;
- lessons;
- watch/video;
- project;
- result/progress/checkpoint;
- other stable substantial source sections.

The whole-unit SCO remains optional/fallback, not the normal Moodle-targeted identity model.

## Micro-activity policy

Micro-activities are mapped under their parent component:

```text
trackAsSeparateSco = false
```

They do not become question/card/item-level SCOs.

## Tests run

| Check | Result |
|---|---|
| Pre-S2 smoke baseline | PASS |
| Python compile checks | PASS |
| Existing + S1 + S2 smoke suite | PASS |
| Node syntax check | PASS |
| PHP syntax check | PASS |

## Test results

All required S2 cases passed. Details are in `S2_TEST_REPORT.md`.

## Regressions

No regressions detected by the smoke suite.

Intentional S2 compatibility change:

- The UI `Identifier` value is preserved as `requestedIdentifier`, but the SCORM manifest uses the stable FLW package identifier.

## Risks

1. Source lessons without stable IDs still require a generated fallback. Reports mark these as `generated_position_fallback`.
2. S2 does not implement S2B SCO-to-SCO learner navigation or Moodle player switching.
3. S2 does not replace the old Moodle Unit→Course importer.
4. Real Moodle tracking preservation still requires later import/update tests after Moodle dataroot permission is fixed.

## GO / NO-GO for S2B

```text
GO for S2B when requested.
NO-GO for real Moodle update/tracking claims until S2B/S5 real Moodle tests are performed.
```

STOP after Gate S2.
