# S2 SCORM Identity

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## Package identifier rule

```text
FLW_<WorldCode>_U###_SCORM12
```

Example:

```text
FLW_REW_U023_SCORM12
```

The manifest package identifier no longer uses timestamps, random UUIDs, Moodle numeric IDs, section positions, or title slugs.

## Unit SCORM activity key rule

S2 prepares package-side metadata for later Moodle import:

```text
UnitID: REW-U023
Unit SCORM ActivityID: REW-U023-UNITSCORM
Future cmidnumber: FLW_REW_U023_UNITSCORM
```

S2 does not create or update Moodle modules.

## SCO identifier rule

```text
FLW_<WorldCode>_U###_<ComponentKey>
```

Examples:

```text
FLW_REW_U023_L01
FLW_REW_U023_L02
FLW_REW_U023_VOCAB
FLW_REW_U023_WATCH
FLW_REW_U023_PROJECT
FLW_REW_U023_RESULT
```

These values are used as SCORM item identifiers. Resource identifiers append `_RES`.

## Title changes

Titles are display metadata only. When a lesson title changes, the component ID and SCO identifier remain the same if the stable lesson/source ID remains the same.

## Reordering

Display order is recorded as `displayOrder`, but `displayOrderIsCanonical` is false. Reordering changes organization order but not component/SCO identity.

## Hashes

S2 separates identity from content revision:

```text
scormManifestIdentifier
packageSha256
packageContentSha256
```

`packageSha256` hashes the ZIP file bytes.

`packageContentSha256` hashes the staged package file paths and contents in deterministic order.

A content hash change does not create a new UnitID or SCO identifier.

## UI identifier field

The report preserves the UI value as `requestedIdentifier`, but S2 uses the stable FLW package identifier for the Moodle-targeted manifest identity.
