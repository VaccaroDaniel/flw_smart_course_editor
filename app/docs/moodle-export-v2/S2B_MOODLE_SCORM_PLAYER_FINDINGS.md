# S2B Moodle SCORM Player Findings

Created: 2026-08-23

## Installed Moodle

Installed Moodle path:

```text
D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\public
```

Version:

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
```

SCORM plugin:

```text
mod_scorm version 2025100601
```

Normal CLI bootstrap now succeeds in this environment:

```text
bootstrapped=5.1.5 (Build: 20260608)
```

## Player launch/switching mechanism

Installed source confirms Moodle launches an active component through the SCORM player with a numeric Moodle `scoid`.

Observed source:

```text
mod/scorm/player.php
  required_param('scoid', PARAM_INT)
  scorm_check_launchable_sco($scorm, $scoid)
  $SESSION->scorm->scoid = $sco->id
  iframe src = loadSCO.php?id=<cmid>&scoid=<scoid>&mode=<mode>

mod/scorm/loadSCO.php
  required_param('scoid', PARAM_INT)
```

`player.php` also calls:

```text
scorm_get_adlnav_json(...)
M.mod_scorm.init(..., $sco->id, $adlnav)
```

`locallib.php` builds `adlnav` entries that include:

```text
identifier
launch
title
url
prevscoid
nextscoid
```

`module.js` keeps that parsed navigation map inside the `M.mod_scorm.init` closure and exposes Moodle previous/next helpers, but it does not expose a clean public arbitrary-identifier launcher. Therefore S2B resolves the stable FLW SCO identifier from the Moodle player page's serialized `adlnav` data and launches Moodle's supported `player.php` endpoint with the numeric `scoid`.

## Native Moodle SCORM TOC/settings

Installed source confirms these constants/settings:

```text
SCORM_TOC_SIDE      = 0
SCORM_TOC_HIDDEN    = 1
SCORM_TOC_POPUP     = 2
SCORM_TOC_DISABLED  = 3

SCORM_NAV_DISABLED      = 0
SCORM_NAV_UNDER_CONTENT = 1
SCORM_NAV_FLOATING      = 2

SCORM_DISPLAY_ATTEMPTSTATUS_NO    = 0
SCORM_DISPLAY_ATTEMPTSTATUS_ALL   = 1
SCORM_DISPLAY_ATTEMPTSTATUS_MY    = 2
SCORM_DISPLAY_ATTEMPTSTATUS_ENTRY = 3

SCORM_SKIPVIEW_NEVER  = 0
SCORM_SKIPVIEW_FIRST  = 1
SCORM_SKIPVIEW_ALWAYS = 2
```

Importer defaults changed for S2B:

```php
$data->skipview = SCORM_SKIPVIEW_ALWAYS;
$data->hidebrowse = 1;
$data->hidetoc = SCORM_TOC_DISABLED;
$data->nav = SCORM_NAV_DISABLED;
$data->displaycoursestructure = 0;
$data->displayattemptstatus = SCORM_DISPLAY_ATTEMPTSTATUS_NO;
```

These settings keep Moodle's SCORM player/tracking active while preventing the native package structure from becoming the primary learner navigator.

## Real Moodle blocker

A controlled import test reached Moodle but failed during file storage:

```text
Cannot create local file pool file. Please verify permissions in dataroot and available disk space.
```

The temporary hidden test course was deleted. Because the package could not be imported into Moodle, browser/player navigation and tracking tests could not be completed.

