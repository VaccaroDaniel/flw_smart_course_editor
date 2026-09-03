# S4 Section Identity

Gate: S4 — Unit Section Resolver

Status: PASS

## Canonical identity

The canonical Unit Section identity is the normalized FLW `UnitID`.

Example:

```text
REW-U023
```

The resolver does not treat Moodle section number, title, or current order as identity. Those are mutable properties.

## Section display title

The default Moodle section name is generated from the unit number and unit title:

```text
U023 — Real Unit 23
```

If the Moodle title drifts, S4 reports/executes:

```text
UPDATE_SECTION
```

Teacher-authored section summary content is preserved while the machine marker is refreshed.

## Identity fields used from normalized metadata

S4 uses the S1/S3 metadata already present in manifests:

- `worldCode`
- `deploymentStageCode`
- `courseExternalKey`
- `unitId`
- `unitNumber`
- `unitSequence`
- `unitTitle`
- `moodleCategory`

## Non-identity fields

These are not canonical identifiers:

- Moodle `course_sections.section`
- Moodle `course_sections.name`
- Moodle display order
- teacher-edited summary text

