# S2B Navigation Architecture

Created: 2026-08-23

Gate: S2B — Unified FLW Navigation + Resume + Correct Moodle SCO Tracking

## Status

```text
CONDITIONAL
```

The editor now exports one compact FLW learner navigator inside each component-level SCORM launch page. This preserves the S2 structure:

```text
1 FLW Unit = 1 SCORM 1.2 package
substantial lesson/component = 1 SCO
micro-activities remain inside parent SCO
```

## Learner-facing model

The learner-facing in-unit model is now:

```text
Moodle Course Roadmap
→ FLW Unit activity
→ FLW compact lesson/component navigator
→ Current lesson/component
```

The normal learner UI uses labels such as:

- Vocabulary
- Lesson 1
- Lesson 2
- Watch
- Project
- Result

It does not display Moodle tracking terminology such as SCO identifiers, Moodle numeric ids, manifest item ids, or cmids.

## Export implementation

`server.py` injects the navigator after all component launch files are known, so the navigator order follows the final S2 `componentMappings` order.

Export report fields added:

```json
{
  "flwNavigatorEnabled": true,
  "flwNavigatorVersion": 4,
  "flwNavigatorInjectedCount": 10,
  "flwNavigatorPrimary": true,
  "resumeStorage": ["cmi.core.lesson_location", "cmi.suspend_data"],
  "moodleScoLaunchMechanism": "/mod/scorm/player.php?scoid=<moodle scorm_scoes.id>"
}
```

Each component page receives:

- a per-page `window.FLW_SCORM_CONFIG` containing the current stable `componentId`;
- a JSON navigator config containing all components;
- one compact `<nav id="flw-unit-navigator">` created at runtime.

## Component state model

S2B supports these display states:

```text
Completed
Current
Available
Locked
```

Current exported packages default components to `Available` unless a component is the current page. `Locked` is supported through `locked: true` or `availability: "locked"` in the navigator config, but S2B does not invent adaptive rules.

Completion display is conservative:

- the current component is marked completed only after the SCORM runtime reports `completed` or `passed`;
- a small browser-side UI cache can remember completed labels during the same browser context;
- Moodle SCORM tracking remains the authority.

## Previous / Next / list behavior

Previous and Next use the FLW component order from `componentMappings`.

Navigator v4 renders Previous, current/total progress, current title, lesson-list control, and Next in one compact row. The list is a bounded overlay rather than an in-flow panel. Adjacent locked components disable Previous/Next, while locked list entries remain visible with learner-readable status and cannot launch.

For local/no-SCORM-API navigation, v4 prefetches adjacent component pages and applies a guarded cross-document transition. The incoming body is not exposed until synchronous component filtering and navigator rendering complete. Moodle navigation continues to use the existing player URL and tracking flow without this local-page delay.

List jumps use stable component identity internally:

```text
ComponentID → SCO identifier → Moodle numeric scoid → Moodle player launch URL
```

Local/offline preview may use relative component launch files when no SCORM API is present. When a SCORM API is present but Moodle launch data cannot be resolved, the navigator fails safe and does not direct-link to another component file.
