# S8 Legacy Protection

Status: PASS  
Date: 2026-08-24

## Legacy Unit Course policy

Legacy Moodle Unit Courses may still exist from the old architecture:

FLW Unit -> Moodle Course

S8 does not delete, clear, adopt, move, or merge these courses during Rebuild Selected FLW Scope.

S8 only detects and reports them as:

- `LEGACY_UNIT_COURSE_PRESENT`

The canonical target remains:

FLW World + Deployment Stage -> Moodle Course  
FLW Unit -> Moodle Section

## Verified disposable legacy fixture

Created legacy course:

- Moodle course id: 206
- fullname: `S8 Disposable Test World Unit 001 Legacy Course`
- idnumber: `S8_LEGACY_S80824151148_U001`
- category: 143
- visible: 0

Preview result for canonical U001:

- SCORM action: `UNCHANGED`
- additional statuses: `MANUAL_CONTENT_PRESENT`, `LEGACY_UNIT_COURSE_PRESENT`
- legacy course count: 1
- legacy courses detected: 1

Reports:

- `verification_exports/s8_disposable_rebuild/s8_legacy_course_fixture_report.json`
- `verification_exports/s8_disposable_rebuild/s8_legacy_detection_preview_report.json`

## Production protection

The old numeric-ID clear behavior is not part of normal S8 production import. S8 never reports "courses deleted" as a normal success metric.

