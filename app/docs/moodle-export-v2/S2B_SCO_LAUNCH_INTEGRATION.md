# S2B SCO Launch Integration

Created: 2026-08-23

## Required launch chain

S2B must not navigate directly from one component HTML file to another while running under Moodle, because Moodle would keep associating SCORM API calls with the previously active numeric `scoid`.

The required chain is:

```text
FLW componentId
→ S2 stable SCO identifier
→ Moodle scorm_scoes.id
→ /mod/scorm/player.php?...&scoid=<id>
→ /mod/scorm/loadSCO.php?id=<cmid>&scoid=<id>
→ current SCO iframe
```

## Runtime resolver

The exported FLW navigator carries stable identity:

```json
{
  "componentId": "REW-U023-L02",
  "scoIdentifier": "FLW_REW_U023_L02",
  "launchFile": "scos/lesson-l02.html"
}
```

At runtime it resolves the Moodle numeric target in this order:

1. explicit `moodleScoMap`, if provided by a future Moodle-side integration;
2. parent/top `FLW_MOODLE_SCO_MAP`, if provided by a future Moodle-side integration;
3. Moodle player page serialized `adlnav`, matching by stable `identifier`;
4. local/offline relative launch only when no SCORM API is present.

When a SCORM API is present and no Moodle `scoid` can be resolved, the navigator does not direct-link to another component file. It shows a learner-safe message asking the learner to reload the activity.

## Why this is tracking-safe

Moodle source shows `player.php` validates and stores the active `scoid`, then frames `loadSCO.php` with that same `scoid`. By launching through `player.php`, the next component's SCORM API writes are associated with the next Moodle `scorm_scoes` row.

Direct local file navigation remains only an offline-preview convenience.

## Current limitation

The resolver is implemented and syntax-tested, but a full Moodle browser/player test could not be completed because Moodle failed while importing the package into its file pool. S2B therefore remains `CONDITIONAL`, not `PASS`.

