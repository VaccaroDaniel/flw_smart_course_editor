from __future__ import annotations

import json
import sys
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from p1_content_deployment_contract import (  # noqa: E402
    P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
    P1ContentDeploymentContract,
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    base = APP_DIR / "verification_exports" / "s8_disposable_rebuild"
    out_dir = APP_DIR / "verification_exports" / "s9_final_qa"
    summary_path = base / "s8_fixture_summary.json"
    if not summary_path.exists():
        raise SystemExit(f"Missing S8 fixture summary: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    map_paths = summary["mapPaths"]
    manifests = summary["manifests"]
    unit_id = summary["units"]["historyBearing"]["unitId"]
    stable_cmidnumber = summary["units"]["historyBearing"]["stableCmidNumber"]
    current_sco = stable_cmidnumber.replace("_UNITSCORM", "_WATCH")
    parent_component = f"{unit_id}-WATCH"
    micro_id = f"{parent_component}-Q001"

    micro_manifest = out_dir / "s9_micro_activity_contract_fixture.json"
    write_json(
        micro_manifest,
        {
            "kind": "smartcourses_scorm_batch",
            "s9ContractFixture": "micro-activity-parent",
            "items": [
                {
                    "unitId": unit_id,
                    "scormActivityExternalKey": f"{unit_id}-UNITSCORM",
                    "componentMappings": [
                        {
                            "componentId": parent_component,
                            "componentKey": "WATCH",
                            "kind": "section",
                            "title": "Watch",
                            "scoIdentifier": current_sco,
                            "launchFile": "scos/watch.html",
                        }
                    ],
                    "microActivityMappings": [
                        {
                            "microActivityId": micro_id,
                            "parentComponentId": parent_component,
                            "trackAsSeparateSco": False,
                        }
                    ],
                }
            ],
        },
    )

    contract = P1ContentDeploymentContract(
        stage_course_map_path=Path(map_paths["stageCourseMap"]),
        unit_section_map_path=Path(map_paths["unitSectionMap"]),
        unit_scorm_map_path=Path(map_paths["unitScormMap"]),
        manifest_paths=[
            Path(manifests["u001_u002_v2"]),
            Path(manifests["multi_stage_v2"]),
            micro_manifest,
        ],
    )

    current = contract.resolve_current_unit_deployment(unit_id)
    if not current:
        raise SystemExit(f"Could not resolve current deployment for {unit_id}")
    historical_cmid = None
    old_sco = ""
    for deployment in contract.unit_scorms.values():
        if deployment.get("UnitID") != unit_id:
            continue
        for row in deployment.get("history", []) or []:
            historical_cmid = int(row["cmid"])
            old_sco = (row.get("tracking", {}).get("trackedScoIdentifiers") or [""])[0]
            break
    if historical_cmid is None:
        raise SystemExit(f"Could not resolve historical deployment fixture for {unit_id}")

    loop_count = 500
    start = time.perf_counter()
    for _ in range(loop_count):
        contract.resolve_current_unit_deployment(unit_id)
        contract.resolve_unit_from_cmid(int(current["cmid"]))
        contract.resolve_activity_from_cmid_and_sco(int(current["cmid"]), current_sco)
        contract.resolve_historical_unit_deployment(unit_id, historical_cmid)
    elapsed = time.perf_counter() - start

    history_handoff = {
        "source": {
            "cmid": historical_cmid,
            "scoIdentifier": old_sco,
            "eventType": "Moodle SCORM tracking row",
        },
        "component": contract.resolve_activity_from_cmid_and_sco(historical_cmid, old_sco),
        "deployment": contract.resolve_historical_unit_deployment(unit_id, historical_cmid),
    }
    current_component = contract.resolve_activity_from_cmid_and_sco(int(current["cmid"]), current_sco)
    cupkp_handoff = {
        "microActivity": micro_id,
        "parent": contract.resolve_micro_activity_parent(micro_id),
        "parentComponent": current_component,
        "currentDeployment": current,
        "historicalDeployment": contract.resolve_historical_unit_deployment(unit_id, historical_cmid),
    }
    report = {
        "status": "PASS",
        "contractVersion": P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
        "fixtureRunId": summary["runId"],
        "invariants": contract.validate_invariants(),
        "worldStage": contract.resolve_world_stage_from_course(int(current["moodleCourseId"])),
        "unitSection": contract.resolve_unit_from_section(int(current["moodleCourseId"]), int(current["moodleSectionId"])),
        "currentDeployment": current,
        "historicalDeployment": contract.resolve_historical_unit_deployment(unit_id, historical_cmid),
        "componentCurrent": current_component,
        "historyHandoff": history_handoff,
        "cupkpHandoff": cupkp_handoff,
        "freshnessCurrent": contract.resolve_deployment_freshness(unit_id),
        "freshnessOutdatedExample": contract.resolve_deployment_freshness(unit_id, "different-content-hash"),
        "lookupPerformance": {
            "loopCount": loop_count,
            "totalSeconds": round(elapsed, 6),
            "averageSecondsPerFourLookups": round(elapsed / loop_count, 8),
            "storage": "local JSON indexes loaded once; no Moodle scan per lookup",
        },
        "outputs": {
            "microFixtureManifest": str(micro_manifest),
        },
    }
    required = [
        report["worldStage"],
        report["unitSection"],
        report["currentDeployment"],
        report["historicalDeployment"],
        report["componentCurrent"],
        report["historyHandoff"]["component"],
        report["historyHandoff"]["deployment"],
        report["cupkpHandoff"]["parent"],
        report["freshnessCurrent"],
        report["freshnessOutdatedExample"],
    ]
    if any(not item for item in required) or report["invariants"]["status"] != "PASS":
        report["status"] = "FAIL"

    report_path = out_dir / "s9_contract_check_report.json"
    write_json(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path), "summary": report["lookupPerformance"]}, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
