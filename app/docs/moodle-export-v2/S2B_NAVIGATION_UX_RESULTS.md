# S2B Navigation UX Results

Created: 2026-08-23
Updated: 2026-08-25

## Status

```text
PASS
```

The FLW navigator was verified in Moodle's normal SCORM player with the trusted HTTPS URL.

## Browser/player UX verified

| UX check | Result |
|---|---|
| Moodle opens without certificate warning | PASS |
| SCORM activity launches through Moodle player | PASS |
| FLW compact navigator visible in SCO iframe | PASS |
| FLW Next switches active Moodle SCO | PASS |
| FLW Previous switches active Moodle SCO | PASS |
| FLW list jump switches active Moodle SCO | PASS |
| Moodle native SCORM TOC/tree/nav panel hidden | PASS |
| Player iframe remains visible | PASS |
| Learner UI exposes `SCO`, `scoid`, `cmid`, or manifest terms | PASS, not exposed |
| Locked component cannot be entered | PASS |

Final native-control visibility:

```json
{
  "iframeVisible": true,
  "scormNavPanelVisible": false,
  "scormTocVisible": false,
  "scormTreeVisible": false
}
```

Final learner navigator text sample:

```text
← Previous 4 of 13 Lesson 1 Lessons Next →
```

Navigator v4 keeps that primary bar to one 50–52px row. The lesson/component list opens as a bounded overlay, automatically brings the current item into view, closes on outside click or Escape, and becomes a single scrollable column at narrow widths.

## Locked state

Locked test result:

```text
Component: REW-U023-L05
Visible label/status: Lesson 5 ◇ Locked
aria-disabled: true
Click result: stayed on REW-U023-L04 / scoid 706
Message: Lesson 5 is locked.
```

## Accessibility/static UX checks retained

The smoke suite still verifies:

- semantic `<nav aria-label="Unit lesson navigation">`;
- native buttons for Previous/Next and component choices;
- native `<details>/<summary>` expandable list;
- destination-aware accessible names for Previous/Next;
- `aria-expanded` and `aria-controls` on the lesson-list control;
- visible focus styling;
- textual status labels, not color alone;
- `aria-current="page"` for current component;
- `aria-disabled="true"` for locked components;
- responsive single-row narrow layout with 40px touch targets;
- independently scrollable lesson-list overlay.

## Navigator v4 local export recheck

A fresh 13-component Chinese Unit 2 export was checked in the browser at 1280×720 and 390×780. Previous/Next local navigation, current/total progress, Escape close/focus return, overlay containment, and narrow-width scrolling passed. Moodle player switching behavior remains covered by the S2B Moodle checks above; the v4 changes do not alter that launch mechanism.

The local Lesson 1 → Lesson 2 transition was additionally checked for the reported page flash. Adjacent component HTML is prefetched, the outgoing page uses a short transition, and the incoming page remains visually guarded until its component filter and navigator are ready. No other lesson content was visible before or after the transition. This behavior is limited to local/no-SCORM-API navigation and does not change Moodle player SCO switching.
