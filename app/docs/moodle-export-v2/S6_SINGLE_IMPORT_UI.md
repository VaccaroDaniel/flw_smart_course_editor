# S6 Single Import UI

Gate: S6 — Single-Unit Moodle Export UI  
Created: 2026-08-24

## UI changes

The SCORM export panel now includes:

- single import mode label `Add New Unit`;
- architecture help text showing:

```text
FLW World + Stage -> Moodle Stage Course -> FLW Unit Section -> Unit SCORM
```

- `Preview Moodle destination` button;
- `Build + deploy Unit SCORM` flow that first runs preview/dry-run, then asks for confirmation.

## Preview display

The single preview/result output now presents:

- FLW Unit:
  - world;
  - source stage;
  - deployment stage;
  - UnitID;
  - unit title.
- Moodle Destination:
  - Stage Course;
  - Course key;
  - Unit Section;
  - Unit SCORM.
- Planned/completed actions:
  - Course action;
  - Section action;
  - SCORM action;
  - history safety;
  - manual Moodle content preservation;
  - legacy warning if present.

The normal UI avoids learner-facing technical SCO terminology. Internal identifiers remain available in JSON reports for diagnostics.

## Confirmation

Real deploy uses the dry-run result as the confirmation summary. The real request sends the preview-state hash back to the backend so changed Moodle state can be detected before mutation.

