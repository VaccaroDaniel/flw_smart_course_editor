# Gate S5 — Moodle SCORM Update Behavior

Status: PASS

Installed Moodle remains:

- Moodle `5.1.5 (Build: 20260608)`
- branch `501`
- SCORM module version `2025100601`

## APIs confirmed/used

- Create SCORM activity:
  - `prepare_new_moduleinfo_data()`
  - `add_moduleinfo()`
  - `scorm_add_instance()`
- Update existing package while preserving cmid:
  - `scorm_update_instance()`
  - `set_coursemodule_idnumber()`
  - `set_coursemodule_name()`
  - `rebuild_course_cache()`
- Supersede without deleting history:
  - `set_coursemodule_idnumber()`
  - `set_coursemodule_visible()`
  - `set_coursemodule_name()`
  - `add_moduleinfo()` for the new current SCORM

`update_moduleinfo()` was inspected and initially tested, but in this CLI path it triggered a Moodle coding exception after the SCORM package had already been updated: “The 'modulename' value must be set in other.” S5 therefore uses Moodle’s supported module-specific `scorm_update_instance()` for package replacement, and uses course-module setters for the course module fields.

## Parser behavior that drives S5 safety

Moodle `mod/scorm/datamodels/scormlib.php::scorm_parse_scorm()` matches old and new SCO rows by manifest item `identifier`.

- Same identifier: Moodle updates the `scorm_scoes` row and preserves its `id`.
- New identifier: Moodle inserts a new `scorm_scoes` row.
- Missing old identifier: Moodle deletes that `scorm_scoes` row and calls `scorm_delete_tracks($scormid, $olditem->id)`.

Therefore S5 treats removal/rename of tracked SCO identifiers as unsafe for in-place update and supersedes instead.

## File-pool behavior found during S5

Windows Moodle file-pool writes failed when Moodle attempted to create a draft upload for a ZIP whose contenthash did not already exist and a stale `*.tmp` was present. The existing S2B helper pre-warmed ZIP contents but not the ZIP file itself. S5 fixes this by calling `ensure_filepool_path($packagepath)` inside `draft_file_from_path()`.

The stale temp file observed for the first package hash was moved aside recoverably:

`D:\Dev\MoodleWindowsInstaller-latest-501\server\moodledata\temp\codex_s5_stale_filepool_tmp_559ced61a8ed86305a10b8c6c105ebb0e1899137.tmp`

After package ZIP pre-warm, create/update/supersede passed.
