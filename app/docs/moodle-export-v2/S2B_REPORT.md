# S2B Report

Created: 2026-08-23
Updated: 2026-08-23

Gate: S2B — Unified FLW Navigation + Resume + Correct Moodle SCO Tracking

## S2B STATUS

```text
PASS
```

## GO / NO-GO FOR S3

```text
GO
```

S3 was not started.

## Summary

The previously blocked browser/player verification was rerun against the normal trusted Moodle HTTPS URL. Moodle opened without a certificate warning, no TLS/certificate bypass was used, and the SCORM activity launched through Moodle's normal player.

All S2B browser/player checks now pass:

- FLW Next: Lesson 1 → Lesson 2 switches Moodle active SCO correctly.
- FLW Previous: Lesson 3 → Lesson 2 switches Moodle active SCO correctly.
- FLW lesson-list jump: Lesson 2 → Watch activates and tracks Watch correctly.
- Per-SCO tracking writes are isolated to the correct Moodle `scorm_scoes.id`.
- Resume returns to the last meaningful stable ComponentID.
- Reordered components preserve stable ComponentIDs and resume still works.
- Locked components cannot be entered through FLW navigation.
- Moodle native SCORM TOC/tree/nav panel is hidden while the player iframe remains visible.
- Learner UI does not expose technical SCO terminology.
- Existing Smart Course Editor regression tests remain PASS.

## Moodle version

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
mod_scorm version 2025100601
wwwroot = https://main.flw.com
```

## Main verification fixture

```text
Package: C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui\verification_exports\s2b_closure_fixed\REW-U023-S2B-Browser-Verification-Unit-SCORM12-20260823_233429.zip
Package SHA-256: 97b5ed63ac77aeb23e1a1ad1903a73ff64bf337b7174273ada69b1a134427772
Content SHA-256: b5b74572112d13a59fc9b576b414628eb0e6ebab4b7fb517b851c48a8545b827
Temporary course id: 196
Temporary user id: 20
cmid: 2087
scorm id: 67
Attempt id: 57
```

## Additional focused fixtures

```text
Locked-component fixture:
  course id: 197
  user id: 21
  cmid: 2089
  scorm id: 68
  locked component: REW-U023-L05 / scoid 707

Reorder fixture:
  course id: 199
  user id: 23
  cmid: 2093
  scorm id: 70
  package: C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui\verification_exports\s2b_closure_fixed\REW-U023-S2B-Browser-Verification-Unit-Reordered-SCORM12-20260823_234244.zip
```

## Browser/player evidence

```text
Trusted URL: https://main.flw.com
Certificate warning: none
Moodle player launch: PASS
Normal launch URL: https://main.flw.com/mod/scorm/player.php?a=67&currentorg=ORG1&scoid=691
FLW Next result: https://main.flw.com/mod/scorm/player.php?a=67&scoid=693&currentorg=&mode=&attempt=1
FLW Previous result: https://main.flw.com/mod/scorm/player.php?a=67&scoid=693&currentorg=&mode=&attempt=1
FLW list jump result: https://main.flw.com/mod/scorm/player.php?a=67&scoid=699&currentorg=&mode=&attempt=1
Resume result: https://main.flw.com/mod/scorm/player.php?a=67&scoid=699&currentorg=ORG1&mode=&attempt=1
```

## Tracking evidence

Moodle 5.1 tracking storage:

```text
scorm_attempt
scorm_scoes_value
scorm_element
```

Final tracked rows:

```text
Vocabulary: FLW_REW_U023_VOCAB / scoid 691 / lesson_location REW-U023-VOCAB / completed / score 100
Lesson 1:   FLW_REW_U023_L01   / scoid 692 / lesson_location REW-U023-L01   / completed / score 100
Lesson 2:   FLW_REW_U023_L02   / scoid 693 / lesson_location REW-U023-L02   / completed / score 100
Lesson 3:   FLW_REW_U023_L03   / scoid 694 / lesson_location REW-U023-L03   / completed / score 100
Watch:      FLW_REW_U023_WATCH / scoid 699 / lesson_location REW-U023-WATCH / completed / score 100
```

Moodle stores submitted `cmi.core.session_time` as accumulated `cmi.core.total_time` in this Moodle 5.1 schema.

## Bugs fixed during S2B closure

- Top-nav hiding was accidentally hiding the injected FLW navigator; `body > nav` is now scoped as `body > nav:not(#flw-unit-navigator)`.
- Moodle adlnav URL parsing decoded `&currentorg` as `¤torg`; URL decoding now preserves Moodle query strings.
- Moodle adlnav object parsing could match the parent organization SCO; the resolver now extracts the exact JSON object around the target stable identifier.
- Moodle normal launch chooses the last incomplete SCO; the FLW resume bridge now redirects to the last stable ComponentID before SCORM init writes tracking.
- Resume state is scoped by package id, Moodle SCORM id, and attempt, including direct `cm=...` launches.
- Moodle native SCORM tree/nav controls are hidden without hiding the player iframe.
- The Moodle 5.1 tracking snapshot helper now supports `scorm_scoes_value` + `scorm_element`.
- The Moodle fixture helper now prewarms both the SCORM ZIP and ZIP-entry file-pool hashes for this Windows Moodle install.

## Tests run

```text
python -m py_compile server.py scripts\smoke_test.py
python scripts\smoke_test.py
node --check static\app.js
php -l scripts\s2b_moodle_browser_fixture.php
php -l scripts\s2b_moodle_browser_tracking_snapshot.php
php -l scripts\s2b_moodle_browser_cleanup.php
Moodle real package import via scripts\s2b_moodle_browser_fixture.php
Moodle real tracking snapshots via scripts\s2b_moodle_browser_tracking_snapshot.php
Controlled browser Moodle/player click-through tests
```

Final smoke suite:

```text
missingRefs PASS
importAsset PASS
replaceReference PASS
restoreBackup PASS
scormPreview PASS
topNavExportOption PASS
directFlwManifest PASS
batchFlwPlanning PASS
s1DeploymentMetadata PASS
s2bNavigatorRuntimeJs PASS
s2ScormIdentity PASS
copyFolder PASS
copyZip PASS
visualRuntimeJs PASS
frontendJs PASS
directFlwUi PASS
```

## Files changed

```text
server.py
scripts/smoke_test.py
scripts/s2b_moodle_browser_fixture.php
scripts/s2b_moodle_browser_tracking_snapshot.php
scripts/s2b_moodle_browser_cleanup.php
docs/moodle-export-v2/S2B_REAL_MOODLE_IMPORT_TEST.md
docs/moodle-export-v2/S2B_REAL_SCO_TRACKING_RESULTS.md
docs/moodle-export-v2/S2B_RESUME_TEST_RESULTS.md
docs/moodle-export-v2/S2B_NAVIGATION_UX_RESULTS.md
docs/moodle-export-v2/S2B_REPORT.md
docs/moodle-export-v2/S2B_MANIFEST.json
```

## Remaining risks / notes

1. Verification helper file-pool prewarm remains a local Windows Moodle workaround; Moodle's normal web upload path should be watched for the same file-pool rename issue.
2. The S2B resume bridge is intentionally scoped to current architecture and should be revisited during the later frozen target architecture work.
3. Temporary Moodle fixtures were used for verification and should not be treated as production course imports.

STOP after Gate S2B.
