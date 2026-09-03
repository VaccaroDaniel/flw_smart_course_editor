from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


SMARTCOURSES_ROOT = Path(r"D:\WinPro.Delta\Projects\SmartCourses")
WORLD_ROOTS = (
    ("01-Adventure", "AEW", 72),
    ("02-Real", "REW", 108),
    ("03-Russian", "RUW", 120),
    ("04-Chinese", "CHW", 132),
    ("05-German", "GEW", 60),
    ("06-Japanese", "JPW", 60),
    ("08-French", "FW", 48),
)


def read_zip_index(zip_path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(zip_path) as package:
        names = [name.replace("\\", "/") for name in package.namelist()]
        if "index.html" in names:
            member = "index.html"
        else:
            candidates = [name for name in names if name.lower().endswith("/index.html")]
            if not candidates:
                return "", ""
            member = sorted(candidates, key=lambda value: (value.count("/"), value.lower()))[0]
        raw = package.read(member)
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), member
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), member


def source_archives(root: Path, maximum_unit: int) -> tuple[list[tuple[str, Path]], dict[str, list[str]]]:
    selected: dict[str, Path] = {}
    duplicates: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(root.glob("*.zip"), key=lambda item: item.name.lower()):
        number = server.unit_number_from_name(path.name)
        if not number or int(number) > maximum_unit:
            continue
        if number in selected:
            duplicates[number].append(path.name)
            continue
        selected[number] = path
    return sorted(selected.items()), dict(duplicates)


def predicted_scos(source_html: str, world_code: str, unit_number: str) -> tuple[list[dict], str]:
    identity = {
        "unitId": f"{world_code}-U{unit_number}",
        "unitNumber": unit_number,
        "worldCode": world_code,
    }
    scos: list[dict] = []
    structured = bool(server.find_json_object_span(source_html, "window.UNIT_DATA="))
    if structured:
        data = server.extract_json_object(source_html, "window.UNIT_DATA=")
        fixed = server.unit_fixed_sections(data)
        for section in [item for item in fixed if item["section"] == "words"]:
            sco = {"kind": section["section"], "id": section["id"], "title": section["title"]}
            server.enrich_sco_with_identity(sco, identity)
            scos.append(sco)
        lessons = data.get("lessons") if isinstance(data.get("lessons"), list) else []
        for index_number, lesson in enumerate(lessons, start=1):
            if not isinstance(lesson, dict):
                continue
            lesson_id = str(lesson.get("id") or f"lesson-{index_number}").strip() or f"lesson-{index_number}"
            title = str(lesson.get("title") or f"Lesson {index_number}").strip()
            sco = {"kind": "lesson", "id": lesson_id, "title": f"Lesson {index_number}: {title}"}
            server.enrich_sco_with_identity(sco, identity, index_number)
            scos.append(sco)
        for section in [item for item in fixed if item["section"] != "words"]:
            sco = {"kind": section["section"], "id": section["id"], "title": section["title"]}
            server.enrich_sco_with_identity(sco, identity)
            scos.append(sco)
        return scos, "structured-unit-data"

    sections = server.generic_sco_sections(source_html)
    for index_number, section in enumerate(sections, start=1):
        sco = {
            "kind": section.get("kind") or "section",
            "id": section["id"],
            "title": section["title"],
            "source": section.get("source") or "",
            "identityKind": section.get("identityKind") or "",
            "identitySourceId": section.get("identitySourceId") or "",
        }
        server.enrich_sco_with_identity(sco, identity, index_number)
        scos.append(sco)
    if scos:
        return scos, str(scos[0].get("source") or "generic")
    fallback = server.unit_sco_identity(identity, "Unit")
    return [{"kind": "unit", "id": f"unit-{unit_number}", **fallback}], "whole-unit-fallback"


def independent_major_targets(source_html: str) -> dict:
    href_ids = []
    for value in re.findall(r"<a\b[^>]*\bhref\s*=\s*['\"]#([^'\"]+)['\"]", source_html, flags=re.I):
        if server.section_id_is_safe(value) and value not in href_ids:
            href_ids.append(value)
    lesson_ids = []
    for value in re.findall(r"\bid\s*=\s*['\"]((?:l|lesson-?)\d{1,2})['\"]", source_html, flags=re.I):
        if value.lower() not in {item.lower() for item in lesson_ids}:
            lesson_ids.append(value)
    station_ids: list[str] = []
    station_block = re.search(r"\bconst\s+stations\s*=\s*\[(.*?)\]\s*;", source_html, flags=re.I | re.S)
    if station_block:
        pair_ids = [
            match.group(2)
            for match in re.finditer(
                r"\[\s*(['\"])([A-Za-z0-9_-]+)\1\s*,\s*(['\"])(.*?)\3\s*\]",
                station_block.group(1),
                flags=re.S,
            )
        ]
        values = pair_ids or re.findall(r"['\"]([A-Za-z0-9_-]+)['\"]", station_block.group(1))
        for value in values:
            if value not in station_ids:
                station_ids.append(value)
    generated_lessons = sorted({int(value) for value in re.findall(r"\blesson\(\s*(\d+)\s*,", source_html)})
    return {
        "hrefIds": href_ids,
        "lessonIds": lesson_ids,
        "stationIds": station_ids,
        "generatedLessonNumbers": generated_lessons,
    }


def load_scorm_map(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("unitScormActivities", {}) if isinstance(data, dict) else {}


def audit(smartcourses_root: Path, scorm_map_path: Path) -> dict:
    deployed = load_scorm_map(scorm_map_path)
    rows: list[dict] = []
    duplicate_archives: dict[str, dict] = {}
    for root_name, world_code, maximum_unit in WORLD_ROOTS:
        root = smartcourses_root / root_name
        archives, duplicates = source_archives(root, maximum_unit)
        if duplicates:
            duplicate_archives[root_name] = duplicates
        for unit_number, archive in archives:
            source_html, index_member = read_zip_index(archive)
            scos, detector = predicted_scos(source_html, world_code, unit_number)
            predicted = [str(sco.get("scoIdentifier") or "") for sco in scos]
            map_key = f"{world_code}-U{unit_number}-UNITSCORM"
            map_entry = deployed.get(map_key) if isinstance(deployed.get(map_key), dict) else {}
            current = list(map_entry.get("componentScoIdentifiers") or [])
            targets = independent_major_targets(source_html)
            duplicate_predicted = sorted(
                identifier for identifier, count in collections.Counter(predicted).items() if count > 1
            )
            reasons: list[str] = []
            if not source_html:
                reasons.append("SOURCE_INDEX_MISSING")
            if duplicate_predicted:
                reasons.append("DUPLICATE_PREDICTED_SCO_IDENTITY")
            if not current:
                reasons.append("NOT_CURRENTLY_MAPPED")
            elif current != predicted:
                reasons.append("DEPLOYED_STRUCTURE_DIFFERS_FROM_CURRENT_DETECTOR")
            if detector == "whole-unit-fallback" and (
                len(targets["hrefIds"]) >= 2
                or len(targets["lessonIds"]) >= 2
                or len(targets["stationIds"]) >= 2
                or len(targets["generatedLessonNumbers"]) >= 2
            ):
                reasons.append("WHOLE_UNIT_FALLBACK_WITH_MULTIPLE_MAJOR_TARGETS")
            if detector == "real-world-checkpoint" and len(scos) != len(targets["stationIds"]):
                reasons.append("REAL_STATION_COUNT_MISMATCH")
            if detector == "german-world-generated" and len(targets["generatedLessonNumbers"]) != 7:
                reasons.append("GERMAN_GENERATED_LESSON_COUNT_UNEXPECTED")
            if detector == "chinese-world" and targets["lessonIds"] and not any(
                str(sco.get("kind")) == "lesson" for sco in scos
            ):
                reasons.append("CHINESE_LESSONS_NOT_DETECTED")
            rows.append(
                {
                    "unitId": f"{world_code}-U{unit_number}",
                    "worldRoot": root_name,
                    "unit": unit_number,
                    "archive": str(archive),
                    "indexMember": index_member,
                    "detector": detector,
                    "predictedScoCount": len(predicted),
                    "deployedScoCount": len(current),
                    "predictedScoIdentifiers": predicted,
                    "deployedScoIdentifiers": current,
                    "currentCmid": map_entry.get("currentCmid"),
                    "currentScormId": map_entry.get("currentScormId"),
                    "currentRevision": map_entry.get("currentRevision"),
                    "majorTargets": targets,
                    "reasons": reasons,
                    "requiresDeployment": bool(current and current != predicted),
                    "detectorError": any(
                        reason
                        in {
                            "SOURCE_INDEX_MISSING",
                            "DUPLICATE_PREDICTED_SCO_IDENTITY",
                            "WHOLE_UNIT_FALLBACK_WITH_MULTIPLE_MAJOR_TARGETS",
                            "REAL_STATION_COUNT_MISMATCH",
                            "GERMAN_GENERATED_LESSON_COUNT_UNEXPECTED",
                            "CHINESE_LESSONS_NOT_DETECTED",
                        }
                        for reason in reasons
                    ),
                }
            )
    profile_counts = collections.Counter(row["detector"] for row in rows)
    deployment_rows = [row for row in rows if row["requiresDeployment"]]
    detector_errors = [row for row in rows if row["detectorError"]]
    by_world = {}
    for root_name, _, _ in WORLD_ROOTS:
        world_rows = [row for row in rows if row["worldRoot"] == root_name]
        by_world[root_name] = {
            "audited": len(world_rows),
            "requiresDeployment": sum(row["requiresDeployment"] for row in world_rows),
            "detectorErrors": sum(row["detectorError"] for row in world_rows),
            "profiles": dict(sorted(collections.Counter(row["detector"] for row in world_rows).items())),
        }
    return {
        "schemaVersion": 1,
        "scope": "Seven production worlds; German U061-U072 excluded; Chinese U134 excluded",
        "smartcoursesRoot": str(smartcourses_root),
        "scormMapPath": str(scorm_map_path),
        "auditedUnitCount": len(rows),
        "detectorErrorCount": len(detector_errors),
        "requiresDeploymentCount": len(deployment_rows),
        "profiles": dict(sorted(profile_counts.items())),
        "byWorld": by_world,
        "duplicateArchives": duplicate_archives,
        "detectorErrors": detector_errors,
        "deploymentCandidates": deployment_rows,
        "units": rows,
    }


def markdown_report(report: dict) -> str:
    lines = [
        "# SCORM section-detection audit",
        "",
        f"- Scope: {report['scope']}",
        f"- Audited Units: {report['auditedUnitCount']}",
        f"- Current detector errors: {report['detectorErrorCount']}",
        f"- Deployed structures differing from the corrected detector: {report['requiresDeploymentCount']}",
        "",
        "## World summary",
        "",
        "| World | Audited | Detector errors | Needs deployment | Profiles |",
        "|---|---:|---:|---:|---|",
    ]
    for world, row in report["byWorld"].items():
        profiles = ", ".join(f"{key}: {value}" for key, value in row["profiles"].items())
        lines.append(
            f"| {world} | {row['audited']} | {row['detectorErrors']} | {row['requiresDeployment']} | {profiles} |"
        )
    lines.extend(["", "## Deployment candidates", ""])
    if report["deploymentCandidates"]:
        lines.extend(
            [
                "| Unit | Detector | Deployed SCOs | Corrected SCOs | cmid | Revision |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in report["deploymentCandidates"]:
            lines.append(
                f"| {row['unitId']} | {row['detector']} | {row['deployedScoCount']} | "
                f"{row['predictedScoCount']} | {row.get('currentCmid') or ''} | {row.get('currentRevision') or ''} |"
            )
    else:
        lines.append("None.")
    lines.extend(["", "## Current detector errors", ""])
    if report["detectorErrors"]:
        for row in report["detectorErrors"]:
            lines.append(f"- {row['unitId']}: {', '.join(row['reasons'])}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source Unit section detection against the deployed Moodle SCORM map.")
    parser.add_argument("--smartcourses-root", type=Path, default=SMARTCOURSES_ROOT)
    parser.add_argument("--scorm-map", type=Path, default=APP_DIR / "flw_moodle_unit_scorm_map.json")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    report = audit(args.smartcourses_root.resolve(), args.scorm_map.resolve())
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("auditedUnitCount", "detectorErrorCount", "requiresDeploymentCount", "byWorld")}, ensure_ascii=False, indent=2))
    return 1 if report["detectorErrorCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
