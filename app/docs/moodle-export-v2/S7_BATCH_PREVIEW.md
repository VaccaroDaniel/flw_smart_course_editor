# S7 Batch Preview

Gate: S7 — Moodle Course / Unit-Section mapping preview  
Created: 2026-08-24

## Preview purpose

The S7 preview shows the Moodle destination before mutation:

```text
FLW World -> Deployment Stage / Moodle Course -> FLW Unit / Moodle Section -> Unit SCORM
```

The preview is intentionally a mapping preview. It does not require SCORM ZIP creation.

## Package-aware diff

Because mapping preview does not create packages, SCORM package hash comparison is not available in preview-only mode.

For those rows, the importer returns:

```text
SCORM_DIFF_REQUIRES_PACKAGE
```

To see create/update/unchanged SCORM package decisions, run batch deploy with `Dry run only` enabled.

## UI changes

The batch preview button is labelled:

```text
Preview Moodle Course / Unit-Section Mapping
```

The result area displays:

- World/Stage groups;
- catalog expected/available/selected totals;
- Stage Course decisions;
- Unit Section decisions;
- SCORM create/update/unchanged/superseded counts;
- blocker/conflict/failure counts;
- manual content and attempt preservation counts.

## Full-catalog preview result

Preview artifact:

```text
verification_exports/s7_full_catalog_preview/flw_preview_20260824_085934_597835/batch_course_preview_report.json
```

Observed:

```text
selected Units: 601
Stage groups: 26
Stage Courses: 24
reused Stage Courses: 3
would create Stage Courses: 20
Unit Sections: 601
would create Unit Sections: 326
reused Unit Sections: 19
blocked Units: 256
SCORM_DIFF_REQUIRES_PACKAGE rows: 601
```

The `FAILED` public status in this preview is correct because unresolved Stage mappings are blocking findings, not silent omissions.

