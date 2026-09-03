# S2B Real SCO Tracking Results

Created: 2026-08-23
Updated: 2026-08-23

## Status

```text
PASS
```

Real Moodle browser/player navigation and Moodle DB tracking isolation passed against `https://main.flw.com` with normal certificate validation.

## Final tracking fixture

```text
Course id: 196
User id: 20
cmid: 2087
scorm id: 67
Attempt id: 57
Tracking storage: scorm_attempt + scorm_scoes_value + scorm_element
```

Moodle 5.1 stores SCORM tracking in `scorm_scoes_value`; `cmi.core.session_time` submitted by the runtime is reflected by Moodle as accumulated `cmi.core.total_time`.

## Browser/player navigation verified

| Check | Result |
|---|---|
| Normal Moodle SCORM player launch | PASS |
| FLW Next: Lesson 1 → Lesson 2 | PASS (`scoid=693`) |
| FLW Previous: Lesson 3 → Lesson 2 | PASS (`scoid=693`) |
| FLW lesson-list jump: Lesson 2 → Watch | PASS (`scoid=699`) |
| Malformed `currentorg` regression | PASS, no `%C2%A4torg` / `¤torg` |
| Learner UI exposes technical SCO terms | PASS, not exposed |

## Per-SCO tracking evidence

```text
Vocabulary: cmi.core.lesson_location=REW-U023-VOCAB, status=completed, score=100, total_time=00:00:03.00
Lesson 1:   cmi.core.lesson_location=REW-U023-L01, status=completed, score=100, total_time=00:00:03.00
Lesson 2:   cmi.core.lesson_location=REW-U023-L02, status=completed, score=100, total_time=00:00:05.00
Lesson 3:   cmi.core.lesson_location=REW-U023-L03, status=completed, score=100, total_time=00:00:03.00
Watch:      cmi.core.lesson_location=REW-U023-WATCH, status=completed, score=100, total_time=00:00:04.00
```

Each tracked SCO stored matching `cmi.suspend_data`:

```json
{"schemaVersion":1,"lastComponentId":"<matching stable ComponentID>"}
```

Final last location/suspend-data write:

```text
scoid: 699
element: cmi.suspend_data
value: {"schemaVersion":1,"lastComponentId":"REW-U023-WATCH"}
```

The transient Moodle resume landing SCO wrote only `x.start.time`; it did not overwrite `lesson_location`, `lesson_status`, `score.raw`, or `suspend_data`.

## Locked component tracking

Locked fixture:

```text
Course id: 197
User id: 21
cmid: 2089
scorm id: 68
Locked component: REW-U023-L05 / scoid 707
```

Result:

```text
Lesson 5 was marked aria-disabled=true and “Locked”.
Clicking it kept the player on REW-U023-L04 / scoid 706.
Lesson 5 had no tracking rows after the blocked click.
```
