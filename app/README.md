# Adventure SCORM GUI

Local browser GUI for inspecting Adventure English World V3 unit folders and exporting Moodle-ready SCORM 1.2 packages.

## Run

```powershell
cd "C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui"
.\Start Course Editor.ps1
```

You can also double-click `Start Course Editor.bat`. The launcher starts the backend as a detached hidden Windows process, waits for the health endpoint, and writes persistent process logs under `logs`. Use `-NoBrowser` when the browser should not open automatically.

Then open:

```text
http://127.0.0.1:8788
```

The default content root is:

```text
D:\WinPro.Delta\Projects\SmartCourses\01-Adventure
```

SCORM exports default to:

```text
D:\WinPro.Delta\Projects\SmartCourses\01-Adventure\scorm_exports
```

## What It Does

- Scans `adventure_english_world_v3_unit001` through `unit072`.
- Scans SmartCourses unit ZIP roots such as `Adventure_world_unit_001.zip`, `Real_world_unit_001.zip`, `RUW2_U001.zip`, `GW3_U001_...zip`, `JW3_U001_...zip`, and `FW_U001_...zip`.
- Auto-unpacks selected ZIP units into `.scorm_gui_unpacked` so preview, editing, validation, and SCORM export can work like normal folders. The original ZIP is not overwritten.
- Provides a `Save back to source ZIP` button for ZIP-backed units. It rebuilds the original ZIP from the edited unpacked folder and first saves a timestamped backup under `.scorm_gui_zip_backups`.
- Remembers the last selected course/unit root and SCORM export folder in `%LOCALAPPDATA%\AdventureScormEditor\settings.json`.
- Previews the selected unit's `index.html`.
- Edits visible text directly in the Preview tab with Visual edit mode.
- Lets you change visible link/button titles, link `href` values, and image/audio/video sources.
- Imports new image/audio/video files into the selected unit package.
- Shows a broken-asset dashboard with ranked replacement suggestions and previews.
- Shows a SCORM structure preview before export.
- Adds a `Build and import to FLW` action in the SCORM tab. It builds the selected unit, detects the SmartCourses language root, and imports the SCORM package into the matching FLW/Moodle language course through Moodle's PHP APIs. The single-unit `Import Mode` can `Overwrite` the matching course, or `Add New` as the next available course. The SCORM tab includes saved `Moodle URL`, `Moodle PHP path`, and `Moodle config.php path` fields so the actual Moodle installation/database target can be selected. Defaults can be overridden with `FLW_MOODLE_URL`, `FLW_MOODLE_PHP`, and `FLW_MOODLE_CONFIG`.
- Includes `Batch FLW import` controls for importing all detected language roots, either across all available units or a chosen unit range. When `All available units in all languages` is selected, each language uses its own available unit list, so a 72-unit Adventure root and a 108-unit Real English root are both imported at their full language-specific counts. Batch `Import Mode` supports `Overwrite`, `Add New`, and `Rebuild Selected FLW Scope`. Rebuild Selected FLW Scope is the safe replacement for the old destructive clear/add idea: it acts only on the selected FLW World/Stage/Unit scope, requires a dry-run preview before real execution, preserves Moodle Stage Courses, Unit Sections, manual teacher content, learner attempts/tracking, grades, completion, and legacy Unit Courses, and supersedes history-bearing SCORMs instead of deleting them. Batch dry run is enabled by default. `Preview Moodle Course / Unit-Section Mapping` checks Moodle Stage Course, Unit Section, and Unit SCORM targets before packages are built. Batch import runs as a background job with progress polling, cancel, and resume-last-job controls.
- Lists timestamped file backups and can restore a backup from the editor.
- Edits the embedded `window.UNIT_DATA` package object through a structured Unit Data tab.
- Edits text files and CSV files with automatic backups in `.scorm_gui_backups`.
- Validates `index.html` and local asset references.
- Exports a SCORM 1.2 zip with a root `imsmanifest.xml`, the full unit `index.html` at the package root, and filtered section SCOs for Vocabulary Builder, each lesson, Watch, and Progress Result. Each section SCO keeps the unit hero/top content and shows only its own section content. The unit top navigation bar is hidden by default, with an export option to keep it. If a unit has no section data, the exporter falls back to one unit-level SCO.

The exporter stages files in a temporary directory and does not modify source unit files.

## Moodle / FLW Deployment Architecture

The frozen Program-1 deployment architecture is:

- FLW World + Deployment Stage → Moodle Stage Course.
- FLW Unit → Moodle Unit Section.
- 1 FLW Unit → 1 SCORM 1.2 package/activity in that Unit Section.
- Each substantial lesson/component → 1 stable SCO.
- Micro-activities remain inside their parent component SCO.
- Learners navigate through the Moodle Course roadmap, the Unit Section, and the FLW compact lesson/component navigator. Moodle's native SCORM TOC is hidden/minimized so it does not become a second primary learner navigator.

Import modes:

- `Overwrite`: synchronize the selected canonical Unit Section and current Unit SCORM without clearing the Stage Course or neighboring Units.
- `Add New`: create only when the canonical UnitID is not already deployed; existing UnitIDs return `UNIT_ALREADY_EXISTS` and should be copied first if a true duplicate Unit is desired.
- `Rebuild Selected FLW Scope`: preview-required safe scoped rebuild. No-history SCORMs may update in place; history-bearing SCORMs are preserved as historical and replaced by a new current SCORM.

Legacy Unit-per-Moodle-Course deployments are detected and left untouched. The editor does not reset Moodle numeric IDs or delete courses by numeric threshold in normal production import paths.

Downstream Program-1 consumers should use the versioned contract in:

```text
docs\moodle-export-v2\P1_CONTENT_DEPLOYMENT_CONTRACT_V1.md
```

Current verified production catalog scope is seven worlds / 600 Units: Adventure 72, Real English 108, Russian 120, Chinese 132, German 60, Japanese 60, and French 48. Spanish remains out of scope. German U061-U072 are intentionally excluded until those source packages are supplied or the release scope is changed.

## Smoke Test and Logs

Run the repeatable smoke test without touching real SmartCourses data:

```powershell
cd "C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui"
python .\scripts\smoke_test.py
```

Editor request/error logs are written to:

```text
logs\editor.log
logs\server-stdout.log
logs\server-stderr.log
logs\editor-process.json
```

If Windows or the editor backend ends during a batch deployment, the next startup marks the unfinished job as `interrupted` instead of leaving it looking active. The Export Result shows the last importer output and how many existing SCORM ZIPs are reusable. `Resume interrupted import` requires confirmation, preserves the job's original Moodle/import settings, and reuses verified packages instead of exporting them again. Startup never resumes a Moodle import automatically.

## Offline Installer

Build a no-admin Windows offline installer with a bundled Python 3.11.9 runtime:

```powershell
cd C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_offline_installer.ps1
```

The installer zip is written to:

```text
dist\AdventureScormEditor-offline-py3119.zip
```

On an offline Windows machine, unzip it and run `Install.bat`, or run `Run Editor.bat` directly for portable use.

## Editing Units

Use Preview > Visual edit when you want to work directly on the HTML page. The visual editor can:

- Edit visible text in place.
- Change text on buttons and links.
- Change navigation/link targets.
- Select an image and replace its `src` with another unit image path.
- Select audio/video and replace its source.
- Import image/audio/video assets into the selected unit.
- Apply preset or custom styling blocks.
- Select parent/child targets for more precise visual edits.
- Remove a selected block from the rendered page.
- Duplicate a selected block.
- Move a selected section or lesson to the top of its parent section.
- Add a new text block after the selected block.
- Add a new image block after the selected block.

The tool saves those changes as visual edit patches in `index.html`, so they are included in SCORM exports.

Use the Unit Data tab for normal package edits:

- Overview: course, unit, title, stage, mission, hero image, video source.
- Vocabulary: word, IPA, meaning, example, note, icon path.
- Lessons: lesson title, aim, study text, rule, tip, image, practice type.
- Watch Script: speaker, text, audio key, duration.
- Raw JSON: full `window.UNIT_DATA` object for advanced edits.

Saving creates a timestamped backup under the unit folder:

```text
.scorm_gui_backups
```
