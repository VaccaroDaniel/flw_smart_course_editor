# S1 Deployment Stage Resolution

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## Resolver

Implemented in:

```text
server.py
→ resolve_deployment_target()
```

Resolution inputs:

- detected source root / world;
- unit number;
- `index.html` / `window.UNIT_DATA` metadata;
- existing package filename CEFR token only for worlds whose S1 policy allows it;
- `flw_moodle_course_map.json`.

## Precedence

The resolver evaluates:

1. canonical World + Unit course-map rule;
2. explicit deployment-stage metadata if present;
3. configured major-CEFR normalization when unambiguous;
4. otherwise unresolved.

If multiple available sources normalize to different deployment stages, S1 returns:

```text
STAGE_CONFLICT
```

The resolver does not silently pick a winner.

## Source stage vs deployment stage

S1 separates:

```text
sourceStage
deploymentStageCode
```

Example:

```text
sourceStage = A2.2
deploymentStageCode = A2
```

This lets FLW preserve source/fine-grained curriculum metadata while planning Moodle courses at deployment-stage boundaries.

## Supported preflight statuses

```text
RESOLVED
STAGE_UNRESOLVED
STAGE_CONFLICT
WORLD_UNRESOLVED
INVALID_CONFIG
SOURCE_ROOT_NOT_FOUND
```

`SOURCE_ROOT_NOT_FOUND` is used in configured source-root status, especially for Spanish when no local source root exists.

## Real import block

For real Moodle import only, `server.py` blocks before invoking the old PHP importer if any planned/exported manifest item has:

```text
STAGE_UNRESOLVED
STAGE_CONFLICT
WORLD_UNRESOLVED
INVALID_CONFIG
SOURCE_ROOT_NOT_FOUND
```

Dry-run and preview can still show these statuses.

This keeps S1 non-destructive and prevents the old Unit→Course importer from silently importing units with unresolved v8 deployment metadata.
