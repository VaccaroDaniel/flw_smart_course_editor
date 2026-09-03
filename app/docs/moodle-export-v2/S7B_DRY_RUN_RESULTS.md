# S7B Dry-Run Results

Gate: S7B — Seven-world full-scope package-aware dry-run  
Created: 2026-08-24

## Command scope

```text
source root: D:\WinPro.Delta\Projects\SmartCourses
batchAllUnits: true
batchProductionScope: seven_world_production
batchFlwImportMode: overwrite
flwDryRun: true
Moodle URL: https://main.flw.com
```

Spanish was excluded from readiness scope. Chinese was capped to U001-U132. German ran U001-U060 because U061-U072 are intentionally ignored in the current production scope.

## Result

```text
elapsedSeconds: 970.42
itemCount: 600
exportedCount: 600
missingCount: 0
exportFailedCount: 0
stageGroupCount: 33
preflight RESOLVED: 600
preflight blockers: 0
publicStatus: SUCCESS_WITH_WARNINGS
```

The warning is from non-blocking legacy Unit Course detection, not from Stage resolution or SCORM failures.

## Moodle dry-run summary

```text
Stage Courses: 33
reused Stage Courses: 3
would create Stage Courses: 30
legacy Unit Courses found: 22
Unit Sections: 600
reused Unit Sections: 19
would create Unit Sections: 581
SCORM created: 581
SCORM updated: 1
SCORM unchanged: 18
SCORM failures: 0
Units blocked: 0
Units conflict: 0
Units failed: 0
manual content preserved: 600
attempts preserved: 600
```

## Artifacts

```text
D:\WinPro.Delta\Projects\SmartCourses\_s7b_seven_world_dryrun_exports\flw_batch_20260824_105523_841065\batch_manifest.json
D:\WinPro.Delta\Projects\SmartCourses\_s7b_seven_world_dryrun_exports\flw_batch_20260824_105523_841065\batch_flw_import_report.json
```

Export folder size:

```text
600 ZIPs
1202 files
about 18.06 GB
```

## Current scoped validation after German scope closure

After the user instruction to ignore German U061-U072, current S7B planning validates as:

```text
expectedTotal: 600
availableValidTotal: 600
selectedTotal: 600
missingOrInvalidTotal: 0
Stage unresolved: 0
Stage conflict: 0
```

Fresh mapping preview artifact:

```text
verification_exports/s7b_pass_closure_preview/flw_preview_20260824_113105_499492/batch_course_preview_report.json
```

Preview result:

```text
expectedTotal: 600
availableValidTotal: 600
selectedTotal: 600
preflight blockers: 0
```

## Interpretation

The 600-Unit seven-world dry-run passed with no Stage blockers and no SCORM failures. S7B production readiness is now PASS for the current 600-Unit scope.
