# S0 Current Implementation

Created: 2026-08-23

Gate: S0 — Current Implementation Freeze

Status: current Smart Course Editor treated as an existing working product. No production code was changed during S0.

## Repository / workspace findings

Current editor root:

```text
C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui
```

The containing workspace lists `.git`, but `git status` from both the workspace root and `adventure_scorm_gui` reports:

```text
fatal: not a git repository (or any of the parent directories): .git
```

So S0 uses filesystem inventory and test results as the baseline. There is no usable Git working-tree diff available from this checkout.

## Relevant Smart Course Editor files

First-party editor source files identified:

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
.settings.json
```

Generated/runtime folders present but not production source:

```text
__pycache__/
batch_jobs/
dist/
logs/
pilot_exports/
unit_cache/
verification_exports/
```

## Primary Python source areas

`server.py` is the main editor/server. Important current-function groups:

- settings/root/export/Moodle target handling:
  - `root_from_value`
  - `normalize_moodle_url`
  - `default_moodle_url`
  - `default_moodle_php_path`
  - `default_moodle_config_path`
  - `moodle_target_from_options`
  - `primary_settings_path`
  - `fallback_settings_path`
  - `settings_path`
  - `load_settings`
  - `save_settings`
  - `update_saved_paths`
  - `ensure_root`
  - `ensure_writable_output_dir`
- unit discovery and ZIP-backed unit handling:
  - `is_unit_dir`
  - `is_unit_archive`
  - `archive_cache_dir`
  - `fallback_archive_cache_dir`
  - `detect_content_root`
  - `find_unit_dir`
  - `find_unit_archive`
  - `extract_unit_archive`
  - `selected_unit_archive`
  - `repack_unit_archive`
  - `unit_dir`
  - `list_units`
- unit editing:
  - `editable_file`
  - `list_unit_files`
  - `import_unit_asset`
  - `list_unit_backups`
  - `restore_unit_backup`
  - `replace_index_reference`
  - `read_csv_file`
  - `write_csv_file`
  - `read_unit_data`
  - `unit_data_summary`
  - `write_unit_data`
  - `read_visual_edits`
  - `merge_visual_edits`
  - `edit_preview_html`
- unit copy:
  - `copy_unit_package`
  - `renamed_unit_name`
  - `update_unit_data_number_fields`
  - `update_copied_index_metadata`
  - `update_copied_manifest_metadata`
- SCORM preview/export:
  - `scorm_structure_preview`
  - `export_scorm`
  - `manifest_xml`
  - `zip_stage`
  - `create_fixed_section_launch`
  - `create_lesson_launches`
  - `create_generic_section_launches`
  - `inject_scorm_script`
  - `inject_lesson_focus_script`
  - `inject_top_nav_hide_style`
- language-specific SCO section detection:
  - `real_world_sco_sections`
  - `russian_world_sco_sections`
  - `chinese_world_sco_sections`
  - `german_world_sco_sections`
  - `japanese_world_sco_sections`
  - `french_world_sco_sections`
  - `generic_sco_sections`
- old FLW/Moodle import integration:
  - `detect_flw_language`
  - `discover_batch_language_roots`
  - `batch_language_unit_plan`
  - `planned_batch_manifest`
  - `direct_flw_manifest`
  - `run_flw_import`
  - `run_flw_course_preview`
  - `export_scorm_to_flw`
  - `export_scorm_batch_to_flw`
  - `run_batch_job`
  - `start_batch_job`

`static/app.js` is the main browser UI controller. It implements current root selection, export folder selection, unit list rendering, visual edit controls/history, unit data editing, file/CSV editing, asset import, ZIP save-back UX, SCORM export UI, and FLW import UI.

`static/index.html` defines the current non-technical editor UI, including:

- root directory browse button;
- export folder browse button;
- Moodle URL / PHP path / config path fields;
- SCORM export tab;
- Build and Import to FLW controls;
- Batch FLW Import controls;
- visual editing toolbar and panel.

`static/style.css` defines the current layout and editor styling.

## Current Unit editing behavior

Observed from source and smoke coverage:

1. The editor can select a root directory and persists the selected root/export/Moodle paths in settings.
2. Units can be discovered as folders or ZIP packages.
3. ZIP-backed units are unpacked into a cache for editing.
4. File edits, CSV edits, unit-data edits, visual edits, asset imports, reference replacement, backup/restore, and unit copy operate on the selected unit.
5. ZIP-backed edits remain in the unpacked cache until the user clicks `Save back to source ZIP`.
6. `Save back to source ZIP` repacks the edited unit and creates/uses ZIP-backup behavior.
7. The current editor includes undo/redo for visual edit operations and compact icon-style controls.
8. The visual edit runtime makes visible text blocks editable in preview and stores patches in `index.html`.
9. Unit list and editing UI are considered existing working product behavior and must not be redesigned during later gates unless directly required by Moodle deployment metadata.

## Current SCORM export behavior

Current SCORM behavior is retained for S0:

1. A selected FLW Unit exports as one SCORM 1.2 package.
2. Export supports multi-SCO generation.
3. Substantial sections/components are detected by language-specific and generic section detectors.
4. Current section detectors include fixed sections such as vocabulary/watch/project/result where detected and lesson-level sections where detected.
5. The exporter injects SCORM API wrapper behavior and launch/focus support.
6. Export can hide the unit top navigation unless the keep-top-nav option is enabled.
7. The generated export includes a ZIP package and JSON report.
8. Batch export currently plans all available units per detected language root.

This S0 did not redesign SCORM granularity or Moodle navigation. Later gates must preserve current multi-SCO export while replacing Moodle deployment architecture.

## Current old Moodle import behavior to replace later

The current Moodle importer still implements the old architecture:

```text
FLW Unit
→ Moodle Course
```

Confirmed old-path PHP functions in `scripts/import_scorm_pilot_to_moodle.php`:

- `language_course_definition()`
- `find_existing_language_course()`
- `find_corresponding_language_course()`
- `resolve_language_course()`
- `create_language_course()`
- `clear_course_for_overwrite()`
- `clear_courses_above_id()`
- `reset_course_id_sequence()`
- `find_or_create_pilot_section()`
- `make_idnumber()`
- `import_by_language()`
- `preview_course_map()`

Current risky behaviors:

- language/unit catalog hard-codes one Moodle course per Unit;
- fixed Unit 001 Moodle course IDs are still encoded;
- fuzzy course-title/shortname matching is used;
- `Overwrite` clears an entire matched course;
- `Clear and Add` deletes courses above ID 100 and resets course ID sequence;
- SCORM activity `cmidnumber` is timestamped through `make_idnumber()`;
- import result wording is course-centric rather than World+Stage Course → Unit Section → Unit SCORM.

These are S0 findings only. They were not changed.

## SmartCourses source roots

Confirmed top directory:

```text
D:\WinPro.Delta\Projects\SmartCourses
```

Actual roots found:

| Root | Path | ZIP units |
|---|---:|---:|
| 01-Adventure | `D:\WinPro.Delta\Projects\SmartCourses\01-Adventure` | 72 |
| 02-Real | `D:\WinPro.Delta\Projects\SmartCourses\02-Real` | 108 |
| 03-Russian | `D:\WinPro.Delta\Projects\SmartCourses\03-Russian` | 120 |
| 04-Chinese | `D:\WinPro.Delta\Projects\SmartCourses\04-Chinese` | 133 |
| 05-German | `D:\WinPro.Delta\Projects\SmartCourses\05-German` | 60 |
| 06-Japanese | `D:\WinPro.Delta\Projects\SmartCourses\06-Japanese` | 60 |
| 08-French | `D:\WinPro.Delta\Projects\SmartCourses\08-French` | 48 |

Spanish:

- No Spanish root is present in the top SmartCourses directory.
- No immediate `07-Spanish` root was found.
- A broad nearby Spanish-name scan was started but stopped because it became too broad and returned no result before stopping.
- S1 must add Spanish support as configurable/discoverable, but cannot assume an actual local Spanish root exists in this workspace.

