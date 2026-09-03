# S8 Failure Recovery

Status: PASS  
Date: 2026-08-24

## Recovery invariant

S8 must not leave a valid Unit Section without a current Unit SCORM when a replacement fails.

For supersession, the importer creates and reloads the replacement first. Only after that does it retire the old current SCORM. If an exception occurs after a replacement cmid exists, the failed replacement is hidden and renamed with a failed pending idnumber on a best-effort basis; the historical SCORM is not deleted.

## Verified invalid-package failure

Fixture:

- Unit: `S8T-S80824151148-U005`
- existing current cmid before failure: 2120
- invalid package: 15-byte non-SCORM ZIP fixture

Result:

- action: `SCORM_PACKAGE_INVALID`
- report exit code: 2
- current cmid after failure: 2120
- current activity remained visible
- current SCORM name remained `U005 — S8 Disposable Unit 005 v2`

Reports:

- `verification_exports/s8_disposable_rebuild/s8_u005_before_invalid_snapshot.json`
- `verification_exports/s8_disposable_rebuild/s8_u005_invalid_failure_report.json`
- `verification_exports/s8_disposable_rebuild/s8_u005_after_invalid_snapshot.json`

## Preview-staleness and confirmation

Real S8 rebuild requires a preview hash. If no preview hash is provided, the importer returns:

- `PREVIEW_REQUIRED`
- public status `BLOCKED`

Report:

- `verification_exports/s8_disposable_rebuild/s8_preview_required_guard_report.json`

## Cancel/resume safety

S8 reuses the S7 batch framework. Resume/idempotence was verified by rerunning the same completed U001/U002 rebuild scope.

Result:

- dry-run after completion: `SKIP_UNCHANGED` for both Units
- real rerun after completion: `SKIP_UNCHANGED` for both Units
- U001 current cmid remained 2123
- no duplicate supersession was created

Report:

- `verification_exports/s8_disposable_rebuild/s8_resume_idempotence_real_report.json`

