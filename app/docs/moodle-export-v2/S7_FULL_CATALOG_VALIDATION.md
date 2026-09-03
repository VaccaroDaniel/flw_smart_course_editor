# S7 Full Catalog Validation

Gate: S7 — Full catalog planning and package-aware dry-run  
Created: 2026-08-24

## Source root

Top root tested:

```text
D:\WinPro.Delta\Projects\SmartCourses
```

## Expected catalog

| World | Expected | Available valid | Selected | Missing/invalid | Extra | Status |
|---|---:|---:|---:|---:|---:|---|
| Adventure | 72 | 72 | 72 | 0 | 0 | RESOLVED |
| Real | 108 | 108 | 108 | 0 | 0 | RESOLVED |
| Russian | 120 | 120 | 120 | 0 | 0 | RESOLVED |
| Chinese | 132 | 133 | 133 | 0 | 1 | RESOLVED |
| German | 72 | 60 | 60 | 12 | 0 | RESOLVED |
| Japanese | 60 | 60 | 60 | 0 | 0 | RESOLVED |
| Spanish | 48 | 0 | 0 | 48 | 0 | SOURCE_ROOT_NOT_FOUND |
| French | 48 | 48 | 48 | 0 | 0 | RESOLVED |

Totals:

```text
expectedTotal: 660
availableValidTotal: 601
selectedTotal: 601
missingOrInvalidTotal: 60
extraAvailableTotal: 1
spanishSourcePresent: false
```

## Preflight

Full catalog preflight:

```text
RESOLVED: 345
STAGE_UNRESOLVED: 256
blockingCount: 256
blockedForRealImport: true
```

The 256 unresolved Stage mappings are reported and block those Units from real import.

## Full package-aware dry-run

Command path:

```text
server.export_scorm_batch_to_flw(
  D:\WinPro.Delta\Projects\SmartCourses,
  batchAllUnits=true,
  batchFlwImportMode=overwrite,
  flwDryRun=true
)
```

Result:

```text
elapsed: 1714.98 seconds
exported packages: 601
artifact size: about 18.1 GB
Stage groups: 26
Stage Courses: 24
reused Stage Courses: 3
would create Stage Courses: 20
legacy Unit Courses found: 18
Unit Sections: 601
would create Unit Sections: 326
reused Unit Sections: 19
blocked Units: 256
SCORM created: 326
SCORM updated: 1
SCORM unchanged: 18
SCORM failures/blockers: 256
manual content preserved: 345
attempts preserved: 345
```

Artifacts:

```text
D:\WinPro.Delta\Projects\SmartCourses\_s7_full_catalog_dryrun_exports\flw_batch_20260824_090103_754253\batch_manifest.json
D:\WinPro.Delta\Projects\SmartCourses\_s7_full_catalog_dryrun_exports\flw_batch_20260824_090103_754253\batch_flw_import_report.json
```

## Interpretation

The dry-run status is `FAILED` because S7 correctly blocks unresolved Stage targets. This is not a batch logic failure. It proves the full catalog is enumerated, grouped, exported, and reported without silently skipping invalid targets.

No production Moodle mutation was performed by the full catalog dry-run.

