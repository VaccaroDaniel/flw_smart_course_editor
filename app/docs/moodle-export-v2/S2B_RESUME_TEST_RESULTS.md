# S2B Resume Test Results

Created: 2026-08-23
Updated: 2026-08-23

## Status

```text
PASS
```

Resume was verified in Moodle's real browser/player without certificate bypass.

## Resume contract verified

The runtime records:

```text
cmi.core.lesson_location = <stable ComponentID>
cmi.suspend_data = {"schemaVersion":1,"lastComponentId":"<stable ComponentID>"}
```

Final browser run:

```text
Lesson-list jump: REW-U023-L02 → REW-U023-WATCH
Normal Moodle activity relaunch returned to: REW-U023-WATCH
Relaunch URL: https://main.flw.com/mod/scorm/player.php?a=67&scoid=699&currentorg=ORG1&mode=&attempt=1
```

Final tracking row:

```text
scoid 699 / FLW_REW_U023_WATCH
cmi.core.lesson_location = REW-U023-WATCH
cmi.suspend_data = {"schemaVersion":1,"lastComponentId":"REW-U023-WATCH"}
```

## Moodle launch behavior handled

Installed Moodle `mod/scorm/view.php` normally launches the last incomplete SCO. S2B now adds an FLW-side resume bridge:

```text
Moodle normal activity launch
→ Moodle selected SCO
→ FLW reads scoped last stable ComponentID
→ FLW redirects to the matching Moodle scoid before SCORM init writes tracking
```

The resume key is scoped by package id, Moodle SCORM id, and attempt. Direct `cm=...` launches also resolve the SCORM id from the framed `loadSCO.php?a=...` URL.

## Reorder verification

Reordered fixture:

```text
Course id: 199
User id: 23
cmid: 2093
scorm id: 70
Package: C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui\verification_exports\s2b_closure_fixed\REW-U023-S2B-Browser-Verification-Unit-Reordered-SCORM12-20260823_234244.zip
```

Reordered lesson order:

```text
REW-U023-L01
REW-U023-L03
REW-U023-L02
REW-U023-L04
REW-U023-L05
REW-U023-L06
REW-U023-L07
```

Result:

```text
Direct launch current ComponentID: REW-U023-L02
Normal activity relaunch current ComponentID: REW-U023-L02
Relaunch URL: https://main.flw.com/mod/scorm/player.php?a=70&scoid=727&currentorg=ORG1&mode=&attempt=1
```

Tracking confirmed `scoid 727 / FLW_REW_U023_L02` stored the stable L02 resume data after reordering.
