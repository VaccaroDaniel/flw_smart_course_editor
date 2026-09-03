# S7 Grouping Rules

Gate: S7 — Batch grouping by World + Deployment Stage  
Created: 2026-08-24

## Root selection

S7 distinguishes two source-root cases:

- Top SmartCourses root: discover all configured language roots below it.
- Direct language root: select only that language root.

This fixes the earlier behavior where choosing `02-Real` could accidentally discover sibling languages.

## All Available Units

When `All Available Units` is selected from the top SmartCourses root, S7 selects every available valid Unit in every configured language root.

Expected validation counts are used only for reporting. Missing source Units are never fabricated.

## Range selection

When a range is selected from a direct language root, S7 applies the range to that language only.

Example verified:

```text
D:\WinPro.Delta\Projects\SmartCourses\02-Real
U019-U036
-> 18 Real Units
-> 1 Stage group: REW:A2
```

When a range is selected from the top SmartCourses root, S7 applies the range across all discovered language roots.

## Target grouping

Each Unit is enriched with:

- `worldCode`
- `deploymentStageCode`
- `unitId`
- `unitSequence`
- `courseExternalKey`
- `unitExternalKey`
- `scormActivityExternalKey`

Groups are ordered by:

1. configured language order;
2. Stage order: Pre-A1, A1, A2, B1, B2, C1, C2;
3. Unit sequence.

## Blockers

A Unit with no resolvable Deployment Stage becomes:

```text
STAGE_UNRESOLVED
```

It is included in preview/report output but blocks real import for that Unit.

## Verified examples

Real U019-U036:

```text
REW:A2 -> FLW_REW_A2 -> REW-U019 ... REW-U036
```

Real U017-U020:

```text
REW:A1 -> FLW_REW_A1 -> REW-U017, REW-U018
REW:A2 -> FLW_REW_A2 -> REW-U019, REW-U020
```

Top SmartCourses U001:

```text
Adventure, Real, Russian, Chinese, German, Japanese, French selected
Spanish reported absent
Russian/Chinese U001 reported as STAGE_UNRESOLVED where applicable
```

