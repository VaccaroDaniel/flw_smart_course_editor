"""Generate disposable S8 safe-rebuild Moodle verification fixtures.

The output is intentionally isolated under verification_exports/s8_disposable_rebuild.
It creates tiny SCORM 1.2 packages plus Smart Course Editor import manifests
with stable FLW identities. The fixtures are not production course content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = REPO_ROOT / "verification_exports" / "s8_disposable_rebuild"
PACKAGE_DIR = BASE_DIR / "packages"
SOURCE_DIR = BASE_DIR / "source"
MAP_DIR = BASE_DIR / "maps"

WORLD_CODE = "S8T"
WORLD_TITLE = "S8 Disposable Test World"
LANGUAGE_CODE = "en"
MOODLE_CATEGORY = 93

COMPONENTS = [
    ("OVERVIEW", "Overview"),
    ("WATCH", "Watch"),
    ("RESULT", "Progress Result"),
]


def stable_run_id() -> str:
    now = datetime.now()
    return "S8" + now.strftime("%m%d%H%M%S")


RUN_ID = stable_run_id()


def clean_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_digest(files: dict[str, bytes]) -> str:
    hasher = hashlib.sha256()
    for name in sorted(files):
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(files[name]).hexdigest().encode("ascii"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def unit_id(unit_number: int) -> str:
    return f"{WORLD_CODE}-{RUN_ID}-U{unit_number:03d}"


def course_key(stage: str) -> str:
    return f"FLW_{WORLD_CODE}_{RUN_ID}_{stage}"


def course_shortname(stage: str) -> str:
    return f"FLW-{WORLD_CODE}-{RUN_ID}-{stage}"


def stable_cmidnumber(unit_number: int) -> str:
    return f"FLW_{WORLD_CODE}_{RUN_ID}_U{unit_number:03d}_UNITSCORM"


def scorm_manifest_identifier(unit_number: int) -> str:
    return f"FLW_{WORLD_CODE}_{RUN_ID}_U{unit_number:03d}_SCORM12"


def component_rows(unit_number: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    parent = unit_id(unit_number)
    for index, (key, title) in enumerate(COMPONENTS, start=1):
        identifier = f"FLW_{WORLD_CODE}_{RUN_ID}_U{unit_number:03d}_{key}"
        rows.append(
            {
                "componentId": f"{parent}-{key}",
                "componentKey": key,
                "componentIdSource": "s8_disposable_fixture",
                "kind": "section",
                "sourceId": key.lower(),
                "title": title,
                "scoIdentifier": identifier,
                "itemIdentifier": identifier,
                "resourceIdentifier": f"{identifier}_RES",
                "launchFile": f"scos/{key.lower()}.html",
                "parentUnitId": parent,
                "trackSeparately": True,
                "displayOrder": index,
                "displayOrderIsCanonical": True,
            }
        )
    return rows


def html_page(title: str, body: str, component_id: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.45; }}
    .pill {{ display: inline-block; padding: .2rem .5rem; border-radius: 999px; background: #e8f1ff; }}
  </style>
</head>
<body data-component-id="{escape(component_id)}">
  <p class="pill">S8 disposable SCORM fixture</p>
  <h1>{escape(title)}</h1>
  <p>{escape(body)}</p>
  <script>
  (function() {{
    function findAPI(win) {{
      var depth = 0;
      while (win && depth < 8) {{
        if (win.API) return win.API;
        if (win.parent === win) break;
        win = win.parent;
        depth++;
      }}
      return null;
    }}
    try {{
      var api = findAPI(window);
      if (api) {{
        api.LMSInitialize("");
        api.LMSSetValue("cmi.core.lesson_status", "completed");
        api.LMSSetValue("cmi.core.lesson_location", "{escape(component_id)}");
        api.LMSSetValue("cmi.core.score.raw", "88");
        api.LMSCommit("");
      }}
    }} catch (e) {{}}
  }})();
  </script>
</body>
</html>
""".encode("utf-8")


def manifest_xml(unit_number: int, revision: str, rows: list[dict[str, object]]) -> bytes:
    manifest_id = scorm_manifest_identifier(unit_number)
    item_xml = []
    resource_xml = []
    for row in rows:
        identifier = str(row["scoIdentifier"])
        resource = str(row["resourceIdentifier"])
        launch_file = str(row["launchFile"])
        title = str(row["title"])
        item_xml.append(
            f"""      <item identifier="{escape(identifier)}" identifierref="{escape(resource)}">
        <title>{escape(title)} {escape(revision)}</title>
      </item>"""
        )
        resource_xml.append(
            f"""    <resource identifier="{escape(resource)}" type="webcontent" adlcp:scormtype="sco" href="{escape(launch_file)}">
      <file href="{escape(launch_file)}"/>
      <file href="index.html"/>
    </resource>"""
        )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{escape(manifest_id)}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG1">
    <organization identifier="ORG1">
      <title>S8 Disposable Unit {unit_number:03d} {escape(revision)}</title>
{os.linesep.join(item_xml)}
    </organization>
  </organizations>
  <resources>
{os.linesep.join(resource_xml)}
  </resources>
</manifest>
"""
    return xml.encode("utf-8")


def make_package(unit_number: int, stage: str, revision: str) -> tuple[Path, str, str, list[dict[str, object]]]:
    rows = component_rows(unit_number)
    files: dict[str, bytes] = {}
    files["imsmanifest.xml"] = manifest_xml(unit_number, revision, rows)
    files["index.html"] = html_page(
        f"S8 Unit {unit_number:03d} {revision}",
        f"This is the root launch page for {unit_id(unit_number)} in {stage}, {revision}.",
        f"{unit_id(unit_number)}-ROOT",
    )
    for row in rows:
        files[str(row["launchFile"])] = html_page(
            f"{row['title']} {revision}",
            f"Stable ComponentID {row['componentId']} rendered by disposable package {revision}.",
            str(row["componentId"]),
        )
    digest = content_digest(files)
    zip_name = f"{unit_id(unit_number)}-{stage}-{revision}-SCORM12.zip"
    zip_path = PACKAGE_DIR / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name)
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[name])
    package_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    return zip_path, package_hash, digest, rows


def make_item(unit_number: int, stage: str, revision: str) -> dict[str, object]:
    zip_path, package_hash, digest, rows = make_package(unit_number, stage, revision)
    unit = f"{unit_number:03d}"
    title = f"S8 Disposable Unit {unit} {revision}"
    source = SOURCE_DIR / f"{unit_id(unit_number)}_{stage}_{revision}"
    source.mkdir(parents=True, exist_ok=True)
    (source / "README.txt").write_text(f"{title}\n", encoding="utf-8")
    metadata = {
        "manifestSchemaVersion": 2,
        "sourceRootCode": "s8-disposable",
        "worldCode": WORLD_CODE,
        "worldTitle": WORLD_TITLE,
        "languageCode": LANGUAGE_CODE,
        "sourceStage": stage,
        "deploymentStageCode": stage,
        "stageResolutionStatus": "RESOLVED",
        "stageResolutionSource": "s8_disposable_fixture",
        "stageResolutionMessage": f"Resolved {unit_id(unit_number)} to {WORLD_CODE}:{stage}.",
        "preflightStatus": "RESOLVED",
        "unitId": unit_id(unit_number),
        "unitNumber": unit,
        "unitSequence": unit_number,
        "unitTitle": title,
        "courseExternalKey": course_key(stage),
        "courseShortname": course_shortname(stage),
        "courseIdnumber": course_key(stage),
        "unitExternalKey": unit_id(unit_number),
        "scormActivityExternalKey": f"{unit_id(unit_number)}-UNITSCORM",
        "moodleCategory": MOODLE_CATEGORY,
        "moodleCategorySource": "s8_disposable_fixture",
        "scormStructureVersion": 2,
        "scormManifestIdentifier": scorm_manifest_identifier(unit_number),
        "futureCmidNumber": stable_cmidnumber(unit_number),
        "packageSha256": package_hash,
        "packageContentSha256": digest,
        "packageIdentifierRule": "S8 disposable stable manifest identity",
        "scoIdentifierRule": "S8 disposable stable SCO identity",
        "componentMappings": rows,
        "microActivityMappings": [],
    }
    export = {
        **metadata,
        "unit": unit,
        "title": title,
        "identifier": scorm_manifest_identifier(unit_number),
        "zipPath": str(zip_path),
        "zipBytes": zip_path.stat().st_size,
        "zipTest": "PASS",
        "manifestAtRoot": True,
        "manifestXmlOk": True,
        "manifestItemCount": len(rows),
        "scoCount": len(rows),
        "launchFile": "index.html",
        "keepTopNavBar": False,
        "flwNavigatorEnabled": True,
        "flwNavigatorPrimary": True,
        "resumeStorage": ["cmi.core.lesson_location", "cmi.suspend_data"],
    }
    return {
        "code": "s8-disposable",
        "label": "S8 Disposable",
        "status": "exported",
        "unit": unit,
        "unitPath": str(source),
        "root": str(SOURCE_DIR),
        "title": title,
        "metadata": {"title": title, "stage": stage, "course": WORLD_TITLE, "unit": unit},
        "validation": {"unit": unit, "title": title, "ok": True, "issues": [], "warnings": [], "missingRefs": []},
        "export": export,
        "manifestSchemaVersion": 2,
        "sourceRootCode": "s8-disposable",
        "worldCode": WORLD_CODE,
        "worldTitle": WORLD_TITLE,
        "languageCode": LANGUAGE_CODE,
        "sourceStage": stage,
        "deploymentStageCode": stage,
        "unitId": unit_id(unit_number),
        "unitNumber": unit,
        "unitSequence": unit_number,
        "unitTitle": title,
        "courseExternalKey": course_key(stage),
        "unitExternalKey": unit_id(unit_number),
        "scormActivityExternalKey": f"{unit_id(unit_number)}-UNITSCORM",
        "preflightStatus": "RESOLVED",
        "stageResolutionStatus": "RESOLVED",
        "stageResolutionMessage": f"Resolved {unit_id(unit_number)} to {WORLD_CODE}:{stage}.",
        "targetMetadata": metadata,
        "scormStructureVersion": 2,
        "scormManifestIdentifier": scorm_manifest_identifier(unit_number),
        "futureCmidNumber": stable_cmidnumber(unit_number),
        "packageSha256": package_hash,
        "packageContentSha256": digest,
        "componentMappings": rows,
        "microActivityMappings": [],
        "batchTarget": {
            "worldCode": WORLD_CODE,
            "deploymentStageCode": stage,
            "unitId": unit_id(unit_number),
            "unitSequence": unit_number,
            "courseExternalKey": course_key(stage),
            "unitExternalKey": unit_id(unit_number),
            "scormActivityExternalKey": f"{unit_id(unit_number)}-UNITSCORM",
            "sourceRootCode": "s8-disposable",
            "sourceUnitPath": str(source),
            "packagePath": str(zip_path),
            "packageSha256": package_hash,
            "packageContentSha256": digest,
            "mode": "clear_add",
        },
    }


def stage_groups(items: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for item in items:
        key = (str(item["worldCode"]), str(item["deploymentStageCode"]))
        grouped.setdefault(key, []).append(item)
    rows: list[dict[str, object]] = []
    for (world, stage), group_items in sorted(grouped.items()):
        rows.append(
            {
                "worldCode": world,
                "worldTitle": WORLD_TITLE,
                "deploymentStageCode": stage,
                "courseExternalKey": course_key(stage),
                "unitCount": len(group_items),
                "unitIds": [str(item["unitId"]) for item in group_items],
                "sourceRootCodes": ["s8-disposable"],
            }
        )
    return rows


def make_manifest(name: str, items: list[dict[str, object]], import_mode: str = "overwrite") -> Path:
    manifest = {
        "kind": "smartcourses_scorm_batch",
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "manifestSchemaVersion": 2,
        "importMode": import_mode,
        "productionScope": "s8_disposable_fixture_only",
        "s8FixtureRunId": RUN_ID,
        "exportDir": str(BASE_DIR),
        "items": items,
        "successCount": len(items),
        "failureCount": 0,
        "missingCount": 0,
        "s7BatchArchitecture": {
            "stageCourse": "FLW World + Deployment Stage -> Moodle Course",
            "unitSection": "FLW Unit -> Moodle Section",
            "unitScorm": "1 FLW Unit -> 1 current SCORM 1.2 activity/package",
            "groupingKey": "WorldCode + DeploymentStageCode",
            "normalBatchImportModes": ["overwrite", "add_new", "clear_add"],
            "s8SafeRebuildMode": "clear_add",
            "s8VisibleOperationName": "Rebuild Selected FLW Scope",
            "s8ScopeModel": "WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID",
        },
        "stageGroups": stage_groups(items),
        "stageGroupCount": len(stage_groups(items)),
        "catalogValidation": {
            "gate": "S8",
            "productionScope": "disposable_test_fixture",
            "expectedTotal": len(items),
            "availableValidTotal": len(items),
            "selectedTotal": len(items),
            "spanishReadinessStatus": "OUT_OF_SCOPE",
        },
        "preflight": {
            "statusCounts": {"RESOLVED": len(items)},
            "blockingCount": 0,
            "blockingStatuses": [],
            "blockingItems": [],
        },
        "blockedForRealImport": False,
    }
    path = BASE_DIR / name
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    if BASE_DIR.exists():
        shutil.rmtree(BASE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    MAP_DIR.mkdir(parents=True, exist_ok=True)

    v1 = {
        "u001": make_item(1, "A1", "v1"),
        "u002": make_item(2, "A1", "v1"),
        "u003": make_item(3, "A1", "v1"),
        "u004_a1": make_item(4, "A1", "v1"),
        "u005": make_item(5, "A2", "v1"),
    }
    v2 = {
        "u001": make_item(1, "A1", "v2"),
        "u002": make_item(2, "A1", "v2"),
        "u003": make_item(3, "A1", "v2"),
        "u004_a2": make_item(4, "A2", "v2"),
        "u005": make_item(5, "A2", "v2"),
        "u006_invalid": make_item(6, "A1", "v2"),
    }

    invalid_zip = Path(str(v2["u006_invalid"]["export"]["zipPath"]))
    invalid_zip.write_bytes(b"not a scorm zip")
    invalid_hash = hashlib.sha256(invalid_zip.read_bytes()).hexdigest()
    v2["u006_invalid"]["export"]["packageSha256"] = invalid_hash
    v2["u006_invalid"]["packageSha256"] = invalid_hash
    v2["u006_invalid"]["targetMetadata"]["packageSha256"] = invalid_hash
    v2["u006_invalid"]["batchTarget"]["packageSha256"] = invalid_hash

    manifests = {
        "seed_v1": make_manifest("s8_manifest_seed_v1.json", list(v1.values()), "overwrite"),
        "u001_v2": make_manifest("s8_manifest_u001_v2.json", [v2["u001"]], "clear_add"),
        "u002_v2": make_manifest("s8_manifest_u002_v2.json", [v2["u002"]], "clear_add"),
        "u001_u002_v2": make_manifest("s8_manifest_u001_u002_v2.json", [v2["u001"], v2["u002"]], "clear_add"),
        "u003_v2": make_manifest("s8_manifest_u003_v2.json", [v2["u003"]], "clear_add"),
        "u004_wrong_stage_v2": make_manifest("s8_manifest_u004_wrong_stage_v2.json", [v2["u004_a2"]], "clear_add"),
        "u005_v2": make_manifest("s8_manifest_u005_v2.json", [v2["u005"]], "clear_add"),
        "multi_stage_v2": make_manifest("s8_manifest_multi_stage_v2.json", [v2["u002"], v2["u005"]], "clear_add"),
        "u006_invalid_v2": make_manifest("s8_manifest_u006_invalid_v2.json", [v2["u006_invalid"]], "clear_add"),
    }

    summary = {
        "status": "PASS",
        "runId": RUN_ID,
        "baseDir": str(BASE_DIR),
        "mapDir": str(MAP_DIR),
        "moodleCategory": MOODLE_CATEGORY,
        "courseKeys": {"A1": course_key("A1"), "A2": course_key("A2")},
        "courseShortnames": {"A1": course_shortname("A1"), "A2": course_shortname("A2")},
        "units": {
            "historyBearing": {
                "unitId": unit_id(1),
                "stableCmidNumber": stable_cmidnumber(1),
                "manualCmidNumber": f"S8_MANUAL_PAGE_{RUN_ID}_U001",
            },
            "noHistory": {
                "unitId": unit_id(2),
                "stableCmidNumber": stable_cmidnumber(2),
                "manualCmidNumber": f"S8_MANUAL_PAGE_{RUN_ID}_U002",
            },
            "duplicateConflict": {
                "unitId": unit_id(3),
                "stableCmidNumber": stable_cmidnumber(3),
                "duplicatePackage": str(v1["u003"]["export"]["zipPath"]),
            },
            "wrongStage": {
                "unitId": unit_id(4),
                "createdStage": "A1",
                "rebuildTargetStage": "A2",
                "stableCmidNumber": stable_cmidnumber(4),
            },
            "multiStage": {
                "unitId": unit_id(5),
                "stableCmidNumber": stable_cmidnumber(5),
            },
            "invalidFailure": {
                "unitId": unit_id(6),
                "stableCmidNumber": stable_cmidnumber(6),
            },
        },
        "manifests": {key: str(value) for key, value in manifests.items()},
        "mapPaths": {
            "stageCourseMap": str(MAP_DIR / "flw_moodle_stage_course_map.s8.json"),
            "unitSectionMap": str(MAP_DIR / "flw_moodle_unit_section_map.s8.json"),
            "unitScormMap": str(MAP_DIR / "flw_moodle_unit_scorm_map.s8.json"),
        },
    }
    (BASE_DIR / "s8_fixture_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
