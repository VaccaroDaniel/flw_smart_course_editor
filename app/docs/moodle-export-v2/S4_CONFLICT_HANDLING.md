# S4 Conflict Handling

Gate: S4 — Unit Section Resolver

Status: PASS

## Conflict statuses

S4 reports explicit statuses and does not silently repair identity conflicts.

| Status | Meaning | S4 behavior |
| --- | --- | --- |
| `CREATE_SECTION` | No existing Unit section found. | Create section when authorized. |
| `REUSE_SECTION` | Existing Unit section matches canonical identity. | Reuse section. |
| `UPDATE_SECTION` | Section title/marker drift found. | Update section name/marker; preserve teacher summary content. |
| `REORDER_SECTION` | Section exists but order differs. | Move section when authorized. |
| `UNIT_SECTION_DUPLICATE` | More than one target course section has the same Unit marker. | Block; require manual cleanup. |
| `UNIT_SECTION_TARGET_MISSING` | Local map points to a missing Moodle section. | Block unless the resolved Stage Course was demonstrably recreated after the saved mapping; that narrow case recreates the section and replaces the stale mapping. |
| `UNIT_STAGE_MOVE_REQUIRED` | Existing marker/map points to a different Stage Course. | Block; migration must be explicit. |
| `SECTION_MAPPING_CONFLICT` | Local map and Moodle marker point to different sections. | Block; require manual decision. |
| `PERMISSION_DENIED` | User lacks course update/move capability. | Block mutation. |
| `SCORM_PENDING_S5` | Unit SCORM activity import is not part of S4. | Report only. |

## Teacher content preservation

S4 only replaces the bounded FLW marker block. It does not overwrite the rest of `course_sections.summary`.

The recreated-course exception compares Moodle `course.timecreated` with the
mapping timestamp. A missing section in the same course generation remains a
blocker; course-ID equality alone is not sufficient to authorize repair.

Verified with:

```text
S4_MANUAL_TEACHER_CONTENT_REW_U023
```

The marker and manual teacher text both remained after title drift repair.
