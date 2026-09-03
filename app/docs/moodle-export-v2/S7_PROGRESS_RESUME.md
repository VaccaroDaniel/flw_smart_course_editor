# S7 Progress, Cancel, and Resume

Gate: S7 — Batch progress and resumability  
Created: 2026-08-24

## Job state

Batch jobs persist public state in:

```text
batch_jobs/<jobId>/job.json
```

Important fields:

- `status`
- `phase`
- `processedCount`
- `itemCount`
- `exportedCount`
- `current`
- `batchPlanId`
- `stageGroupCount`
- `catalogValidation`
- `preflight`
- `items`
- `manifestPath`
- `flwReportPath`
- `flw`

## Phases

S7 uses these phases:

```text
queued
planning
exporting
importing
cancelling
interrupted
complete
failed
canceled
```

## Cancellation policy

Cancellation before Moodle mutation is honored safely.

Cancellation after Moodle mutation has started does not terminate the PHP process mid-import. The job records:

```text
Moodle mutation already started; not terminating PHP process mid-import.
```

This avoids leaving Moodle state half-mutated.

## Resume policy

Resume reuses exported packages when the prior item has:

- `status = exported`
- manifest schema version 2 or later;
- target metadata;
- an existing ZIP path.

Reused rows are marked:

```text
REUSED_EXPORTED_PACKAGE
```

## Backend interruption recovery

Use `Start Course Editor.ps1` or `Start Course Editor.bat` for normal Windows operation. The launcher detaches the backend from the opening terminal, waits for `/api/config`, and preserves server output in:

```text
logs/server-stdout.log
logs/server-stderr.log
logs/editor-process.json
```

On startup, the editor reconciles persisted non-terminal jobs. If the recorded Moodle importer process is no longer running, the job becomes:

```text
status: interrupted
phase: interrupted
interruptionReason: EDITOR_BACKEND_PROCESS_ENDED
```

The job records its last non-empty Moodle importer log line and verifies every exported ZIP before enabling Resume. Resume is always a user-confirmed action; startup does not mutate Moodle. If every package remains reusable, Resume is import-only and rows are marked `REUSED_INTERRUPTED_JOB_EXPORT`. If some packages are absent, existing packages are retained and only missing packages are rebuilt before Moodle is re-checked idempotently using the original job options and import mode.

The batch worker is non-daemon so an ordinary Python shutdown waits for active batch work instead of silently abandoning the worker. The detached launcher additionally prevents the backend from ending merely because its launching terminal closes.

## Verified cancel/resume result

Test job:

```text
jobId: 20260824_094841_8b571ede
source: D:\WinPro.Delta\Projects\SmartCourses\02-Real
Units: U021-U024
mode: Overwrite
dry-run: true
```

Cancel snapshot:

```text
phase: exporting
processedCount: 1
exportedCount: 1
cancelRequested: true
```

Terminal after cancel:

```text
status: canceled
phase: canceled
processedCount: 2
exportedCount: 2
```

Resume result:

```text
status: complete
phase: complete
processedCount: 4
exportedCount: 4
resumeStates: REUSED_EXPORTED_PACKAGE, REUSED_EXPORTED_PACKAGE
publicStatus: UNCHANGED
```

Artifacts:

```text
verification_exports/s7_cancel_resume_job/flw_batch_job_20260824_094841_8b571ede/batch_manifest.json
verification_exports/s7_cancel_resume_job/flw_batch_job_20260824_094841_8b571ede/batch_flw_import_report.json
verification_exports/s7_cancel_resume_job/flw_batch_job_20260824_094841_8b571ede/moodle_import_stdout.log
verification_exports/s7_cancel_resume_job/flw_batch_job_20260824_094841_8b571ede/moodle_import_stderr.log
```
