# S7B World Stage Maps

Gate: S7B — Seven-world deterministic deployment-stage maps  
Created: 2026-08-24

## Rule source

The authoritative map is:

```text
flw_moodle_course_map.json
```

The resolver preserves fine-grained `sourceStage` while using the major `deploymentStageCode` for Moodle Stage Course grouping.

Example:

```text
sourceStage: B1.3
deploymentStageCode: B1
```

## Adventure English World

Source: Unit metadata plus checkpoint course-map rules.

| Stage | Units |
|---|---|
| Pre-A1 | U001-U012 |
| A1 | U013-U030 |
| A2 | U031-U048 |
| B1 | U049-U072 |

## Real English World

Source: already-approved frozen REW mapping.

| Stage | Units |
|---|---|
| A1 | U001-U018 |
| A2 | U019-U036 |
| B1 | U037-U060 |
| B2 | U061-U084 |
| C1 | U085-U108 |

## Russian World

Source: `CEFR_KP_map.md` in packages plus S7B course-map rules.

| Stage | Units |
|---|---|
| A1 | U001-U024 |
| A2 | U025-U048 |
| B1 | U049-U088 |
| B2 | U089-U096 |
| C1 | U097-U120 |

Note: RUW-U073-U088 remain sourceStage `B1.3`; they now deploy to B1.

## Chinese World

Source: package title/folder/checkpoint/README/package-integrity metadata plus S7B course-map rules. U134 is extra and outside the current 132-Unit production scope.

| Stage | Units |
|---|---|
| A1 | U001-U030 |
| A2 | U031-U060 |
| B1 | U061-U084 |
| B2 | U085-U108 |
| C1 | U109-U132 |

## German World

Source: package filename CEFR tokens plus S7B course-map rules.

| Stage | Units |
|---|---|
| A1 | U001-U012 |
| A2 | U013-U024 |
| B1 | U025-U036 |
| B2 | U037-U048 |
| C1 | U049-U060 |

German U061-U072 are intentionally ignored for the current production scope, so no C2 or later rule was fabricated.

## Japanese World

Source: `manifest.json` where present, otherwise package filename CEFR tokens, plus S7B course-map rules.

| Stage | Units |
|---|---|
| A1 | U001-U012 |
| A2 | U013-U024 |
| B1 | U025-U036 |
| B2 | U037-U048 |
| C1 | U049-U060 |

## French World

Source: package filename CEFR tokens plus S7B course-map rules.

| Stage | Units |
|---|---|
| A1 | U001-U012 |
| A2 | U013-U024 |
| B1 | U025-U036 |
| B2 | U037-U048 |

## Final map validation

```text
Stage unresolved: 0
Stage conflict: 0
World unresolved: 0
Invalid config: 0
```
