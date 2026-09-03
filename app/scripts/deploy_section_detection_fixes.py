from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


DEFAULT_AUDIT = Path(
    r"D:\WinPro.Delta\Projects\SmartCourses\scorm_exports\section_detection_audit_20260827\section_detection_audit.json"
)
DEFAULT_MOODLE_URL = "https://192.168.129.79"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_extract_archive(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            server.validate_zip_member_name(info.filename)
        package.extractall(destination)
    root = server.extracted_unit_root(destination)
    if not root:
        raise RuntimeError(f"No index.html found after extracting {archive}")
    return root


def expected_identifiers(row: dict) -> list[str]:
    return [str(value) for value in row.get("predictedScoIdentifiers") or []]


def build(audit_path: Path, output_dir: Path) -> Path:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    candidates = list(audit.get("deploymentCandidates") or [])
    if not candidates:
        raise RuntimeError("The audit has no deployment candidates.")
    packages_dir = output_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "build_state.json"
    items: list[dict] = []
    completed: list[dict] = []
    failures: list[dict] = []
    for position, row in enumerate(candidates, start=1):
        unit_id = str(row.get("unitId") or "")
        archive = Path(str(row.get("archive") or ""))
        source_root = archive.parent
        print(f"BUILD {position}/{len(candidates)} {unit_id} from {archive.name}", flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix=f"flw_{unit_id.lower()}_") as temporary:
                unit_path = safe_extract_archive(archive, Path(temporary))
                language = server.detect_flw_language(source_root, unit_path)
                metadata = server.index_meta(unit_path)
                report = server.export_scorm(
                    unit_path,
                    {
                        "title": metadata.get("title") or unit_path.name,
                        "root": str(source_root),
                        "exportDir": str(packages_dir),
                        "launchFile": "index.html",
                        "includeSourceData": False,
                        "includeTools": False,
                        "includeUnitSco": False,
                        "keepTopNavBar": False,
                        "autocomplete": True,
                    },
                )
                actual = [
                    str(mapping.get("scoIdentifier") or "")
                    for mapping in report.get("componentMappings") or []
                ]
                expected = expected_identifiers(row)
                if actual != expected:
                    raise RuntimeError(
                        f"Export identity mismatch for {unit_id}: expected {expected}, got {actual}"
                    )
                item = server.batch_manifest_item(language, source_root, unit_path, report)
                items.append(item)
                completed.append(
                    {
                        "unitId": unit_id,
                        "archive": str(archive),
                        "zipPath": report.get("zipPath"),
                        "scoCount": report.get("scoCount"),
                        "currentCmid": row.get("currentCmid"),
                        "currentScormId": row.get("currentScormId"),
                        "currentRevision": row.get("currentRevision"),
                        "componentScoIdentifiers": actual,
                    }
                )
        except Exception as exc:
            failures.append({"unitId": unit_id, "archive": str(archive), "error": str(exc)})
            print(f"FAILED {unit_id}: {exc}", flush=True)
        write_json(
            state_path,
            {
                "auditPath": str(audit_path),
                "planned": len(candidates),
                "completed": completed,
                "failures": failures,
            },
        )
    if failures:
        raise RuntimeError(f"Build failed for {len(failures)} Unit(s). See {state_path}")
    stamp = server.flw_import_stamp()
    manifest = server.enrich_manifest_preflight(
        {
            "kind": "smartcourses_scorm_batch",
            "timestamp": stamp,
            "manifestSchemaVersion": 2,
            "importMode": "overwrite",
            "allAvailableUnits": False,
            "batchWorldScope": "audit_selection",
            "productionScope": "seven_world_production",
            "units": [row.get("unit") for row in candidates],
            "exportDir": str(packages_dir),
            "items": items,
            "successCount": len(items),
            "failureCount": 0,
            "auditPath": str(audit_path),
        }
    )
    if manifest.get("blockedForRealImport"):
        raise RuntimeError(f"Manifest preflight is blocked: {manifest.get('preflight')}")
    manifest_path = output_dir / "batch_manifest.json"
    write_json(manifest_path, manifest)
    print(f"BUILD COMPLETE {len(items)}/{len(candidates)} packages; manifest={manifest_path}", flush=True)
    return manifest_path


def report_failures(report: dict, expected_actions: set[str], expected_count: int) -> list[str]:
    errors: list[str] = []
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for key in ("unitsBlocked", "unitsConflict", "unitsFailed", "scormFailures", "scormSuperseded"):
        if int(summary.get(key) or 0):
            errors.append(f"{key}={summary.get(key)}")
    rows = report.get("unitResults") if isinstance(report.get("unitResults"), list) else []
    if len(rows) != expected_count:
        errors.append(f"unitResults={len(rows)} expected={expected_count}")
    for row in rows:
        unit_id = row.get("unitId") or f"U{row.get('unit')}"
        action = str(row.get("scormAction") or "")
        if action not in expected_actions:
            errors.append(
                f"{unit_id}: scormAction={action}, expected one of={sorted(expected_actions)}"
            )
        safety = row.get("safety") if isinstance(row.get("safety"), dict) else {}
        if action == "UPDATE_SCORM" and not bool(safety.get("safe")):
            errors.append(f"{unit_id}: safety.safe is not true")
        missing = safety.get("missingTrackedScoIdentifiers") or []
        if missing:
            errors.append(f"{unit_id}: missing tracked identifiers={missing}")
    return errors


def run_import(
    manifest_path: Path,
    report_path: Path,
    *,
    moodle_url: str,
    dry_run: bool,
    expected_actions: set[str],
    expected_preview_state: str = "",
) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_count = len(manifest.get("items") or [])
    result = server.run_flw_import(
        manifest_path=manifest_path,
        report_path=report_path,
        stamp=server.flw_import_stamp(),
        moodle_url=moodle_url,
        dry_run=dry_run,
        section_prefix="Section detection correction",
        name_prefix="Section detection correction",
        import_mode="overwrite",
        timeout_seconds=7200,
        allow_nonzero_with_report=True,
        expected_preview_state=expected_preview_state,
    )
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    failures = report_failures(report, expected_actions, expected_count)
    result["verification"] = {
        "expectedActions": sorted(expected_actions),
        "expectedCount": expected_count,
        "failures": failures,
        "passed": not failures,
    }
    result_path = report_path.with_name(report_path.stem + ".runner_result.json")
    write_json(result_path, result)
    if failures:
        raise RuntimeError("Import verification failed: " + " | ".join(failures[:20]))
    print(
        f"{'PREVIEW' if dry_run else 'DEPLOY'} PASS {expected_count} Units; "
        f"actions={','.join(sorted(expected_actions))}; previewStateHash={report.get('previewStateHash') or ''}",
        flush=True,
    )
    return result


def make_resume_chunks(manifest_path: Path, output_dir: Path, chunk_size: int) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    map_data = json.loads((APP_DIR / "flw_moodle_unit_scorm_map.json").read_text(encoding="utf-8"))
    mapped = map_data.get("unitScormActivities") if isinstance(map_data, dict) else {}
    remaining: list[dict] = []
    already_current: list[str] = []
    for item in manifest.get("items") or []:
        unit_id = str(item.get("unitId") or (item.get("targetMetadata") or {}).get("unitId") or "")
        activity_id = str(
            item.get("scormActivityExternalKey")
            or (item.get("targetMetadata") or {}).get("scormActivityExternalKey")
            or (f"{unit_id}-UNITSCORM" if unit_id else "")
        )
        current = mapped.get(activity_id) if isinstance(mapped, dict) else {}
        package_sha = str((item.get("export") or {}).get("packageSha256") or "")
        if package_sha and str((current or {}).get("packageSha256") or "") == package_sha:
            already_current.append(unit_id)
        else:
            remaining.append(item)
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    for offset in range(0, len(remaining), chunk_size):
        items = remaining[offset : offset + chunk_size]
        chunk_number = len(chunk_paths) + 1
        chunk = dict(manifest)
        chunk.update(
            {
                "timestamp": server.flw_import_stamp(),
                "items": items,
                "units": [item.get("unit") for item in items],
                "successCount": len(items),
                "failureCount": 0,
                "resumeChunk": chunk_number,
                "resumeSourceManifest": str(manifest_path),
            }
        )
        chunk = server.enrich_manifest_preflight(chunk)
        path = output_dir / f"resume_chunk_{chunk_number:02d}.manifest.json"
        write_json(path, chunk)
        chunk_paths.append(path)
    write_json(
        output_dir / "resume_plan.json",
        {
            "sourceManifest": str(manifest_path),
            "alreadyCurrentCount": len(already_current),
            "alreadyCurrent": already_current,
            "remainingCount": len(remaining),
            "chunkSize": chunk_size,
            "chunks": [str(path) for path in chunk_paths],
        },
    )
    print(
        f"RESUME PLAN already-current={len(already_current)} remaining={len(remaining)} chunks={len(chunk_paths)}",
        flush=True,
    )
    for path in chunk_paths:
        print(path, flush=True)
    return chunk_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, preview, deploy, and verify audited section-detection fixes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    chunk_parser = subparsers.add_parser("make-resume-chunks")
    chunk_parser.add_argument("--manifest", type=Path, required=True)
    chunk_parser.add_argument("--output-dir", type=Path, required=True)
    chunk_parser.add_argument("--chunk-size", type=int, default=10)
    for command in ("preview", "deploy", "verify"):
        action = subparsers.add_parser(command)
        action.add_argument("--manifest", type=Path, required=True)
        action.add_argument("--report", type=Path, required=True)
        action.add_argument("--moodle-url", default=DEFAULT_MOODLE_URL)
        action.add_argument("--expected-actions", default="")
        if command == "deploy":
            action.add_argument("--expected-preview-state", required=True)
    args = parser.parse_args()
    if args.command == "build":
        build(args.audit.resolve(), args.output_dir.resolve())
        return 0
    if args.command == "make-resume-chunks":
        if args.chunk_size < 1 or args.chunk_size > 25:
            raise RuntimeError("chunk-size must be between 1 and 25")
        make_resume_chunks(args.manifest.resolve(), args.output_dir.resolve(), args.chunk_size)
        return 0
    default_actions = "UNCHANGED" if args.command == "verify" else "UPDATE_SCORM"
    expected_actions = {
        value.strip().upper()
        for value in (args.expected_actions or default_actions).split(",")
        if value.strip()
    }
    result = run_import(
        args.manifest.resolve(),
        args.report.resolve(),
        moodle_url=args.moodle_url,
        dry_run=args.command != "deploy",
        expected_actions=expected_actions,
        expected_preview_state=getattr(args, "expected_preview_state", ""),
    )
    if args.command == "preview":
        preview_hash = ((result.get("report") or {}).get("previewStateHash") or "").strip()
        if not preview_hash:
            raise RuntimeError("Preview completed without previewStateHash.")
        (args.report.parent / "preview_state_hash.txt").write_text(preview_hash + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
