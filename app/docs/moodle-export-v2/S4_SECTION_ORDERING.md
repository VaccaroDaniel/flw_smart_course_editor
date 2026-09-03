# S4 Section Ordering

Gate: S4 — Unit Section Resolver

Status: PASS

## Ordering rule

Unit sections in a Stage Course are ordered by normalized `unitSequence`.

Example for Real English World A2:

```text
REW-U019 → section 1
REW-U020 → section 2
...
REW-U036 → section 18
```

Moodle section 0 is never moved.

## Enforcement

S4 scans FLW-marked sections in the Moodle course, sorts them by `unitSequence`, and moves them using:

```php
move_section_to($course, $fromsection, $tosection, true)
```

Reordering requires:

```text
moodle/course:movesections
```

## Conflict safety

S4 does not reorder when the current group has a blocking Unit Section conflict, such as:

- `UNIT_SECTION_DUPLICATE`
- `UNIT_SECTION_TARGET_MISSING`
- `UNIT_STAGE_MOVE_REQUIRED`
- `SECTION_MAPPING_CONFLICT`
- `PERMISSION_DENIED`

This prevents accidental cleanup or silent migration when identity is ambiguous.

## Map refresh

After real Moodle reordering, S4 refreshes the local Unit→Section map so `moodleSectionNumber` matches Moodle's current section order.

