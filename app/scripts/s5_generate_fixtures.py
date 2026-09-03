from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402


OUT_DIR = APP_DIR / "verification_exports" / "s5_unit_scorm_tests"
SOURCE_ROOT = APP_DIR.parent / "S5SmartCourses" / "02-Real"
UNIT_DIR = SOURCE_ROOT / "Real_world_unit_023"
EXPORT_ROOT = OUT_DIR / "packages"


def write_unit_index(
    unit: Path,
    *,
    lessons: list[dict],
    title: str = "Real Unit 23",
    extra_text: str = "",
    include_watch: bool = True,
    include_progress: bool = True,
) -> None:
    unit.mkdir(parents=True, exist_ok=True)
    (unit / "assets" / "images").mkdir(parents=True, exist_ok=True)
    unit_data = {
        "unit": 23,
        "title": title,
        "stage": "A2.2",
        "course": "Real English World",
        "vocab": [{"id": "v001", "word": "hello"}, {"id": "v002", "word": "weather"}],
        "lessons": lessons,
        "practice": {
            lesson["id"]: [{"id": f"q{lesson['id'][1:]:0>2}{i:02d}", "type": "practice"} for i in range(1, 4)]
            for lesson in lessons
            if lesson.get("id")
        },
    }
    if include_watch:
        unit_data["watch"] = [{"id": "w001", "text": "watch"}]
        unit_data["watchPractice"] = [{"id": "wq001", "type": "watch-check"}]
    if include_progress:
        unit_data["progress"] = [{"id": "r001", "text": "result"}]

    lesson_html = "".join(
        f'<details class="lesson" id="{lesson["id"]}"><summary>{lesson["title"]}</summary>'
        + "".join(
            f'<button data-activity-id="{item["id"]}">{item["id"]}</button>'
            for item in unit_data["practice"].get(lesson["id"], [])
        )
        + "</details>"
        for lesson in lessons
    )
    nav_links = [
        '<a href="#words">Words</a>',
        '<a href="#lessons">Lessons</a>',
    ]
    if include_watch:
        nav_links.append('<a href="#watch">Watch</a>')
    if include_progress:
        nav_links.append('<a href="#progress">Progress</a>')
    sections = [
        '<section id="words"><h2>Vocabulary Builder</h2><p>Build useful words.</p></section>',
        f'<section id="lessons">{lesson_html}</section>',
    ]
    if include_watch:
        sections.append('<section id="watch"><h2>Watch</h2><p>Watch the model conversation.</p></section>')
    if include_progress:
        sections.append('<section id="progress"><h2>Progress Result</h2><p>Check your result.</p></section>')

    (unit / "index.html").write_text(
        (
            "<!doctype html><html><head>"
            f"<title>{title}</title>"
            "</head><body>"
            f'<header class="top"><nav>{"".join(nav_links)}</nav></header>'
            f"<h1>{title}</h1>"
            + "".join(sections)
            + f"<p>{extra_text}</p>"
            + "<script>function applyUnitChrome(){} function renderVocab(){} function renderLessons(){} "
            + "function renderWatch(){} function renderProgress(){} function bindAudio(){} function bindZoom(){}</script>"
            + f"<script>window.UNIT_DATA={json.dumps(unit_data, ensure_ascii=False)};</script>"
            + "</body></html>"
        ),
        encoding="utf-8",
    )


def export_variant(name: str, *, lessons: list[dict], title: str = "Real Unit 23", extra_text: str = "", include_watch: bool = True) -> dict:
    write_unit_index(UNIT_DIR, lessons=lessons, title=title, extra_text=extra_text, include_watch=include_watch)
    export_dir = EXPORT_ROOT / name
    if export_dir.exists():
        shutil.rmtree(export_dir)
    report = server.export_scorm(
        UNIT_DIR,
        {
            "root": str(SOURCE_ROOT),
            "launchFile": "index.html",
            "exportDir": str(export_dir),
            "title": title,
            "flwNavigator": True,
            "keepTopNavBar": False,
        },
    )
    report["variant"] = name
    return report


def manifest_for(report: dict, name: str) -> dict:
    target = {
        "sourceRootCode": "02-real",
        "worldCode": report["worldCode"],
        "worldTitle": "Real English World",
        "languageCode": "en",
        "sourceStage": "A2.2",
        "deploymentStageCode": report["deploymentStageCode"],
        "unitId": report["unitId"],
        "unitNumber": "023",
        "unitSequence": 23,
        "unitTitle": report["title"],
        "courseExternalKey": report["courseExternalKey"],
        "courseShortname": "FLW-REW-A2",
        "courseIdnumber": report["courseExternalKey"],
        "unitExternalKey": report["unitExternalKey"],
        "scormActivityExternalKey": report["scormActivityExternalKey"],
        "futureCmidNumber": report["futureCmidNumber"],
        "scormManifestIdentifier": report["scormManifestIdentifier"],
        "packageSha256": report["packageSha256"],
        "packageContentSha256": report["packageContentSha256"],
        "componentMappings": report["componentMappings"],
        "microActivityMappings": report["microActivityMappings"],
        "scoIdentifierRule": report["scoIdentifierRule"],
        "preflightStatus": "RESOLVED",
        "stageResolutionStatus": "RESOLVED",
        "moodleCategory": 93,
    }
    item = {
        "code": "02-real",
        "label": "Real",
        "status": "exported",
        "unit": "023",
        "title": report["title"],
        "targetMetadata": target,
        "export": {
            "zipPath": report["zipPath"],
            "futureCmidNumber": report["futureCmidNumber"],
            "scormManifestIdentifier": report["scormManifestIdentifier"],
            "packageSha256": report["packageSha256"],
            "packageContentSha256": report["packageContentSha256"],
            "componentMappings": report["componentMappings"],
            "microActivityMappings": report["microActivityMappings"],
            "scoCount": report["scoCount"],
            "lessonScoCount": report["lessonScoCount"],
            "sectionScoCount": report["sectionScoCount"],
            "flwNavigatorPrimary": report["flwNavigatorPrimary"],
            "moodleScoLaunchMechanism": report["moodleScoLaunchMechanism"],
        },
    }
    return {
        "kind": "s5_unit_scorm_test_manifest",
        "timestamp": "20260824_050000_" + name,
        "manifestSchemaVersion": 2,
        "variant": name,
        "items": [item],
    }


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if SOURCE_ROOT.parent.exists():
        shutil.rmtree(SOURCE_ROOT.parent)

    lessons_base = [
        {"id": "l1", "title": "Lesson 1"},
        {"id": "l2", "title": "Lesson 2"},
        {"id": "l3", "title": "Lesson 3"},
    ]
    variants = {
        "v1": export_variant("v1", lessons=lessons_base, extra_text="initial package"),
        "content_update": export_variant("content_update", lessons=lessons_base, extra_text="content-only package revision"),
        "title_change": export_variant(
            "title_change",
            lessons=[lessons_base[0], {**lessons_base[1], "title": "Discussing the weather"}, lessons_base[2]],
            extra_text="title-change package revision",
        ),
        "reorder": export_variant(
            "reorder",
            lessons=[lessons_base[0], lessons_base[2], lessons_base[1]],
            extra_text="reordered package revision",
        ),
        "add_sco": export_variant(
            "add_sco",
            lessons=lessons_base + [{"id": "l4", "title": "Lesson 4"}],
            extra_text="added substantial component",
        ),
        "remove_tracked": export_variant(
            "remove_tracked",
            lessons=[lessons_base[0], lessons_base[2]],
            extra_text="removed tracked Lesson 2",
        ),
    }

    manifest_paths = {}
    for name, report in variants.items():
        manifest = manifest_for(report, name)
        path = OUT_DIR / f"s5_rew_u023_{name}_manifest.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest_paths[name] = str(path)

    summary = {
        "status": "PASS",
        "unitId": "REW-U023",
        "unitScormActivityId": variants["v1"]["scormActivityExternalKey"],
        "stableCmidNumber": variants["v1"]["futureCmidNumber"],
        "scormManifestIdentifier": variants["v1"]["scormManifestIdentifier"],
        "variants": {
            name: {
                "zipPath": report["zipPath"],
                "manifestPath": manifest_paths[name],
                "packageSha256": report["packageSha256"],
                "packageContentSha256": report["packageContentSha256"],
                "componentScoIdentifiers": [item["scoIdentifier"] for item in report["componentMappings"]],
                "flwNavigatorPrimary": report["flwNavigatorPrimary"],
            }
            for name, report in variants.items()
        },
    }
    (OUT_DIR / "s5_fixture_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
