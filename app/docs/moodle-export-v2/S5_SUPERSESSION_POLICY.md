# Gate S5 — Supersession Policy

Status: PASS

S5 never deletes a Moodle SCORM activity to replace a FLW Unit SCORM package.

## In-place update is allowed when

- the existing activity is resolved by UnitSCORMActivityID map, stable cmidnumber, or safe adoption;
- the new package manifest identifier matches the expected Unit manifest identifier;
- all tracked existing launch SCO identifiers remain present in the new package;
- there is no duplicate stable cmidnumber or conflicting map target.

## Supersession is required when

- a tracked SCO identifier is removed or renamed;
- a user explicitly passes `--force-supersede`;
- future checks determine package update is unsafe for learner history.

## Supersession action

1. Retire the existing current cmid:
   - set retired idnumber: `FLW_<WORLD>_U###_UNITSCORM_REV<N>_SUPERSEDED`
   - hide the old course module
   - rename it with `[Superseded]`
2. Create a new current SCORM in the same Moodle Unit Section.
3. Assign the stable cmidnumber to the new current cmid.
4. Update the local Unit SCORM map so only the new cmid is current.
5. Keep historical cmids and learner tracking intact.

## Evidence

Unsafe remove:

- retired: cmid `2094`, scorm id `71`, `FLW_REW_U023_UNITSCORM_REV4_SUPERSEDED`
- new current: cmid `2095`, scorm id `72`, `FLW_REW_U023_UNITSCORM`

Forced supersede:

- retired: cmid `2095`, scorm id `72`, `FLW_REW_U023_UNITSCORM_REV5_SUPERSEDED`
- new current: cmid `2097`, scorm id `73`, `FLW_REW_U023_UNITSCORM`
