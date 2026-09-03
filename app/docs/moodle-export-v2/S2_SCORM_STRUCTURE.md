# S2 SCORM Structure

Created: 2026-08-23

Gate: S2 — Stable SCORM Structure / Package / SCO Identity

## Frozen structure

S2 preserves the existing working multi-SCO exporter while freezing the Moodle-targeted FLW structure:

```text
1 FLW Unit
→ 1 SCORM 1.2 package

1 substantial lesson/component
→ 1 SCO

micro-activities
→ remain inside parent SCO
```

S2 does not implement S2B navigation or Moodle course/section/module deployment.

## Granularity

Tracked as separate SCOs when present/detected:

- substantial vocabulary component;
- lesson components;
- watch/video component;
- project component when detected in substantial section/profile HTML;
- result/progress/checkpoint component;
- other substantial HTML/profile sections with stable source IDs.

Not tracked as separate SCOs:

- individual questions;
- one practice item;
- vocabulary cards;
- hints;
- feedback blocks;
- short sub-exercises;
- drag/drop or matching item fragments.

## Giant-SCO prevention

Normal structured FLW units continue to produce multiple substantial SCOs. The whole-unit SCO is only included when the user explicitly enables it or when no component SCOs can be detected.

## SCO explosion prevention

Micro-activities are reported in `microActivityMappings` but do not become SCORM `<item>` or `<resource>` nodes.

## Fields added to export reports

```text
manifestSchemaVersion = 2
scormStructureVersion = 2
unitId
scormActivityExternalKey
futureCmidNumber
scormManifestIdentifier
packageSha256
packageContentSha256
componentMappings
microActivityMappings
```

The existing SCORM API wrapper, filtering, preview, unit editing, ZIP handling, and batch framework were preserved.
