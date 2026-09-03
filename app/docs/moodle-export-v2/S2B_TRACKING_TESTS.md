# S2B Tracking Tests

Created: 2026-08-23

## Static/editor tests run

Command:

```text
python scripts\smoke_test.py
```

Result:

```json
{
  "missingRefs": "PASS",
  "importAsset": "PASS",
  "replaceReference": "PASS",
  "restoreBackup": "PASS",
  "scormPreview": "PASS",
  "topNavExportOption": "PASS",
  "directFlwManifest": "PASS",
  "batchFlwPlanning": "PASS",
  "s1DeploymentMetadata": "PASS",
  "s2bNavigatorRuntimeJs": "PASS",
  "s2ScormIdentity": "PASS",
  "copyFolder": "PASS",
  "copyZip": "PASS",
  "visualRuntimeJs": "PASS",
  "frontendJs": "PASS",
  "directFlwUi": "PASS"
}
```

S2B smoke assertions include:

- FLW navigator injected into every component launch page;
- navigator runtime JavaScript passes Node syntax check;
- learner-visible text does not contain `SCO`;
- stable current component ID is present per launch page;
- SCORM runtime contains `lesson_location`, `suspend_data`, and `session_time`;
- Moodle importer settings disable/minimize native SCORM learner navigation.

## Syntax checks run

Command:

```text
python -m py_compile server.py moodle_import_support.py scorm_gui_support.py scripts\smoke_test.py scripts\pilot_export_scorm.py scripts\verify_scorm_display_consistency.py
node --check static\app.js
php -l scripts\import_scorm_pilot_to_moodle.php
php -l scripts\s2b_moodle_tracking_check.php
```

Result:

```text
PASS
```

## Real Moodle check attempted

Fresh package created:

```text
C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui\verification_exports\s2b_moodle\REW-U023-S2B-Moodle-Tracking-Unit-SCORM12-20260823_212928.zip
```

Moodle bootstrap:

```text
bootstrapped=5.1.5 (Build: 20260608)
```

Moodle import/tracking check command:

```text
D:\Dev\MoodleWindowsInstaller-latest-501\server\php\php.exe scripts\s2b_moodle_tracking_check.php --moodle-config=D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\public\config.php --zip=<fresh S2B package>
```

Result:

```json
{
  "status": "FAIL",
  "createdCourseId": 177,
  "createdCourseDeleted": true,
  "moodleRelease": "5.1.5 (Build: 20260608)",
  "checks": [],
  "error": "Cannot create local file pool file. Please verify permissions in dataroot and available disk space."
}
```

Follow-up PHP writability probe:

```text
dataroot=D:\Dev\MoodleWindowsInstaller-latest-501\server\moodledata
is_writable=yes
filedir_writable=yes
```

## Mandatory test matrix

| Test | Result | Evidence |
|---|---|---|
| A — Lesson 1 → Lesson 2 tracking isolation | BLOCKED | Moodle package import failed before SCORM rows were created |
| B — Lesson-list jump to Watch | BLOCKED | Moodle package import failed |
| C — Previous tracking | BLOCKED | Moodle package import failed |
| D — Completion states | STATIC PASS / REAL BLOCKED | Navigator does not mark completion without SCORM status; real Moodle blocked |
| E — Resume | STATIC PASS / REAL BLOCKED | Runtime writes stable `lesson_location` and `suspend_data`; relaunch blocked |
| F — Stable resume identity after reorder | STATIC PASS / REAL BLOCKED | S2 smoke confirms stable IDs after reorder; real relaunch blocked |
| G — Missing component fallback | DESIGN ONLY / REAL BLOCKED | Fallback policy documented; real relaunch blocked |
| H — Locked component | STATIC PASS / REAL BLOCKED | Navigator supports locked state and blocks selection; no current FLW lock data source in S2B |
| I — Native Moodle navigation hidden/minimized | CONFIGURED / UI BLOCKED | Importer sets `skipview`, `hidetoc`, `nav`, `displaycoursestructure`, `displayattemptstatus`; UI import blocked |
| J — Learner technical terminology absent | STATIC PASS | Smoke strips scripts/styles and asserts learner-visible text has no `SCO` |
| K — Mobile responsive | STATIC PASS / MANUAL BLOCKED | CSS has narrow viewport layout; browser Moodle test blocked |
| L — Existing editor regression | PASS | `scripts\smoke_test.py` passed |

## Conclusion

S2B implementation and static regression checks pass. The gate cannot pass because real Moodle import/player/tracking tests are blocked by Moodle file-pool storage failure.

