# S6 Import Mode Semantics

Gate: S6 — Single Import Modes  
Created: 2026-08-24

## Overwrite

Visible label:

```text
Overwrite
```

Meaning:

```text
Synchronize this FLW Unit with its canonical Moodle Stage Course, Unit Section, and current Unit SCORM.
```

Overwrite is an upsert:

- missing Stage Course -> create Stage Course;
- missing Unit Section -> create Unit Section;
- missing Unit SCORM -> create Unit SCORM;
- compatible changed package -> update SCORM in-place;
- unchanged package -> return `UNCHANGED`;
- unsafe package update -> supersede, preserving historical SCORM/tracking.

Overwrite does not clear the Stage Course, delete neighboring Units, or delete attempt-bearing historical SCORMs.

## Add New Unit

Visible label:

```text
Add New Unit
```

Meaning:

```text
Deploy this Unit as a new canonical FLW Unit only if its UnitID is not already deployed.
```

If the UnitID already exists in the canonical Stage Course, S6 returns:

```text
UNIT_ALREADY_EXISTS
```

The UI/report tells the user:

```text
Use Copy Unit in the Smart Course Editor first, then import the copied Unit.
```

S6 does not create artificial Moodle-only Unit IDs such as `U023-copy`.

## Batch note

S6 does not implement full batch production import changes. Batch controls remain available but are not redesigned in this gate.

