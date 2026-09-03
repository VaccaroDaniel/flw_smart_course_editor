from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import traceback
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


PILOT_UNITS = [
    {
        "code": "01-adventure",
        "label": "Adventure",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\01-Adventure",
    },
    {
        "code": "02-real",
        "label": "Real",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\02-Real",
    },
    {
        "code": "03-russian",
        "label": "Russian",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\03-Russian",
    },
    {
        "code": "04-chinese",
        "label": "Chinese",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\04-Chinese",
    },
    {
        "code": "05-german",
        "label": "German",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\05-German",
    },
    {
        "code": "06-japanese",
        "label": "Japanese",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\06-Japanese",
    },
    {
        "code": "08-french",
        "label": "French",
        "root": r"D:\WinPro.Delta\Projects\SmartCourses\08-French",
    },
]


def safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    cleaned = cleaned.strip("_.-")
    return cleaned or "SCORM_PILOT"


def compact_title(parts: list[str]) -> str:
    seen: set[str] = set()
    output: list[str] = []
    for part in parts:
        value = re.sub(r"\s+", " ", str(part or "")).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return " - ".join(output)


def export_one(item: dict, unit: str, stamp: str, export_dir: Path) -> dict:
    root = server.ensure_root(item["root"])
    unit_path = server.unit_dir(root, unit)
    meta = server.index_meta(unit_path)
    validation = server.validate_unit(unit_path)
    title = compact_title([item["label"], f"Unit {unit}", meta.get("title") or unit_path.name])
    identifier = safe_identifier(f"FLW_SMARTCOURSES_PILOT_{item['code']}_U{unit}_{stamp}")
    report = server.export_scorm(
        unit_path,
        {
            "title": title,
            "identifier": identifier,
            "exportDir": str(export_dir),
            "launchFile": "index.html",
            "includeSourceData": False,
            "includeTools": False,
            "includeUnitSco": False,
            "keepTopNavBar": False,
            "autocomplete": True,
        },
    )
    return {
        **item,
        "status": "exported",
        "unit": unit,
        "unitPath": str(unit_path),
        "title": title,
        "metadata": meta,
        "validation": validation,
        "export": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export one pilot SCORM package per SmartCourses language.")
    parser.add_argument("--unit", default="001", help="Unit number to export from each language root.")
    parser.add_argument("--export-dir", default="", help="Output folder. Defaults to adventure_scorm_gui/pilot_exports/<timestamp>.")
    args = parser.parse_args()

    unit_match = re.search(r"(\d{1,3})", args.unit)
    if not unit_match:
        raise SystemExit("Unit number is required, for example --unit=001")
    unit = f"{int(unit_match.group(1)):03d}"

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = Path(args.export_dir).expanduser() if args.export_dir else APP_DIR / "pilot_exports" / stamp
    export_dir = export_dir.resolve()
    export_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    for item in PILOT_UNITS:
        try:
            exported = export_one(item, unit, stamp, export_dir)
            items.append(exported)
            report = exported["export"]
            issues = len(exported.get("validation", {}).get("issues", []))
            print(
                f"[exported] {item['label']}: "
                f"{report['scoCount']} SCOs, {report['zipBytes']:,} bytes, "
                f"{issues} validation issue(s)"
            )
            print(f"           {report['zipPath']}")
        except Exception as exc:  # Keep the pilot report useful even if one language fails.
            failure = {
                **item,
                "status": "failed",
                "unit": unit,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            items.append(failure)
            print(f"[failed] {item['label']}: {exc}", file=sys.stderr)

    manifest = {
        "kind": "smartcourses_scorm_pilot",
        "timestamp": stamp,
        "unit": unit,
        "exportDir": str(export_dir),
        "items": items,
        "successCount": sum(1 for item in items if item.get("status") == "exported"),
        "failureCount": sum(1 for item in items if item.get("status") != "exported"),
    }
    manifest_path = export_dir / "pilot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[manifest] {manifest_path}")
    return 0 if manifest["failureCount"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
