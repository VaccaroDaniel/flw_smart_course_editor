# S0 Moodle / SCORM API Findings

Created: 2026-08-23

Gate: S0 — Current Implementation Freeze

## Installed Moodle version

Installed Moodle path inspected:

```text
D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\public
```

Moodle version from `version.php`:

```text
$version  = 2025100605.00
$release  = '5.1.5 (Build: 20260608)'
$branch   = '501'
$maturity = MATURITY_STABLE
```

SCORM plugin version from `mod/scorm/version.php`:

```text
$plugin->version   = 2025100601
$plugin->requires  = 2025092600
$plugin->component = 'mod_scorm'
```

Moodle config loader:

```text
D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\public\config.php
```

Real config file:

```text
D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\config.php
```

Non-secret config facts:

```text
dbtype  = pgsql
prefix  = mdl_
wwwroot = https://192.168.129.79
dataroot = D:\Dev\MoodleWindowsInstaller-latest-501\server/moodledata
```

Normal Moodle CLI bootstrap currently fails:

```text
Fatal error: $CFG->dataroot is not writable, admin has to fix directory permissions! Exiting.
```

S0 used direct read-only PostgreSQL queries through PHP `pgsql` to verify installed tables. This does not replace the need to fix dataroot before real Moodle import/tracking tests.

## Installed Moodle SCORM source inspected

Core files inspected:

```text
mod/scorm/lib.php
mod/scorm/locallib.php
mod/scorm/mod_form.php
mod/scorm/player.php
mod/scorm/loadSCO.php
mod/scorm/datamodels/scormlib.php
```

## Creating a SCORM activity

Supported Moodle module creation path:

- normal Moodle activity creation is via `add_moduleinfo($moduleinfo, $course)`;
- SCORM module-specific creation is handled by `scorm_add_instance($scorm, $mform = null)` in `mod/scorm/lib.php`.

Relevant source facts:

- `scorm_add_instance()` inserts into `scorm`;
- sets `course_modules.instance`;
- saves the uploaded local package into file storage;
- calls `scorm_parse($record, true)`;
- updates grade item/calendar/completion.

Current editor importer uses this path:

```text
scripts/import_scorm_pilot_to_moodle.php
→ import_item()
→ build_scorm_moduleinfo()
→ add_moduleinfo()
→ Moodle scorm_add_instance()
```

## Updating an existing SCORM package

Supported Moodle module update path:

- update existing activity with Moodle module update APIs;
- SCORM module-specific update is `scorm_update_instance($scorm, $mform = null)` in `mod/scorm/lib.php`.

Relevant source facts:

- `scorm_update_instance()` keeps the existing SCORM instance id through `$scorm->id = $scorm->instance`;
- for local packages, it deletes/replaces the `mod_scorm/package` file area;
- updates the `scorm` DB record;
- calls `scorm_parse($scorm, (bool)$scorm->updatefreq)`;
- updates grades/calendar/completion.

S5 must prefer Moodle's supported update path rather than editing SCORM tables directly.

## Preserving existing cmid

Likely supported when using Moodle's activity update flow against an existing course module:

- existing `course_modules.id` is the cmid;
- `scorm_update_instance()` updates the SCORM instance, not the course module identity;
- the editor must resolve the existing Unit SCORM by stable `course_modules.idnumber` / mapping and pass the existing `coursemodule` / `instance` to Moodle's update flow.

This still requires a real Moodle integration test after dataroot is writable.

## Preserving learner attempts/tracking

SCORM tracking is stored by SCORM attempt and SCO id in this Moodle 5.1.5 install.

Relevant tables confirmed in live DB:

```text
scorm
scorm_attempt
scorm_element
scorm_scoes
scorm_scoes_data
scorm_scoes_value
scorm_seq_mapinfo
scorm_seq_objective
scorm_seq_rolluprule
scorm_seq_rolluprulecond
scorm_seq_rulecond
scorm_seq_ruleconds
```

Relevant source:

- `scorm_insert_track()` writes/updates `scorm_scoes_value`;
- `scorm_get_attempt()` creates/gets the attempt row;
- `scorm_get_sco_value()` reads by `scoid`, `userid`, element, and attempt;
- `scorm_delete_tracks()` deletes values and may delete attempts depending on parameters.

Critical package-update behavior from `mod/scorm/datamodels/scormlib.php`:

- when a new manifest SCO has the same `identifier` as an existing `scorm_scoes` row, Moodle updates that row and keeps the existing id so user tracks remain attached;
- when an old `scorm_scoes` row is no longer present by identifier, Moodle deletes that SCO and calls `scorm_delete_tracks($scorm->id, $olditem->id)`.

S5 implication:

```text
Stable SCO identifiers are mandatory.
Renaming/removing SCO identifiers during package update can delete historical SCO tracking.
```

If a package update cannot preserve stable SCO ids, the later importer must use a safe supersession strategy instead of destructive in-place update.

## Launching/switching between SCOs

Supported player endpoints:

```text
/mod/scorm/player.php
/mod/scorm/loadSCO.php
```

`player.php` requires:

```text
scoid
```

and accepts:

```text
cm
a
mode
currentorg
newattempt
display
```

Relevant source facts:

- `player.php` validates the requested `scoid` using `scorm_check_launchable_sco()`;
- it stores active SCO/attempt details in session;
- it frames `loadSCO.php?id=<cmid>&scoid=<scoid>&mode=<mode>`;
- it calls `scorm_insert_track(..., 'x.start.time', time())`;
- `loadSCO.php` also requires `scoid`, resolves the SCO launch URL with `scorm_get_sco_and_launch_url()`, inserts `x.start.time`, triggers the SCO launched event, then redirects/loads the content.

S2B implication:

```text
FLW in-package Previous/Next/lesson-list navigation must use Moodle's player/loadSCO mechanism or a verified equivalent that changes Moodle's active scoid.
Directly linking from one SCO HTML file to another is not acceptable unless proven to preserve active Moodle SCO tracking.
```

## Hiding/minimizing native Moodle SCORM TOC/structure

Supported SCORM settings inspected in `mod/scorm/mod_form.php`:

```text
skipview
displaycoursestructure
hidetoc
nav
navpositionleft
navpositiontop
displayattemptstatus
hidebrowse
popup
auto
autocommit
forcenewattempt
lastattemptlock
```

SCORM constants inspected in `mod/scorm/locallib.php`:

```text
SCORM_SKIPVIEW_NEVER  = 0
SCORM_SKIPVIEW_FIRST  = 1
SCORM_SKIPVIEW_ALWAYS = 2
```

Native TOC options are provided by `scorm_get_hidetoc_array()` and used by `player.php` and `scorm_get_toc()`.

Current editor importer settings in `build_scorm_moduleinfo()` include:

```text
displaycoursestructure = cfg default, fallback 0
skipview = cfg default, fallback SCORM_SKIPVIEW_FIRST
hidetoc = cfg default, fallback SCORM_TOC_SIDE
nav = cfg default, fallback SCORM_NAV_UNDER_CONTENT
displayattemptstatus = cfg default, fallback SCORM_DISPLAY_ATTEMPTSTATUS_ALL
popup = 0
```

S5 implication:

- later implementation must explicitly choose Moodle-supported values that minimize native structure/TOC and attempt/status dominance;
- exact values should be tested in the installed Moodle UI/player;
- current fallback `SCORM_TOC_SIDE` is not aligned with the frozen v8 learner-navigation target.

## Skipping the native SCORM content-structure entry page

`scorm_simple_play()` in `mod/scorm/locallib.php` implements skip-view behavior.

Source behavior:

- if user has report capability, skip-view is disabled so reports can be seen;
- when `skipview >= SCORM_SKIPVIEW_FIRST`, Moodle computes a launch target and can redirect directly to `player.php`;
- `SCORM_SKIPVIEW_ALWAYS` always skips where supported;
- `SCORM_SKIPVIEW_FIRST` skips on first access / when no tracks exist according to Moodle's conditions.

S5 implication:

```text
Use `skipview` deliberately. Do not guess; set/test installed Moodle 5.1.5 behavior.
```

## SCORM resume behavior

Installed Moodle behavior observed from source:

- `scorm_get_last_attempt($scormid, $userid)` returns the latest attempt number, defaulting to `1`;
- `scorm_simple_play()` calls `scorm_get_toc()` and may launch the last incomplete SCO when `forcenewattempt` is not always;
- SCORM data elements such as `cmi.core.lesson_location` and `cmi.suspend_data` are stored as `scorm_element` + `scorm_scoes_value` entries by `scorm_insert_track()`;
- attempt separation is represented in `scorm_attempt`.

S2B/S5 implication:

- stable component identity should be encoded in SCORM `lesson_location` / `suspend_data` payload if Moodle's native last-incomplete behavior is insufficient;
- relaunch/resume must be tested with real learner attempts after dataroot is writable.

## Existing FLW/Moodle mapping facilities

Installed local FLW plugins found:

```text
local_flwaiassessment 2026061400
local_flwcupkp        2026081416
local_flwexam         2026081400
local_flwkp           2026061200
local_flwmedia        2026071002
local_flwplacement    2026072101
local_flwtextbookimport 2026081202
mod_flwaispeaking     2026061501
mod_flwvrroom         2026081501
mod_scorm             2025100601
```

Live DB confirmed relevant FLW tables:

```text
flwcupkp_framework
flwcupkp_object
flwcupkp_object_map
flwcupkp_evidence
flwcupkp_state
local_flwkp_languages
local_flwkp_levels
local_flwkp_units
local_flwkp_points
local_flwkp_mappings
```

Mapping-related counts from live DB:

```text
flwcupkp_framework_total: 2
flwcupkp_framework_with_courseid: 0
flwcupkp_object_total: 12
flwcupkp_object_with_courseid: 12
flwcupkp_object_with_cmid: 12
flwcupkp_object_with_unitcode: 12
flwcupkp_object_map_total: 21
local_flwkp_mappings_total: 0
course_idnumber_flw: 63
course_sections_with_flw_marker: 0
course_modules_flw_idnumber: 92
```

Classification:

| Mapping need | Existing support | S0 classification |
|---|---|---|
| World+Stage → Moodle Course | `flwcupkp_framework` has `coursecode`, `cefrrange`, `courseid`, but current rows have `courseid = null`; many old FLW course shortnames/idnumbers exist | Partial / not canonical for v8 deployment |
| Unit → Moodle Section | No table or marker found; `course_sections_with_flw_marker = 0` | Missing |
| Activity → cmid | `flwcupkp_object` has `externalid`, `courseid`, `unitcode`, `lesson`, `objecttype`, `cmid`, `sourceid`; 12 live rows have cmid | Partial; reusable conceptually for learning objects, not yet a Unit SCORM deployment map |
| KP/object evidence mapping | `flwcupkp_object_map`, `flwcupkp_evidence`, `local_flwkp_mappings` schema exists | Exists for C-UP-KP/KP evidence, not a replacement for deployment identity |

S1/S5 implication:

```text
Do not invent a separate architecture if existing FLW tables can be reused safely, but do not treat current C-UP-KP object mappings as a complete deployment map.
Need a v8 deployment identity layer or validated extension for:
World+Stage Course,
Unit Section,
Unit SCORM cmid,
component/SCO identifier.
```

