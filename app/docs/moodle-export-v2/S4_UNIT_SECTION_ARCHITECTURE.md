# S4 Unit Section Architecture

Gate: S4 — Unit Section Resolver

Status: PASS

## Frozen relationship implemented in S4

S4 keeps the architecture established by S1–S3 and adds the missing Unit section layer:

```text
FLW World + Deployment Stage
→ Moodle Course

FLW Unit
→ Moodle Section
```

S4 deliberately stops before SCORM activity import:

```text
1 FLW Unit
→ 1 SCORM 1.2 package
→ pending S5 Moodle SCORM activity import
```

## Runtime flow

The existing Moodle import CLI now resolves in this order:

1. Read S1/S3 normalized target metadata from each manifest item.
2. Resolve the Stage Course using the S3 resolver.
3. Resolve one Moodle course section per FLW Unit using canonical `UnitID`.
4. Create, reuse, update, or reorder Moodle sections as needed.
5. Report `SCORM_PENDING_S5`; no SCORM module is created during S4.

## Moodle APIs used

Moodle version verified: `5.1.5 (Build: 20260608)`.

S4 uses Moodle's normal course APIs:

- `course_create_sections_if_missing($course, $sectionnumber)`
- `course_update_section($course, $section, $data)`
- `move_section_to($course, $fromsection, $tosection, true)`
- `rebuild_course_cache($courseid, true)`

Permissions are checked before mutation:

- create/update: `moodle/course:update`
- ordering: `moodle/course:movesections`

## Files changed

- `scripts/import_scorm_pilot_to_moodle.php`
  - `unit_section_definition()`
  - `resolve_unit_section()`
  - marker parsing/writing helpers
  - local Unit→Section JSON mapping
  - `enforce_unit_section_order()`
  - S4 report summaries and `SCORM_PENDING_S5`
- `static/index.html`
  - UI wording changed from Stage Course-only to Unit Section resolution.
- `static/app.js`
  - Direct and batch FLW report summaries now show Unit Section actions and SCORM pending S5.
- `scripts/smoke_test.py`
  - Added static S4 regression guards.

