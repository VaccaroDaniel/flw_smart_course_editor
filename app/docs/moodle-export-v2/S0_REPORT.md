# S0 Report

Created: 2026-08-23

Gate: S0 — Current Implementation Freeze

## S0 status

```text
CONDITIONAL
```

Reason:

- Current editor tests pass.
- Actual Moodle version is known.
- Installed Moodle SCORM source and APIs were inspected.
- Existing FLW/Moodle mapping facilities were classified from source and live DB schema.
- No production editor behavior was changed.
- However, normal Moodle CLI bootstrap currently fails because `$CFG->dataroot is not writable`. This does not prevent S0 documentation, but it will block real Moodle import/tracking/resume tests in later gates until fixed.

## Repository findings

Editor root:

```text
C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui
```

Usable Git working tree:

```text
Not available. `git status` reports this is not a Git repository.
```

Relevant production files:

```text
server.py
moodle_import_support.py
scorm_gui_support.py
README.md
static/app.js
static/index.html
static/style.css
scripts/import_scorm_pilot_to_moodle.php
scripts/smoke_test.py
scripts/pilot_export_scorm.py
scripts/verify_scorm_display_consistency.py
scripts/build_offline_installer.ps1
```

S0 docs created:

```text
docs/moodle-export-v2/S0_CURRENT_IMPLEMENTATION.md
docs/moodle-export-v2/S0_BASELINE_TESTS.md
docs/moodle-export-v2/S0_MOODLE_API_FINDINGS.md
docs/moodle-export-v2/S0_REPORT.md
```

## Tests actually run

| Test/check | Result |
|---|---|
| Python compile checks | PASS |
| Node syntax check on `static/app.js` | PASS |
| PHP syntax check on `scripts/import_scorm_pilot_to_moodle.php` | PASS |
| Existing smoke test `scripts/smoke_test.py` | PASS |

Smoke test PASS modules:

```text
missingRefs
importAsset
replaceReference
restoreBackup
scormPreview
topNavExportOption
directFlwManifest
batchFlwPlanning
copyFolder
copyZip
visualRuntimeJs
frontendJs
directFlwUi
```

## Moodle / SCORM API findings

Installed Moodle:

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
Version 2025100605.00
```

Installed SCORM plugin:

```text
mod_scorm version 2025100601
```

SCORM create API:

```text
add_moduleinfo()
→ scorm_add_instance()
```

SCORM update API:

```text
update module flow
→ scorm_update_instance()
→ scorm_parse()
```

CMID preservation:

- Supported in principle when updating an existing course module instead of deleting/recreating it.
- Must be verified with a real Moodle import/update after dataroot permissions are fixed.

Learner attempt/tracking preservation:

- Moodle tracks by `scorm_attempt` plus `scorm_scoes.id`.
- `scormlib.php` preserves SCO row ids only when manifest `identifier` is stable.
- Removed/renamed SCO identifiers cause Moodle to delete old SCO rows and call `scorm_delete_tracks()`.

SCO launching/switching:

- Moodle player expects/uses `scoid`.
- Player/load flow is `/mod/scorm/player.php` and `/mod/scorm/loadSCO.php`.
- FLW navigation must use Moodle's player/launch mechanism or a verified equivalent so Moodle's active SCO id changes correctly.

Native SCORM TOC/entry controls:

```text
skipview
displaycoursestructure
hidetoc
nav
displayattemptstatus
hidebrowse
popup
auto
autocommit
forcenewattempt
lastattemptlock
```

Current importer defaults are not yet aligned with the frozen target because `hidetoc` falls back to side TOC. This must be changed/tested in later gates, not S0.

## Existing mapping support

Confirmed live DB support:

- FLW/C-UP-KP plugins and tables exist.
- `flwcupkp_object` can map learning-object `externalid` to `courseid`, `unitcode`, `lesson`, `objecttype`, and `cmid`.
- 12 live `flwcupkp_object` rows have cmids.
- `flwcupkp_framework` exists, but current framework rows do not have `courseid`.
- No Unit→Moodle Section marker/table was found.
- `local_flwkp_mappings` exists but currently has zero rows.

Classification:

```text
World+Stage → Moodle Course: partial / not canonical
Unit → Moodle Section: missing
Activity → cmid: partial, through flwcupkp_object
```

## Files/functions that must change later

Do not change during S0. Later gates must focus on:

Python:

- `server.py`
  - `detect_flw_language`
  - `discover_batch_language_roots`
  - `planned_batch_manifest`
  - `direct_flw_manifest`
  - `run_flw_import`
  - `run_flw_course_preview`
  - `preview_batch_flw_courses`
  - `export_scorm_to_flw`
  - `export_scorm_batch_to_flw`
  - `run_batch_job`
  - SCORM identity/component mapping functions around `manifest_xml`, `scorm_structure_preview`, `export_scorm`
- `static/app.js`
- `static/index.html`
- `README.md`
- `scripts/smoke_test.py`

PHP:

- `scripts/import_scorm_pilot_to_moodle.php`
  - replace old Unit=Moodle Course functions:
    - `language_course_definition`
    - `find_existing_language_course`
    - `find_corresponding_language_course`
    - `resolve_language_course`
    - `create_language_course`
    - `clear_course_for_overwrite`
    - `clear_courses_above_id`
    - `reset_course_id_sequence`
    - `find_or_create_pilot_section`
    - `make_idnumber`
    - `import_by_language`
    - `preview_course_map`

Potential Moodle-side reuse/extension:

- `local_flwcupkp` mapping/object services may be reusable for Activity→cmid, but not enough for full deployment mapping.
- A new or extended stable deployment map is still needed for World+Stage Course, Unit Section, Unit SCORM, and component/SCO identity.

## Risks

1. Moodle dataroot is not writable for normal Moodle bootstrap.
   - Blocks real importer/tracking tests.
   - Must be fixed before S2B/S5 real Moodle evidence.
2. Current importer has destructive old architecture.
   - `Overwrite` clears a whole Moodle course.
   - `Clear and Add` deletes courses by numeric threshold.
3. Current importer uses timestamped SCORM module idnumbers.
   - Not stable for v8 identity.
4. Moodle preserves tracking only when SCO manifest identifiers remain stable.
   - Renamed/removed SCO identifiers can delete old tracking rows.
5. Existing FLW mapping tables are only partial for deployment identity.
   - They should be reused or extended carefully, but cannot be assumed complete.
6. Spanish source root is not present in the confirmed SmartCourses directory.
   - Spanish support must be configurable/discoverable, but cannot be validated from local source units yet.
7. Native Moodle SCORM TOC/player behavior must be tested in real UI.
   - Source shows settings exist; S0 did not perform learner UI/player tracking tests.

## S0 GO / NO-GO recommendation

Recommendation:

```text
CONDITIONAL GO to S1 when requested.
```

Conditions before real Moodle import/tracking gates:

1. Fix Moodle dataroot write permission so normal Moodle CLI/bootstrap works.
2. Do not run destructive old `Overwrite` or `Clear and Add` production imports.
3. Keep Unit editor behavior frozen.
4. Build S1 as metadata/mapping-only, with no redesign of Unit editing.
5. Add tests around stable identity before replacing the old importer path.

STOP after Gate S0.

