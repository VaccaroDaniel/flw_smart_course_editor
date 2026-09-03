# Gate S5 — Unit SCORM Upsert Architecture

Status: PASS

S5 implements the final Unit-level Moodle deployment object without starting S6 production batch architecture.

## Frozen architecture implemented

- FLW World + Deployment Stage → Moodle Course
- FLW Unit → Moodle Section
- 1 FLW Unit → 1 current SCORM 1.2 activity/package in that Unit Section
- substantial FLW lesson/component → 1 launchable SCO
- micro-activities remain inside their parent SCO
- Moodle SCORM native TOC/structure is minimized/hidden by the same S2B settings
- learner-facing navigation remains the FLW compact navigator inside the SCO content

## Canonical S5 identifiers

For Real English Unit 23:

- UnitID: `REW-U023`
- UnitSCORMActivityID: `REW-U023-UNITSCORM`
- stable cmidnumber: `FLW_REW_U023_UNITSCORM`
- SCORM manifest identifier: `FLW_REW_U023_SCORM12`
- launch SCO identifiers: `FLW_REW_U023_<ComponentKey>`

The exporter was corrected so `futureCmidNumber` follows the frozen rule `FLW_<WORLD>_U###_UNITSCORM`.

## Code entry points

- `scripts/import_scorm_pilot_to_moodle.php`
  - `draft_file_from_path()` now pre-warms the package ZIP itself in Moodle filedir.
  - `unit_scorm_definition()` consumes normalized S1/S2/S3 target metadata and export mappings.
  - `scorm_package_manifest_details()` validates `imsmanifest.xml`.
  - `resolve_current_unit_scorm()` resolves existing current activity.
  - `deploy_unit_scorm_activity()` creates, updates, leaves unchanged, or supersedes the Unit SCORM.
  - `scorm_update_safety()` blocks unsafe in-place updates that would remove tracked SCO identifiers.
  - `retire_current_scorm_for_supersession()` hides and renames historical cmids without deletion.
  - `import_by_language()` and `preview_course_map()` now perform S5 Unit SCORM upsert/preview.
- `server.py`
  - `scorm_identity_context()` now emits `FLW_<WORLD>_U###_UNITSCORM`.
- `static/app.js`, `static/index.html`
  - UI/result copy now says Unit SCORM deployment instead of S4-only “pending S5”.

## Resolution order

The S5 importer resolves the Unit SCORM target in this order:

1. local UnitSCORMActivityID → current cmid map;
2. exact stable `course_modules.idnumber`;
3. safe adoption candidate in the resolved Unit Section whose parsed SCORM manifest identifier matches the expected Unit manifest;
4. create a new SCORM activity.

If a local map points to a missing cmid or a cmid outside the resolved Unit Section, the importer blocks with `SCORM_TARGET_MISSING` or `SCORM_IDENTITY_CONFLICT`.

## Current activity invariant

Only one visible/current FLW Unit SCORM has the stable cmidnumber. Superseded activities are preserved hidden with retired idnumbers such as:

`FLW_REW_U023_UNITSCORM_REV4_SUPERSEDED`

Teacher-authored Moodle activities in the Unit Section are not deleted, moved, or overwritten.
