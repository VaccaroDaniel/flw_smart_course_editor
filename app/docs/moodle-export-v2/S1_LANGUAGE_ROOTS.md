# S1 Language Roots

Created: 2026-08-23

Gate: S1 — Deployment Metadata + Course Map

## Configured roots

S1 configures all current/future source roots:

| Source root code | World code | Local S1 source status |
|---|---:|---|
| `01-adventure` | `AEW` | Found |
| `02-real` | `REW` | Found |
| `03-russian` | `RUW` | Found |
| `04-chinese` | `CHW` | Found |
| `05-german` | `GEW` | Found |
| `06-japanese` | `JPW` | Found |
| `07-spanish` | `SW` | `SOURCE_ROOT_NOT_FOUND` |
| `08-french` | `FW` | Found |

## Actual source roots scanned

Base:

```text
D:\WinPro.Delta\Projects\SmartCourses
```

| Root | Units | S1 status |
|---|---:|---|
| `01-Adventure` | 72 | Found |
| `02-Real` | 108 | Found |
| `03-Russian` | 120 | Found |
| `04-Chinese` | 133 | Found |
| `05-German` | 60 | Found |
| `06-Japanese` | 60 | Found |
| `08-French` | 48 | Found |
| Spanish | 0 | `SOURCE_ROOT_NOT_FOUND` |

## Actual deployment-stage scan

Read-only S1 metadata scan result:

| World | Resolved by S1 metadata/config | Unresolved |
|---|---:|---:|
| AEW | 69 | 3 |
| REW | 108 | 0 |
| RUW | 0 | 120 |
| CHW | 0 | 133 |
| GEW | 60 | 0 |
| JPW | 60 | 0 |
| FW | 48 | 0 |
| SW | 0 | source absent |

Adventure unresolved examples:

```text
AEW-U048 — blank source stage metadata
AEW-U060 — blank source stage metadata
AEW-U072 — blank source stage metadata
```

Russian and Chinese units currently lack authoritative stage metadata or S1 course-map rules, so all are `STAGE_UNRESOLVED`.

S1 deliberately does not invent ranges for Russian/Chinese/Adventure review units.
