# S4 Section Mapping

Gate: S4 — Unit Section Resolver

Status: PASS

## Mapping method

S0 found no existing reusable FLW Unit→Moodle Section mapping table in the installed Moodle/FLW code.

S4 therefore uses the smallest repo-compatible approach:

1. A local JSON map file.
2. A hidden machine marker in the Moodle section summary.

Default map path:

```text
flw_moodle_unit_section_map.json
```

Verification map path:

```text
verification_exports/s4_unit_section_tests/s4_unit_section_map.json
```

## Hidden Moodle marker

S4 appends this bounded marker to `course_sections.summary`:

```html
<!-- FLW_UNIT_SECTION_MARKER_START -->
<!-- FLW_UNIT_KEY:REW-U023 -->
<!-- FLW_WORLD_CODE:REW -->
<!-- FLW_DEPLOYMENT_STAGE:A2 -->
<!-- FLW_COURSE_KEY:FLW_REW_A2 -->
<!-- FLW_UNIT_SEQUENCE:23 -->
<!-- FLW_UNIT_SECTION_MARKER_END -->
```

The resolver replaces only the bounded marker block. Teacher-authored summary content outside the marker is preserved.

## JSON map entry

Each map entry stores:

- `UnitID`
- `WorldCode`
- `DeploymentStageCode`
- `courseExternalKey`
- `moodleCourseId`
- `moodleSectionId`
- `moodleSectionNumber`
- `unitNumber`
- `unitSequence`
- `unitTitle`
- `sectionName`
- `status`
- timestamps

## Resolver precedence

S4 checks both local map and Moodle markers:

1. Wrong-course/stage mapping or marker → `UNIT_STAGE_MOVE_REQUIRED`.
2. Duplicate markers in the target course → `UNIT_SECTION_DUPLICATE`.
3. Local map points to a missing section:
   - if the current Stage Course was created after the mapping timestamp, treat the entry as stale and recreate/remap the Unit Section;
   - otherwise → `UNIT_SECTION_TARGET_MISSING`.
4. Local map and Moodle marker disagree → `SECTION_MAPPING_CONFLICT`.
5. Existing single marker or map target → reuse/update section.
6. No target → create section.
