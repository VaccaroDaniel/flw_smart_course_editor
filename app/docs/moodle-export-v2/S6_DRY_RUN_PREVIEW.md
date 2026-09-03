# S6 Dry Run / Preview

Gate: S6 — Dry Run Preview  
Created: 2026-08-24

## Behavior

Single import preview runs the same resolver sequence as real import:

```text
S3 Stage Course resolver
S4 Unit Section resolver
S5 Unit SCORM resolver
```

Preview/dry-run does not:

- create courses;
- create sections;
- upload packages;
- update SCORM;
- change mappings.

S6 fixed a pre-existing dry-run issue where reused Stage Courses could still write the local stage-course map.

## Preview-state hash

S6 reports:

```text
previewStateHash
```

The real import can send this hash back as `--expect-preview-state`. The backend reruns resolution before mutation and returns:

```text
PREVIEW_STALE
```

if the current Moodle destination state no longer matches the preview.

## Verified examples

REW-U023 overwrite preview:

```text
REUSE_STAGE_COURSE -> UPDATE_SECTION -> UPDATE_SCORM
```

After S6 content-hash backfill and repeat export:

```text
REUSE_STAGE_COURSE -> REUSE_SECTION -> UNCHANGED
```

REW-U001 Add New Unit preview:

```text
CREATE_STAGE_COURSE -> CREATE_SECTION -> CREATE_SCORM
```

Wrong preview hash:

```text
PREVIEW_STALE / BLOCKED
```

