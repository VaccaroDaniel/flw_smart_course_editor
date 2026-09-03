# S2B Resume Contract

Created: 2026-08-23

## Stable resume identity

The SCORM runtime now records the active FLW component using stable identity:

```text
cmi.core.lesson_location = REW-U023-L04
```

It also writes bounded versioned suspend data:

```json
{
  "schemaVersion": 1,
  "lastComponentId": "REW-U023-L04"
}
```

The payload is intentionally small. It does not store large learner history, C-UP-KP state, or adaptive-learning state.

## Runtime functions added

`assets/scorm/scorm_api.js` now exposes:

```text
FLWScormInitialize()
FLWScormGetValue(element)
FLWScormSetValue(element, value)
FLWScormCommit()
FLWScormComplete(score)
FLWScormRecordComponent(componentId)
FLWScormReadSuspendData()
FLWScormFinish()
```

The runtime also records `cmi.core.session_time` on commit/finish.

## Resume fallback policy

When a stored component ID is consumed by future Moodle-side launch logic, fallback must resolve safely:

1. same stable component ID if available and accessible;
2. nearest valid current component according to FLW policy;
3. first incomplete available component;
4. Unit start/overview fallback.

S2B does not implement adaptive learning or a new external state store.

## Current verification status

Static/export checks confirm:

- every component page receives its own `componentId`;
- `lesson_location` and `suspend_data` writes are present in the SCORM runtime;
- reorder tests preserve stable component IDs.

Real Moodle relaunch/resume could not be verified because Moodle failed importing the SCORM package into its file pool during the controlled integration check. Resume is therefore implemented at the package/runtime contract level, but not fully player-verified.

