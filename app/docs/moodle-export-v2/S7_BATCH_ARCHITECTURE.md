# S7 Batch Architecture

Gate: S7 — Batch import + Course/Unit-Section mapping preview + Progress/Resume/Idempotency  
Created: 2026-08-24

## Architecture

S7 keeps the frozen architecture:

```text
FLW World + Deployment Stage -> Moodle Stage Course
FLW Unit -> Moodle Unit Section
1 FLW Unit -> 1 current multi-SCO SCORM 1.2 activity inside the Unit Section
substantial lesson/component -> SCO
micro-activities -> remain inside parent SCO
```

S7 does not redesign the Unit editor and does not modify Moodle core.

## Batch pipeline

The batch pipeline is:

```text
source root selection
-> language root discovery
-> Unit catalog planning
-> S1/S3/S4/S5 target enrichment
-> optional SCORM package export
-> Moodle dry-run or real upsert
-> persisted batch report
```

The frontend never resolves Moodle IDs itself. It displays the backend contract: World, Stage Course, Unit Section, and Unit SCORM.

## Import modes

S7 supports normal batch modes only:

- `Overwrite`: synchronize each selected Unit into its canonical Stage Course and Unit Section.
- `Add New Unit`: add only when the canonical UnitID is not already present.

`Clear and Add` is deliberately rejected in S7. Clear/rebuild production behavior belongs to S8.

## Preservation guarantees

S7 batch import preserves:

- existing Moodle Stage Courses;
- unrelated sections and teacher-authored content;
- existing Unit Section identity where possible;
- existing SCORM cmid on update/unchanged paths;
- learner attempts/tracking where the cmid and SCORM activity are preserved.

S7 real batch import never clears a Stage Course and never deletes legacy Unit Courses.

## Concurrency

Real batch imports acquire scoped locks per Stage/Unit target before Moodle mutation. This prevents overlapping real imports for the same canonical Unit target while allowing unrelated dry-run planning and export operations.

## Async job runner

Batch jobs are persisted under `batch_jobs/<jobId>/job.json`.

The Moodle PHP child process now spools stdout/stderr to:

- `moodle_import_stdout.log`
- `moodle_import_stderr.log`

This prevents async jobs from deadlocking on full stdout/stderr pipes.

