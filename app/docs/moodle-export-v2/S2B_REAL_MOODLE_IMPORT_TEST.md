# S2B Real Moodle Import Test

Created: 2026-08-23
Updated: 2026-08-23

## Status

```text
PASS
```

Moodle accepted, parsed, and launched the generated multi-SCO SCORM package through the installed Moodle SCORM module APIs and normal browser player. The previously blocked browser/player tests were rerun against the normal trusted HTTPS URL without bypassing certificate validation.

## Moodle version

```text
Moodle 5.1.5 (Build: 20260608)
Branch 501
mod_scorm version 2025100601
wwwroot = https://main.flw.com
```

## Final browser/player fixture

```text
Package: C:\Users\com\Documents\Estimation Speaking\adventure_scorm_gui\verification_exports\s2b_closure_fixed\REW-U023-S2B-Browser-Verification-Unit-SCORM12-20260823_233429.zip
Package SHA-256: 97b5ed63ac77aeb23e1a1ad1903a73ff64bf337b7174273ada69b1a134427772
Content SHA-256: b5b74572112d13a59fc9b576b414628eb0e6ebab4b7fb517b851c48a8545b827
Temporary course id: 196
Temporary user id: 20
cmid: 2087
scorm id: 67
Attempt id: 57
```

Expected and parsed SCO count:

```text
10 / 10
```

Stable identifier to Moodle `scorm_scoes.id`:

```json
{
  "FLW_REW_U023_VOCAB": 691,
  "FLW_REW_U023_L01": 692,
  "FLW_REW_U023_L02": 693,
  "FLW_REW_U023_L03": 694,
  "FLW_REW_U023_L04": 695,
  "FLW_REW_U023_L05": 696,
  "FLW_REW_U023_L06": 697,
  "FLW_REW_U023_L07": 698,
  "FLW_REW_U023_WATCH": 699,
  "FLW_REW_U023_RESULT": 700
}
```

## HTTPS / browser result

```text
https://main.flw.com opened normally.
No certificate warning appeared.
No ignoreHTTPSErrors, certificate interstitial bypass, TLS bypass, or --ignore-certificate-errors was used.
```

## Import/parser result

```text
Package import: PASS, with verification-helper file-pool prewarm
SCORM parser: PASS
Expected SCO rows: 10
Parsed SCO rows: 10
Normal Moodle player launch: PASS
```

The fixture helper prewarms Moodle file-pool hashes before calling Moodle's normal module creation/parser path to avoid the intermittent Windows file-pool rename failure previously observed on this local Moodle install.

## Moodle native SCORM settings

Final test activity settings:

```json
{
  "skipview": 2,
  "hidetoc": 3,
  "nav": 0,
  "displaycoursestructure": 0,
  "displayattemptstatus": 0,
  "hidebrowse": 1
}
```

Runtime browser verification also confirmed Moodle native `#scorm_toc`, `#scorm_tree`, and `#scorm_navpanel` were hidden while `iframe#scorm_object` remained visible.
