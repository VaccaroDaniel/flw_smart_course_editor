from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION = "1.0"

DEPLOYMENT_STATES = {
    "CURRENT",
    "OUTDATED",
    "DRIFTED",
    "CONFLICT",
    "FAILED",
    "SUPERSEDED",
    "UNKNOWN",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
    return data if isinstance(data, dict) else {}


def _as_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _first_mapping_list(*sources: dict[str, Any], key: str) -> list[dict[str, Any]]:
    for source in sources:
        value = source.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


@dataclass
class P1ContentDeploymentContract:
    """Read-only Program-1 deployment lookup contract.

    The contract intentionally consumes existing S3-S8 artifacts:
    stage-course map, unit-section map, unit-SCORM map, and exported
    Smart Course Editor manifests/reports. It does not query or mutate Moodle.
    """

    stage_course_map_path: Path
    unit_section_map_path: Path
    unit_scorm_map_path: Path
    manifest_paths: list[Path] = field(default_factory=list)

    stage_courses: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    unit_sections: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    unit_scorms: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    components_by_sco: dict[tuple[int, str], dict[str, Any]] = field(init=False, default_factory=dict)
    components_by_activity: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    micro_parent: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    manifests_indexed: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.stage_courses = _load_json(self.stage_course_map_path).get("stageCourses", {}) or {}
        self.unit_sections = _load_json(self.unit_section_map_path).get("unitSections", {}) or {}
        self.unit_scorms = _load_json(self.unit_scorm_map_path).get("unitScormActivities", {}) or {}
        self._index_manifests()

    @classmethod
    def default(cls, root: Path | str = ".") -> "P1ContentDeploymentContract":
        base = Path(root)
        return cls(
            stage_course_map_path=base / "flw_moodle_stage_course_map.json",
            unit_section_map_path=base / "flw_moodle_unit_section_map.json",
            unit_scorm_map_path=base / "flw_moodle_unit_scorm_map.json",
            manifest_paths=[],
        )

    def _iter_manifest_items(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        items = manifest.get("items")
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _index_manifests(self) -> None:
        for path in self.manifest_paths:
            manifest = _load_json(path)
            items = self._iter_manifest_items(manifest)
            if not items:
                continue
            self.manifests_indexed += 1
            for item in items:
                export = item.get("export") if isinstance(item.get("export"), dict) else {}
                target = item.get("targetMetadata") if isinstance(item.get("targetMetadata"), dict) else {}
                unit_id = str(target.get("unitId") or item.get("unitId") or export.get("unitId") or "")
                activity_id = str(
                    target.get("scormActivityExternalKey")
                    or item.get("scormActivityExternalKey")
                    or export.get("scormActivityExternalKey")
                    or (unit_id + "-UNITSCORM" if unit_id else "")
                )
                deployment = self.resolve_current_unit_deployment(unit_id) if unit_id else None
                cmid = _as_int((deployment or {}).get("cmid"))
                component_mappings = _first_mapping_list(item, export, target, key="componentMappings")
                for component in component_mappings:
                    sco = str(component.get("scoIdentifier") or component.get("itemIdentifier") or "")
                    component_id = str(component.get("componentId") or "")
                    if not sco or not component_id:
                        continue
                    row = {
                        "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
                        "ComponentActivityID": component_id,
                        "UnitID": unit_id,
                        "UnitSCORMActivityID": activity_id,
                        "cmid": cmid,
                        "scoIdentifier": sco,
                        "componentKey": component.get("componentKey", ""),
                        "kind": component.get("kind", ""),
                        "title": component.get("title", ""),
                        "launchFile": component.get("launchFile", ""),
                        "status": "CURRENT" if cmid else "UNDEPLOYED",
                    }
                    self.components_by_activity[component_id] = row
                    if cmid:
                        self.components_by_sco[(cmid, sco)] = row

                for micro in _first_mapping_list(item, export, target, key="microActivityMappings"):
                    micro_id = str(micro.get("microActivityId") or micro.get("MicroActivityID") or micro.get("activityId") or "")
                    parent_id = str(
                        micro.get("parentComponentId")
                        or micro.get("parentComponentActivityID")
                        or micro.get("ComponentActivityID")
                        or ""
                    )
                    if micro_id and parent_id:
                        self.micro_parent[micro_id] = {
                            "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
                            "MicroActivityID": micro_id,
                            "parentComponentActivityID": parent_id,
                            "UnitID": unit_id,
                            "UnitSCORMActivityID": activity_id,
                            "trackAsSeparateSco": bool(micro.get("trackAsSeparateSco", False)),
                            "status": "PARENT_COMPONENT",
                        }

    def resolve_world_stage_from_course(self, courseid: int) -> dict[str, Any] | None:
        for entry in self.stage_courses.values():
            if _as_int(entry.get("moodleCourseId")) == courseid:
                return {
                    "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
                    "WorldCode": entry.get("WorldCode", ""),
                    "DeploymentStageCode": entry.get("DeploymentStageCode", ""),
                    "courseExternalKey": entry.get("courseExternalKey", ""),
                    "moodleCourseId": courseid,
                    "moodleCourseIdnumber": entry.get("moodleCourseIdnumber", ""),
                    "status": entry.get("status", "CURRENT"),
                }
        return None

    def resolve_unit_from_section(self, courseid: int, sectionid: int) -> dict[str, Any] | None:
        for entry in self.unit_sections.values():
            if _as_int(entry.get("moodleCourseId")) == courseid and _as_int(entry.get("moodleSectionId")) == sectionid:
                return {
                    "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
                    "UnitID": entry.get("UnitID", ""),
                    "WorldCode": entry.get("WorldCode", ""),
                    "DeploymentStageCode": entry.get("DeploymentStageCode", ""),
                    "moodleCourseId": courseid,
                    "moodleSectionId": sectionid,
                    "moodleSectionNumber": entry.get("moodleSectionNumber"),
                    "sectionName": entry.get("sectionName", ""),
                    "status": entry.get("status", "CURRENT"),
                }
        return None

    def resolve_current_unit_deployment(self, unit_id: str) -> dict[str, Any] | None:
        for entry in self.unit_scorms.values():
            if str(entry.get("UnitID", "")) == unit_id and str(entry.get("status", "CURRENT")) == "CURRENT":
                return self._deployment_row(entry, historical=None)
        return None

    def resolve_unit_from_cmid(self, cmid: int) -> dict[str, Any] | None:
        for entry in self.unit_scorms.values():
            if _as_int(entry.get("currentCmid")) == cmid:
                return self._deployment_row(entry, historical=None)
            for historical in entry.get("history", []) or []:
                if isinstance(historical, dict) and _as_int(historical.get("cmid")) == cmid:
                    return self._deployment_row(entry, historical=historical)
        return None

    def resolve_activity_from_cmid_and_sco(self, cmid: int, sco_identifier: str) -> dict[str, Any] | None:
        row = self.components_by_sco.get((cmid, sco_identifier))
        if row:
            return dict(row)
        deployment = self.resolve_unit_from_cmid(cmid)
        if not deployment:
            return None
        unit_id = str(deployment.get("UnitID", ""))
        for activity in self.components_by_activity.values():
            if activity.get("UnitID") == unit_id and activity.get("scoIdentifier") == sco_identifier:
                resolved = dict(activity)
                resolved["cmid"] = cmid
                resolved["status"] = deployment.get("status", "UNKNOWN")
                return resolved
        return None

    def resolve_micro_activity_parent(self, activity_id: str) -> dict[str, Any] | None:
        return dict(self.micro_parent[activity_id]) if activity_id in self.micro_parent else None

    def resolve_historical_unit_deployment(self, unit_id: str, cmid: int) -> dict[str, Any] | None:
        deployment = self.resolve_unit_from_cmid(cmid)
        if deployment and deployment.get("UnitID") == unit_id and deployment.get("status") == "SUPERSEDED":
            return deployment
        return None

    def resolve_content_revision_for_deployment(self, *, unit_id: str | None = None, cmid: int | None = None) -> dict[str, Any] | None:
        deployment = self.resolve_unit_from_cmid(cmid) if cmid else self.resolve_current_unit_deployment(unit_id or "")
        if not deployment:
            return None
        return {
            "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
            "UnitID": deployment.get("UnitID", ""),
            "UnitSCORMActivityID": deployment.get("UnitSCORMActivityID", ""),
            "cmid": deployment.get("cmid"),
            "scormInstanceId": deployment.get("scormInstanceId"),
            "deploymentRevision": deployment.get("deploymentRevision"),
            "status": deployment.get("status"),
            "packageSha256": deployment.get("packageSha256", ""),
            "packageContentSha256": deployment.get("packageContentSha256", ""),
            "freshness": deployment.get("freshness", "UNKNOWN"),
        }

    def resolve_deployment_freshness(self, unit_id: str, expected_package_content_sha256: str | None = None) -> dict[str, Any] | None:
        deployment = self.resolve_current_unit_deployment(unit_id)
        if not deployment:
            return None
        current_hash = str(deployment.get("packageContentSha256") or "")
        if not expected_package_content_sha256:
            state = "CURRENT" if current_hash else "UNKNOWN"
        elif current_hash == expected_package_content_sha256:
            state = "CURRENT"
        else:
            state = "OUTDATED"
        return {
            "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
            "UnitID": unit_id,
            "cmid": deployment.get("cmid"),
            "packageContentSha256": current_hash,
            "expectedPackageContentSha256": expected_package_content_sha256 or "",
            "deploymentState": state,
        }

    def validate_invariants(self) -> dict[str, Any]:
        current_by_activity: dict[str, list[int]] = {}
        for activity_id, entry in self.unit_scorms.items():
            if str(entry.get("status", "CURRENT")) == "CURRENT":
                cmid = _as_int(entry.get("currentCmid"))
                if cmid:
                    current_by_activity.setdefault(activity_id, []).append(cmid)
        duplicate_current = {
            key: cmids for key, cmids in current_by_activity.items() if len(set(cmids)) > 1
        }
        return {
            "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
            "status": "PASS" if not duplicate_current else "FAIL",
            "currentDeploymentCount": sum(len(cmids) for cmids in current_by_activity.values()),
            "duplicateCurrentDeployments": duplicate_current,
            "stageCourseCount": len(self.stage_courses),
            "unitSectionCount": len(self.unit_sections),
            "unitScormCount": len(self.unit_scorms),
            "componentActivityCount": len(self.components_by_activity),
            "microActivityCount": len(self.micro_parent),
            "manifestFilesIndexed": self.manifests_indexed,
        }

    def _deployment_row(self, entry: dict[str, Any], historical: dict[str, Any] | None) -> dict[str, Any]:
        is_history = historical is not None
        cmid = _as_int((historical or {}).get("cmid")) if is_history else _as_int(entry.get("currentCmid"))
        scorm_id = _as_int((historical or {}).get("scormId")) if is_history else _as_int(entry.get("currentScormId"))
        component_ids = entry.get("componentScoIdentifiers", [])
        if is_history:
            component_ids = (historical or {}).get("componentScoIdentifiers") or (historical or {}).get("tracking", {}).get("trackedScoIdentifiers", [])
        return {
            "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
            "UnitID": entry.get("UnitID", ""),
            "UnitSCORMActivityID": entry.get("UnitSCORMActivityID", ""),
            "WorldCode": entry.get("WorldCode", ""),
            "DeploymentStageCode": entry.get("DeploymentStageCode", ""),
            "courseExternalKey": entry.get("courseExternalKey", ""),
            "moodleCourseId": entry.get("moodleCourseId"),
            "moodleSectionId": entry.get("moodleSectionId"),
            "cmid": cmid,
            "scormInstanceId": scorm_id,
            "cmidnumber": (historical or {}).get("retiredCmidNumber") if is_history else entry.get("stableCmidNumber", ""),
            "deploymentRevision": (historical or {}).get("deploymentRevision", "historical") if is_history else entry.get("currentRevision"),
            "status": "SUPERSEDED" if is_history else entry.get("status", "CURRENT"),
            "freshness": "SUPERSEDED" if is_history else ("CURRENT" if entry.get("packageContentSha256") else "UNKNOWN"),
            "packageSha1": (historical or {}).get("packageSha1", "") if is_history else entry.get("packageSha1", ""),
            "packageSha256": (historical or {}).get("packageSha256", "") if is_history else entry.get("packageSha256", ""),
            "packageContentSha256": (historical or {}).get("packageContentSha256", "") if is_history else entry.get("packageContentSha256", ""),
            "componentScoIdentifiers": component_ids if isinstance(component_ids, list) else [],
        }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Program-1 content deployment contract lookup service")
    parser.add_argument("--stage-map", required=True)
    parser.add_argument("--section-map", required=True)
    parser.add_argument("--scorm-map", required=True)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    contract = P1ContentDeploymentContract(
        stage_course_map_path=Path(args.stage_map),
        unit_section_map_path=Path(args.section_map),
        unit_scorm_map_path=Path(args.scorm_map),
        manifest_paths=[Path(path) for path in args.manifest],
    )
    report: dict[str, Any] = {
        "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
        "invariants": contract.validate_invariants(),
    }
    if args.self_test:
        current = next((contract.resolve_current_unit_deployment(entry.get("UnitID", "")) for entry in contract.unit_scorms.values()), None)
        current = current or {}
        unit_id = str(current.get("UnitID", ""))
        cmid = _as_int(current.get("cmid"))
        first_sco = (current.get("componentScoIdentifiers") or [""])[0]
        report["selfTest"] = {
            "currentDeployment": current,
            "worldStage": contract.resolve_world_stage_from_course(_as_int(current.get("moodleCourseId")) or 0),
            "unitSection": contract.resolve_unit_from_section(_as_int(current.get("moodleCourseId")) or 0, _as_int(current.get("moodleSectionId")) or 0),
            "unitFromCmid": contract.resolve_unit_from_cmid(cmid or 0),
            "componentFromCmidAndSco": contract.resolve_activity_from_cmid_and_sco(cmid or 0, str(first_sco)) if first_sco else None,
            "contentRevision": contract.resolve_content_revision_for_deployment(unit_id=unit_id),
            "freshness": contract.resolve_deployment_freshness(unit_id),
        }
        historical = None
        for entry in contract.unit_scorms.values():
            for row in entry.get("history", []) or []:
                if isinstance(row, dict):
                    historical = contract.resolve_historical_unit_deployment(str(entry.get("UnitID", "")), _as_int(row.get("cmid")) or 0)
                    break
            if historical:
                break
        report["selfTest"]["historicalDeployment"] = historical
        required = [
            report["selfTest"]["currentDeployment"],
            report["selfTest"]["worldStage"],
            report["selfTest"]["unitSection"],
            report["selfTest"]["unitFromCmid"],
            report["selfTest"]["contentRevision"],
            report["selfTest"]["freshness"],
        ]
        if any(not item for item in required) or report["invariants"]["status"] != "PASS":
            report["status"] = "FAIL"
        else:
            report["status"] = "PASS"
    else:
        report["status"] = report["invariants"]["status"]

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(_main())
