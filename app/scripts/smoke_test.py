"""Repeatable smoke checks for the local SCORM editor.

This script intentionally uses temporary unit packages only. It does not edit
real SmartCourses folders and it does not build the offline installer.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import server  # noqa: E402
from p1_content_deployment_contract import (  # noqa: E402
    P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION,
    P1ContentDeploymentContract,
)


def write_unit_index(
    unit: Path,
    title: str = "Unit 1 Old",
    *,
    unit_number: int = 1,
    stage: str = "",
    deployment_stage: str = "",
) -> None:
    (unit / "assets" / "images").mkdir(parents=True, exist_ok=True)
    unit_data = {
        "unit": unit_number,
        "title": title,
        "vocab": [{"word": "hello"}],
        "lessons": [{"id": "l1", "title": "Say hello"}],
        "watch": [{"text": "hi"}],
    }
    if stage:
        unit_data["stage"] = stage
    if deployment_stage:
        unit_data["deploymentStage"] = deployment_stage
    (unit / "index.html").write_text(
        (
            "<!doctype html><html><head>"
            f"<title>{title}</title>"
            "</head><body>"
            '<header class="top"><nav><a href="#words">Words</a><a href="#lessons">Lessons</a></nav></header>'
            f"<h1>{title}</h1>"
            '<img src="assets/images/missing.png">'
            '<a href="lesson1.html">Lesson link</a>'
            f"<script>window.UNIT_DATA={json.dumps(unit_data, ensure_ascii=False)};</script>"
            "</body></html>"
        ),
        encoding="utf-8",
    )


def write_s2_unit_index(unit: Path, *, lessons: list[dict] | None = None, title: str = "S2 Stable Unit", extra_text: str = "") -> None:
    lessons = lessons or [
        {"id": f"l{i}", "title": f"Lesson {i}", "questions": [{"id": f"q{i:03d}", "type": "practice"}]}
        for i in range(1, 8)
    ]
    unit_data = {
        "unit": 23,
        "title": title,
        "stage": "A2.2",
        "course": "Real English World",
        "vocab": [{"id": "v001", "word": "hello"}],
        "lessons": lessons,
        "practice": {
            lesson["id"]: [{"id": f"q{lesson['id'][1:]:0>2}{i:02d}", "type": "practice"} for i in range(1, 4)]
            for lesson in lessons
            if lesson.get("id")
        },
        "watch": [{"id": "w001", "text": "watch"}],
        "watchPractice": [{"id": "wq001", "type": "watch-check"}],
    }
    lesson_html = "".join(
        f'<details class="lesson" id="{lesson["id"]}"><summary>{lesson["title"]}</summary>'
        + "".join(f'<button data-activity-id="{item["id"]}">{item["id"]}</button>' for item in unit_data["practice"].get(lesson["id"], []))
        + "</details>"
        for lesson in lessons
    )
    (unit / "assets" / "images").mkdir(parents=True, exist_ok=True)
    (unit / "index.html").write_text(
        (
            "<!doctype html><html><head>"
            f"<title>{title}</title>"
            "<style>nav{max-width:1180px;display:flex;align-items:center;gap:8px;overflow:auto}</style>"
            "</head><body>"
            '<header class="top"><nav><a href="#words">Words</a><a href="#lessons">Lessons</a><a href="#watch">Watch</a><a href="#progress">Progress</a></nav></header>'
            f"<h1>{title}</h1>"
            '<section id="words"><h2>Vocabulary Builder</h2></section>'
            f'<section id="lessons">{lesson_html}</section>'
            '<section id="watch"><h2>Watch</h2></section>'
            '<section id="progress"><h2>Progress Result</h2></section>'
            f"<p>{extra_text}</p>"
            "<script>function applyUnitChrome(){} function renderVocab(){} function renderLessons(){} function renderWatch(){} function renderProgress(){} function bindAudio(){} function bindZoom(){}</script>"
            f"<script>window.UNIT_DATA={json.dumps(unit_data, ensure_ascii=False)};</script>"
            "</body></html>"
        ),
        encoding="utf-8",
    )


def node_check(path: Path) -> str:
    if not shutil.which("node"):
        return "SKIP: node not found"
    result = subprocess.run(["node", "--check", str(path)], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return "PASS"


def visible_text(html_text: str) -> str:
    html_text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<style\b[^>]*>.*?</style>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", html_text)


def main() -> int:
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="scorm_gui_smoke_") as tmp:
        root = Path(tmp) / "SmartCourses" / "01-Adventure"
        unit = root / "Adventure_world_unit_001"
        unit.mkdir(parents=True)
        write_unit_index(unit)
        real_root = Path(tmp) / "SmartCourses" / "02-Real"
        real_unit_001 = real_root / "Real_world_unit_001"
        real_unit_002 = real_root / "Real_world_unit_002"
        real_unit_001.mkdir(parents=True)
        real_unit_002.mkdir(parents=True)
        write_unit_index(real_unit_001, "Real Unit 1", unit_number=1, stage="A1.1")
        write_unit_index(real_unit_002, "Real Unit 2", unit_number=2, stage="A1.1")

        unit_json_meta = server.index_meta_from_text(
            "GW3_U006_A1_Guideline_V1_Moodle",
            '<html><head><title>German World Unit 6</title></head><body><script id="unit-json" type="application/json">'
            '{"unit_number":6,"course":"German World V3","level":"A1.2","cefr":"A1","title":"Zu Hause"}'
            "</script></body></html>",
        )
        assert unit_json_meta["course"] == "German World V3"
        assert unit_json_meta["sourceStage"] == "A1"
        assert unit_json_meta["title"] == "Zu Hause"

        cached_german_unit = APP_DIR / "unit_cache" / "test_hash" / "GW3_U006_A1_Guideline_V1_Moodle"
        german_root = Path(tmp) / "SmartCourses" / "05-German"
        assert server.detect_flw_language(german_root, cached_german_unit) == {"code": "05-german", "label": "German"}
        assert server.detect_flw_language(Path(tmp) / "SmartCourses", cached_german_unit) == {"code": "05-german", "label": "German"}

        wrong_identity_report = {
            "worldCode": "AEW",
            "unitId": "AEW-U006",
            "scormActivityExternalKey": "AEW-U006-UNITSCORM",
            "scormManifestIdentifier": "FLW_AEW_U006_SCORM12",
            "futureCmidNumber": "FLW_AEW_U006_UNITSCORM",
        }
        correct_german_target = {"worldCode": "GEW", "unitNumber": "006", "unitId": "GEW-U006"}
        assert len(server.scorm_export_identity_mismatches(correct_german_target, wrong_identity_report)) == 5
        try:
            server.validate_scorm_export_identity(correct_german_target, wrong_identity_report)
        except server.AppError as exc:
            assert "SCORM_EXPORT_IDENTITY_MISMATCH" in str(exc)
        else:
            raise AssertionError("Wrong-world SCORM export identity was not blocked")
        results["multilingualIdentityGuard"] = "PASS"

        rew_checkpoint_html = """<!doctype html><html><head><title>Real English World Unit 108</title></head><body>
<header><h1>Unit 108</h1></header><nav id="tabs"></nav><main id="app"></main>
<script>const UNIT = {"profile":{"papers":["Use of English","Reading","Listening"]}};
const stations=[['overview','Overview'],['use','Use of English'],['reading','Reading'],['listening','Listening'],['speaking','Speaking'],['writing','Writing'],['portfolio','Portfolio'],['dictation','Dictation'],['results','Repair / Results']];
let current='overview'; function show(st){current=st;render();} function render(){}</script></body></html>"""
        rew_checkpoint_sections = server.generic_sco_sections(rew_checkpoint_html)
        assert [item["id"] for item in rew_checkpoint_sections] == [
            "overview", "use-of-english", "reading", "listening", "speaking",
            "writing", "portfolio", "dictation", "repair-results",
        ]
        rew_reading_html = server.generic_section_sco_html(
            rew_checkpoint_html,
            "Real English World Unit 108",
            rew_checkpoint_sections[2],
        )
        assert 'let current="reading"' in rew_reading_html
        assert 'function show(st){st="reading";' in rew_reading_html
        assert "main > article" not in rew_reading_html
        assert ".part-actions .btn.secondary" in rew_reading_html
        rew_overview_identity = server.enrich_sco_with_identity(
            {
                "kind": rew_checkpoint_sections[0]["kind"],
                "id": rew_checkpoint_sections[0]["id"],
                "title": rew_checkpoint_sections[0]["title"],
                "identityKind": rew_checkpoint_sections[0].get("identityKind"),
                "identitySourceId": rew_checkpoint_sections[0].get("identitySourceId"),
            },
            {"unitId": "REW-U108", "unitNumber": "108", "worldCode": "REW"},
        )
        assert rew_overview_identity["componentKey"] == "UNIT"
        assert rew_overview_identity["scoIdentifier"] == "FLW_REW_U108_UNIT"

        rew_legacy_checkpoint_html = """<!doctype html><html><head><title>Real English World Unit 18</title></head><body>
<main id="app"></main><script>const UNIT = {"course":"Real English World","profile":{"papers":[]}};
const stations=[['overview','Overview'],['use','Use of English'],['reading','Reading'],['results','Results / Repair']];
let current='overview'; function show(st){current=st;render();} function render(){}</script></body></html>"""
        rew_legacy_sections = server.generic_sco_sections(rew_legacy_checkpoint_html)
        rew_legacy_identities = []
        for index_number, section in enumerate(rew_legacy_sections, start=1):
            sco = {
                "kind": section["kind"],
                "id": section["id"],
                "title": section["title"],
                "identityKind": section.get("identityKind"),
                "identitySourceId": section.get("identitySourceId"),
            }
            rew_legacy_identities.append(
                server.enrich_sco_with_identity(
                    sco,
                    {"unitId": "REW-U018", "unitNumber": "018", "worldCode": "REW"},
                    index_number,
                )["componentKey"]
            )
        assert rew_legacy_identities == ["OVERVIEW", "USE", "READING", "RESULT"]

        rew_checkpoint_string_stations = """<!doctype html><html><head><title>Real English World Unit 84</title></head><body>
<header><h1>Unit 84</h1></header><nav id="tabs"></nav><main id="app"></main>
<script>const UNIT = {"profile":{"papers":["Use of English","Reading"]}};
const stations=['overview','use','reading','listening','speaking','writing','dictation','results'];
const titles={overview:'Overview',use:'Use of English',reading:'Reading',listening:'Listening',speaking:'Speaking',writing:'Writing',dictation:'Dictation',results:'Results / Repair'};
let current='overview', answers={}; function show(s){current=s;render();} function render(){}</script></body></html>"""
        rew_string_sections = server.generic_sco_sections(rew_checkpoint_string_stations)
        assert [item["id"] for item in rew_string_sections] == [
            "overview", "use-of-english", "reading", "listening", "speaking",
            "writing", "dictation", "repair-results",
        ]
        rew_string_listening_html = server.generic_section_sco_html(
            rew_checkpoint_string_stations,
            "Real English World Unit 84",
            rew_string_sections[3],
        )
        assert 'let current="listening"' in rew_string_listening_html
        assert 'function show(s){s="listening";' in rew_string_listening_html

        chw_variant_html = """<!doctype html><html><head><title>中文世界 第91单元</title></head><body>
<nav><a href="#open">单元</a><a href="#goals">目标</a><a href="#vocab">词语</a>
<a href="#lesson1">第1课</a><a href="#lesson2">第2课</a><a href="#lesson3">第3课</a>
<a href="#lesson4">第4课</a><a href="#lesson5">第5课</a><a href="#lesson6">第6课</a>
<a href="#lesson7">第7课</a><a href="#watch">Watch</a><a href="#project">作品</a></nav><main>
<section id="open"><h1>第91单元</h1></section><section id="goals"><h2>本单元会做</h2></section>
<section id="vocab"><h2>核心词语和例句</h2></section>
<details class="lesson" id="lesson1"><summary><h2>第1课</h2></summary></details>
<details class="lesson" id="lesson2"><summary><h2>第2课</h2></summary></details>
<details class="lesson" id="lesson3"><summary><h2>第3课</h2></summary></details>
<details class="lesson" id="lesson4"><summary><h2>第4课</h2></summary></details>
<details class="lesson" id="lesson5"><summary><h2>第5课</h2></summary></details>
<details class="lesson" id="lesson6"><summary><h2>第6课</h2></summary></details>
<details class="lesson" id="lesson7"><summary><h2>第7课</h2></summary></details>
<section id="watch"><h2>故事</h2></section><section id="project"><h2>作品</h2></section>
</main></body></html>"""
        chw_variant_sections = server.generic_sco_sections(chw_variant_html)
        assert [item["id"] for item in chw_variant_sections] == [
            "goals", "vocab", "lesson1", "lesson2", "lesson3", "lesson4",
            "lesson5", "lesson6", "lesson7", "watch", "project",
        ]
        assert [item["kind"] for item in chw_variant_sections].count("lesson") == 7

        chw_exam_html = """<!doctype html><html><head><title>第132单元：HSK 5 模拟考试</title></head><body>
<h1>Chinese World</h1><nav><a href="#top">HSK 5</a><a href="#instructions">说明</a>
<a href="#listening">听力</a><a href="#reading">阅读</a><a href="#writing">写作</a><a href="#sheet">答题卡</a></nav>
<section id="top"></section><section id="instructions"></section><section id="listening"><div id="L01"></div></section>
<section id="reading"><div id="R01"></div></section><section id="writing"></section><section id="sheet"></section>
<div id="vocab"></div></body></html>"""
        chw_exam_sections = server.generic_sco_sections(chw_exam_html)
        assert [item["id"] for item in chw_exam_sections] == [
            "top", "instructions", "listening", "reading", "writing", "sheet",
        ]

        gew_generated_html = """<!doctype html><html><head><title>German World Unit 49</title></head><body>
<div id="app"></div><script id="unit-json" type="application/json">{"course":"German World","unit_number":49}</script>
<script>function appHtml(){return `<section class="hero"></section><section id="vb"></section>
<section id="lessons"><div id="lessonBox"></div></section><section id="watch"></section>
<section id="checkpoint"></section><section id="practice"></section><section id="progress"></section>`;}
function renderLessons(){return [
lesson(1,'Vocabulary','Context',one),lesson(2,'Grammar','Precision',two),
lesson(3,'Listening','Evidence',three),lesson(4,'Reading','Sources',four),
lesson(5,'Speaking','Defend',five),lesson(6,'Writing','Revise',six),
lesson(7,'Project','Transfer',seven)];}</script></body></html>"""
        gew_generated_sections = server.generic_sco_sections(gew_generated_html)
        assert [item["id"] for item in gew_generated_sections] == [
            "vb", "lesson-01", "lesson-02", "lesson-03", "lesson-04", "lesson-05",
            "lesson-06", "lesson-07", "watch", "c1-checkpoint", "practice", "progress",
        ]
        assert [item["kind"] for item in gew_generated_sections].count("lesson") == 7
        assert gew_generated_sections[3]["identitySourceId"] == "hoeren"
        assert gew_generated_sections[3]["identityKind"] == "section"
        assert gew_generated_sections[10]["identitySourceId"] == "ueben"
        gew_listening_identity = server.enrich_sco_with_identity(
            {
                "kind": gew_generated_sections[3]["kind"],
                "id": gew_generated_sections[3]["id"],
                "title": gew_generated_sections[3]["title"],
                "identityKind": gew_generated_sections[3].get("identityKind"),
                "identitySourceId": gew_generated_sections[3].get("identitySourceId"),
            },
            {"unitId": "GEW-U049", "unitNumber": "049", "worldCode": "GEW"},
        )
        assert gew_listening_identity["componentKey"] == "HOEREN"
        assert gew_listening_identity["scoIdentifier"] == "FLW_GEW_U049_HOEREN"
        gew_lesson_two_html = server.generic_section_sco_html(
            gew_generated_html,
            "German World Unit 49",
            gew_generated_sections[2],
        )
        assert "#lessonBox > details.lesson:nth-of-type(2)" in gew_lesson_two_html
        assert "#lessonBox > details.lesson" in gew_lesson_two_html
        results["variantSectionDetection"] = "PASS"

        validation = server.validate_unit(unit)
        assert any(item["ref"] == "assets/images/missing.png" and item["kind"] == "image" for item in validation["missingRefs"])
        results["missingRefs"] = "PASS"

        imported = server.import_unit_asset(
            unit,
            "replacement.png",
            # Valid transparent 1x1 PNG so Moodle-side course-image validation
            # exercises the same raster contract as production packages.
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL5WQAAAABJRU5ErkJggg==",
            "image",
        )
        assert imported["path"].startswith("assets/images/")
        results["importAsset"] = "PASS"

        replaced = server.replace_index_reference(unit, "assets/images/missing.png", imported["path"])
        assert replaced["count"] == 1
        results["replaceReference"] = "PASS"

        before_restore = (unit / "index.html").read_text(encoding="utf-8")
        server.write_text(unit / "index.html", before_restore.replace("Lesson link", "Changed link"))
        backups = server.list_unit_backups(unit)
        assert backups
        restored = server.restore_unit_backup(unit, backups[0]["stamp"], backups[0]["path"])
        assert restored["path"] == "index.html"
        if imported["path"] not in (unit / "index.html").read_text(encoding="utf-8"):
            assert server.replace_index_reference(unit, "assets/images/missing.png", imported["path"])["count"] == 1
        results["restoreBackup"] = "PASS"

        structure = server.scorm_structure_preview(unit, {"launchFile": "index.html"})
        assert structure["scoCount"] >= 3 and structure["lessonScoCount"] == 1
        results["scormPreview"] = "PASS"

        export_dir = Path(tmp) / "exports"
        hidden_nav_export = server.export_scorm(unit, {"launchFile": "index.html", "exportDir": str(export_dir)})
        assert hidden_nav_export["keepTopNavBar"] is False
        assert hidden_nav_export["topNavBarStyleInjected"] is True
        assert hidden_nav_export["courseImage"]["packagePath"] == imported["path"]
        assert hidden_nav_export["courseImage"]["selectionSource"] == "html_img"
        with zipfile.ZipFile(hidden_nav_export["zipPath"]) as package:
            assert "flw-top-nav-sco-style" in package.read("index.html").decode("utf-8")
            assert imported["path"] in package.namelist()
        kept_nav_export = server.export_scorm(unit, {"launchFile": "index.html", "exportDir": str(export_dir), "keepTopNavBar": True})
        assert kept_nav_export["keepTopNavBar"] is True
        assert kept_nav_export["topNavBarStyleInjected"] is False
        with zipfile.ZipFile(kept_nav_export["zipPath"]) as package:
            assert "flw-top-nav-sco-style" not in package.read("index.html").decode("utf-8")
        results["topNavExportOption"] = "PASS"

        language = server.detect_flw_language(root, unit)
        assert language == {"code": "01-adventure", "label": "Adventure"}
        assert server.normalize_moodle_url("192.168.129.79") == "https://192.168.129.79"
        assert server.normalize_moodle_url("http://moodle.local/") == "http://moodle.local"
        target = server.moodle_target_from_options(
            {
                "moodleUrl": "moodle.local",
                "moodlePhpPath": str(Path(tmp) / "php.exe"),
                "moodleConfigPath": str(Path(tmp) / "config.php"),
            }
        )
        assert target["moodleUrl"] == "https://moodle.local"
        assert target["moodlePhpPath"].name == "php.exe"
        assert target["moodleConfigPath"].name == "config.php"
        assert server.normalize_flw_import_mode({"flwImportMode": "Add New"}) == "add_new"
        assert server.normalize_flw_import_mode({"batchFlwImportMode": "Add New Unit"}, batch=True) == "add_new"
        assert server.normalize_flw_import_mode({"batchFlwImportMode": "Rebuild Selected FLW Scope"}, batch=True) == "clear_add"
        assert server.normalize_flw_import_mode({"batchFlwImportMode": "Clear and Add"}, batch=True) == "clear_add"
        direct_manifest = server.direct_flw_manifest(root, unit, hidden_nav_export, "20260101_010101_000000")
        assert direct_manifest["kind"] == "smartcourses_scorm_direct"
        assert direct_manifest["items"][0]["code"] == "01-adventure"
        assert direct_manifest["items"][0]["export"]["zipPath"] == hidden_nav_export["zipPath"]
        assert direct_manifest["items"][0]["courseImage"]["packagePath"] == imported["path"]
        assert direct_manifest["items"][0]["targetMetadata"]["courseImage"]["packagePath"] == imported["path"]
        results["directFlwManifest"] = "PASS"

        p1_dir = Path(tmp) / "p1_contract"
        p1_dir.mkdir()
        stage_map = p1_dir / "stage.json"
        section_map = p1_dir / "section.json"
        scorm_map = p1_dir / "scorm.json"
        p1_manifest = p1_dir / "manifest.json"
        stage_map.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "stageCourses": {
                        "FLW_REW_A2": {
                            "WorldCode": "REW",
                            "DeploymentStageCode": "A2",
                            "courseExternalKey": "FLW_REW_A2",
                            "moodleCourseId": 342,
                            "moodleCourseIdnumber": "FLW_REW_A2",
                            "status": "REUSE_STAGE_COURSE",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        section_map.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "unitSections": {
                        "REW-U023": {
                            "UnitID": "REW-U023",
                            "WorldCode": "REW",
                            "DeploymentStageCode": "A2",
                            "courseExternalKey": "FLW_REW_A2",
                            "moodleCourseId": 342,
                            "moodleSectionId": 812,
                            "moodleSectionNumber": 5,
                            "sectionName": "U023 — Weather",
                            "status": "REUSE_SECTION",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        scorm_map.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "unitScormActivities": {
                        "REW-U023-UNITSCORM": {
                            "UnitID": "REW-U023",
                            "UnitSCORMActivityID": "REW-U023-UNITSCORM",
                            "WorldCode": "REW",
                            "DeploymentStageCode": "A2",
                            "courseExternalKey": "FLW_REW_A2",
                            "moodleCourseId": 342,
                            "moodleSectionId": 812,
                            "stableCmidNumber": "FLW_REW_U023_UNITSCORM",
                            "currentRevision": 4,
                            "currentCmid": 927,
                            "currentScormId": 54,
                            "packageSha256": "current-package",
                            "packageContentSha256": "current-content",
                            "componentScoIdentifiers": ["FLW_REW_U023_L02"],
                            "status": "CURRENT",
                            "history": [
                                {
                                    "cmid": 841,
                                    "scormId": 41,
                                    "deploymentRevision": 3,
                                    "retiredCmidNumber": "FLW_REW_U023_UNITSCORM_REV3_SUPERSEDED",
                                    "packageSha1": "historical-package-sha1",
                                    "packageSha256": "historical-package",
                                    "packageContentSha256": "historical-content",
                                    "componentScoIdentifiers": ["FLW_REW_U023_L02"],
                                    "tracking": {"trackedScoIdentifiers": ["FLW_REW_U023_L02"]},
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        p1_manifest.write_text(
            json.dumps(
                {
                    "kind": "smartcourses_scorm_batch",
                    "items": [
                        {
                            "unitId": "REW-U023",
                            "scormActivityExternalKey": "REW-U023-UNITSCORM",
                            "componentMappings": [
                                {
                                    "componentId": "REW-U023-L02",
                                    "componentKey": "L02",
                                    "kind": "lesson",
                                    "title": "Lesson 2",
                                    "scoIdentifier": "FLW_REW_U023_L02",
                                    "launchFile": "scos/lesson-l02.html",
                                }
                            ],
                            "microActivityMappings": [
                                {
                                    "microActivityId": "REW-U023-L02-Q003",
                                    "parentComponentId": "REW-U023-L02",
                                    "trackAsSeparateSco": False,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        contract = P1ContentDeploymentContract(stage_map, section_map, scorm_map, [p1_manifest])
        assert P1_CONTENT_DEPLOYMENT_CONTRACT_VERSION == "1.0"
        assert contract.resolve_world_stage_from_course(342)["courseExternalKey"] == "FLW_REW_A2"
        assert contract.resolve_unit_from_section(342, 812)["UnitID"] == "REW-U023"
        assert contract.resolve_current_unit_deployment("REW-U023")["cmid"] == 927
        assert contract.resolve_historical_unit_deployment("REW-U023", 841)["status"] == "SUPERSEDED"
        assert contract.resolve_historical_unit_deployment("REW-U023", 841)["packageSha256"] == "historical-package"
        assert contract.resolve_activity_from_cmid_and_sco(927, "FLW_REW_U023_L02")["ComponentActivityID"] == "REW-U023-L02"
        assert contract.resolve_micro_activity_parent("REW-U023-L02-Q003")["parentComponentActivityID"] == "REW-U023-L02"
        assert contract.resolve_deployment_freshness("REW-U023")["deploymentState"] == "CURRENT"
        assert contract.validate_invariants()["status"] == "PASS"
        results["p1ContentDeploymentContract"] = "PASS"

        batch_roots = server.discover_batch_language_roots(str(root))
        assert [language["code"] for language in batch_roots] == ["01-adventure", "02-real"]
        assert server.batch_unit_numbers(batch_roots, {"batchAllUnits": True}) == ["001", "002"]
        all_pairs = [(language["code"], unit_number) for language, unit_number in server.batch_unit_pairs(batch_roots, {"batchAllUnits": True})]
        assert all_pairs == [("01-adventure", "001"), ("02-real", "001"), ("02-real", "002")]
        assert server.batch_unit_numbers(batch_roots, {"batchAllUnits": False, "batchUnitStart": "001", "batchUnitEnd": "003"}) == ["001", "002", "003"]
        range_pairs = [(language["code"], unit_number) for language, unit_number in server.batch_unit_pairs(batch_roots, {"batchAllUnits": False, "batchUnitStart": "001", "batchUnitEnd": "003"})]
        assert len(range_pairs) == 6
        current_world_roots = server.batch_language_roots_for_options(
            str(real_root),
            {"batchAllUnits": False, "batchWorldScope": "current"},
        )
        assert [language["code"] for language in current_world_roots] == ["02-real"]
        specific_world_roots = server.batch_language_roots_for_options(
            str(root),
            {"batchAllUnits": False, "batchWorldScope": "specific", "batchSpecificWorld": "01-adventure"},
        )
        assert [language["code"] for language in specific_world_roots] == ["01-adventure"]
        specific_range_manifest = server.planned_batch_manifest(
            str(root),
            {
                "batchAllUnits": False,
                "batchUnitStart": "001",
                "batchUnitEnd": "002",
                "batchWorldScope": "specific",
                "batchSpecificWorld": "02-real",
            },
            "20260101_010101_000000",
        )
        assert [language["code"] for language in specific_range_manifest["languageRoots"]] == ["02-real"]
        assert specific_range_manifest["plannedCount"] == 2
        batch_job_state = {"jobId": "snapshot-test", "status": "running", "items": [{"unit": "001"}], "thread": object()}
        batch_job_snapshot = server.public_batch_job(batch_job_state)
        batch_job_state["items"][0]["unit"] = "999"
        batch_job_state["lateMutation"] = True
        assert "thread" not in batch_job_snapshot
        assert "lateMutation" not in batch_job_snapshot
        assert batch_job_snapshot["items"][0]["unit"] == "001"
        reusable_zip = Path(tmp) / "reusable-dry-run.zip"
        reusable_zip.write_bytes(b"zip")
        promotion_options = {
            "root": str(root),
            "flwDryRun": False,
            "batchAllUnits": True,
            "batchFlwImportMode": "overwrite",
            "batchProductionScope": "",
            "launchFile": "index.html",
            "autocomplete": True,
        }
        completed_dry_run_job = {
            "status": "complete",
            "root": str(root),
            "options": {**promotion_options, "flwDryRun": True},
            "items": [
                {
                    "status": "exported",
                    "manifestSchemaVersion": 2,
                    "targetMetadata": {"unitId": "AEW-U001"},
                    "export": {"zipPath": str(reusable_zip)},
                }
            ],
        }
        assert server.completed_dry_run_exports_can_be_promoted(completed_dry_run_job, promotion_options)
        assert not server.completed_dry_run_exports_can_be_promoted(
            completed_dry_run_job,
            {**promotion_options, "batchUnitEnd": "999"},
        )

        recovery_jobs_dir = Path(tmp) / "batch_jobs"
        recovery_job_dir = recovery_jobs_dir / "interrupted_test"
        recovery_job_dir.mkdir(parents=True)
        interrupted_zip = Path(tmp) / "interrupted-reusable.zip"
        interrupted_zip.write_bytes(b"zip")
        interrupted_manifest = Path(tmp) / "interrupted_batch" / "batch_manifest.json"
        interrupted_manifest.parent.mkdir()
        interrupted_manifest.with_name("moodle_import_stdout.log").write_text(
            "Imported TEST-U001 successfully\n",
            encoding="utf-8",
        )
        interrupted_job = {
            "jobId": "interrupted_test",
            "status": "running",
            "phase": "importing",
            "processId": 99999999,
            "itemCount": 1,
            "exportedCount": 1,
            "manifestPath": str(interrupted_manifest),
            "items": [
                {
                    "code": "01-adventure",
                    "unit": "001",
                    "status": "exported",
                    "manifestSchemaVersion": 2,
                    "targetMetadata": {"unitId": "AEW-U001"},
                    "export": {"zipPath": str(interrupted_zip)},
                }
            ],
        }
        (recovery_job_dir / "job.json").write_text(json.dumps(interrupted_job), encoding="utf-8")
        original_batch_jobs_dir = server.BATCH_JOBS_DIR
        original_batch_jobs = server.BATCH_JOBS
        try:
            server.BATCH_JOBS_DIR = recovery_jobs_dir
            server.BATCH_JOBS = {}
            recovered = server.reconcile_stale_batch_jobs()
            assert recovered == [
                {
                    "jobId": "interrupted_test",
                    "previousStatus": "running",
                    "previousProcessId": 99999999,
                    "reusableExportCount": 1,
                    "expectedCount": 1,
                }
            ]
            recovered_job = server.BATCH_JOBS["interrupted_test"]
            assert recovered_job["status"] == "interrupted"
            assert recovered_job["phase"] == "interrupted"
            assert recovered_job["interruptionReason"] == "EDITOR_BACKEND_PROCESS_ENDED"
            assert recovered_job["canResume"] is True
            assert recovered_job["resumeReusableExportCount"] == 1
            assert recovered_job["resumeRequiresExportCount"] == 0
            assert recovered_job["resumeWillReuseAllExports"] is True
            assert recovered_job["lastImporterOutput"] == "Imported TEST-U001 successfully"
            assert server.reconcile_stale_batch_jobs() == []
        finally:
            server.BATCH_JOBS_DIR = original_batch_jobs_dir
            server.BATCH_JOBS = original_batch_jobs
        results["interruptedBatchRecovery"] = "PASS"

        all_manifest = server.planned_batch_manifest(str(root), {"batchAllUnits": True}, "20260101_010101_000000")
        assert all_manifest["allAvailableUnits"] is True
        assert all_manifest["plannedCount"] == 3
        assert all_manifest["missingCount"] == 0
        assert all_manifest["stageGroupCount"] >= 1
        assert all_manifest["catalogValidation"]["expectedTotal"] == 660
        assert all_manifest["catalogValidation"]["availableValidTotal"] == 3
        assert all_manifest["catalogValidation"]["spanishSourcePresent"] is False
        assert all_manifest["items"][0]["batchTarget"]["mode"] == "overwrite"
        rebuild_manifest = server.planned_batch_manifest(
            str(root),
            {"batchAllUnits": True, "batchFlwImportMode": "Rebuild Selected FLW Scope"},
            "20260101_010101_000000",
        )
        assert rebuild_manifest["items"][0]["batchTarget"]["mode"] == "clear_add"
        assert rebuild_manifest["s7BatchArchitecture"]["s8VisibleOperationName"] == "Rebuild Selected FLW Scope"
        assert rebuild_manifest["s7BatchArchitecture"]["s8ScopeModel"] == "WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID"
        planned_counts = {language["code"]: language["plannedUnitCount"] for language in all_manifest["languageRoots"]}
        assert planned_counts == {"01-adventure": 1, "02-real": 2}
        results["batchFlwPlanning"] = "PASS"

        real_unit_023 = real_root / "Real_world_unit_023"
        real_unit_061 = real_root / "Real_world_unit_061"
        real_unit_085 = real_root / "Real_world_unit_085"
        real_unit_conflict = real_root / "Real_world_unit_024"
        for candidate in (real_unit_023, real_unit_061, real_unit_085, real_unit_conflict):
            candidate.mkdir(parents=True)
        write_unit_index(real_unit_023, "Real Unit 23", unit_number=23, stage="A2.2")
        write_unit_index(real_unit_061, "Real Unit 61", unit_number=61)
        write_unit_index(real_unit_085, "Real Unit 85", unit_number=85)
        write_unit_index(real_unit_conflict, "Real Unit Conflict", unit_number=24, stage="A1")

        real_language = {"code": "02-real", "label": "Real"}
        target_001 = server.resolve_deployment_target(real_language, real_root, real_unit_001, "001", server.index_meta(real_unit_001))
        assert target_001["worldCode"] == "REW"
        assert target_001["deploymentStageCode"] == "A1"
        assert target_001["courseExternalKey"] == "FLW_REW_A1"
        target_023 = server.resolve_deployment_target(real_language, real_root, real_unit_023, "023", server.index_meta(real_unit_023))
        assert target_023["worldCode"] == "REW"
        assert target_023["sourceStage"] == "A2.2"
        assert target_023["deploymentStageCode"] == "A2"
        assert target_023["courseExternalKey"] == "FLW_REW_A2"
        target_061 = server.resolve_deployment_target(real_language, real_root, real_unit_061, "061", server.index_meta(real_unit_061))
        assert target_061["deploymentStageCode"] == "B2"
        assert target_061["courseExternalKey"] == "FLW_REW_B2"
        target_085 = server.resolve_deployment_target(real_language, real_root, real_unit_085, "085", server.index_meta(real_unit_085))
        assert target_085["deploymentStageCode"] == "C1"
        assert target_085["courseExternalKey"] == "FLW_REW_C1"
        target_conflict = server.resolve_deployment_target(real_language, real_root, real_unit_conflict, "024", server.index_meta(real_unit_conflict))
        assert target_conflict["preflightStatus"] == "STAGE_CONFLICT"

        unresolved_root = Path(tmp) / "SmartCourses" / "07-Spanish"
        unresolved_unit = unresolved_root / "Spanish_world_unit_001"
        unresolved_unit.mkdir(parents=True)
        write_unit_index(unresolved_unit, "Spanish Unit 1", unit_number=1)
        target_unresolved = server.resolve_deployment_target({"code": "07-spanish", "label": "Spanish"}, unresolved_root, unresolved_unit, "001", server.index_meta(unresolved_unit))
        assert target_unresolved["preflightStatus"] == "STAGE_UNRESOLVED"

        invalid_config = Path(tmp) / "bad_course_map.json"
        invalid_config.write_text('{"schemaVersion": 1, "worlds": {"02-real": {"worldCode": "REW"}}}', encoding="utf-8")
        invalid_target = server.resolve_deployment_target(real_language, real_root, real_unit_001, "001", server.index_meta(real_unit_001), invalid_config)
        assert invalid_target["preflightStatus"] == "INVALID_CONFIG"

        all_world_parent = Path(tmp) / "AllWorlds"
        expected_world_codes = [language["code"] for language in server.FLW_LANGUAGE_ROOTS]
        for language in server.FLW_LANGUAGE_ROOTS:
            world_root = all_world_parent / language["code"].replace("-", "-").title()
            world_root.mkdir(parents=True)
            sample = world_root / f"{language['code']}_unit_001"
            sample.mkdir()
            write_unit_index(sample, f"{language['label']} Unit 1", unit_number=1, stage="A1.1")
        all_world_roots = server.discover_batch_language_roots(str(all_world_parent))
        assert [language["code"] for language in all_world_roots] == expected_world_codes
        all_world_manifest = server.planned_batch_manifest(str(all_world_parent), {"batchAllUnits": True}, "20260101_010101_000000")
        assert all_world_manifest["catalogValidation"]["spanishSourcePresent"] is True
        assert all_world_manifest["catalogValidation"]["selectedTotal"] == len(expected_world_codes)
        scoped_world_manifest = server.planned_batch_manifest(
            str(all_world_parent),
            {"batchAllUnits": True, "batchProductionScope": "seven_world_production"},
            "20260101_010101_000000",
        )
        assert scoped_world_manifest["catalogValidation"]["gate"] == "S7B"
        assert scoped_world_manifest["catalogValidation"]["expectedTotal"] == 600
        assert scoped_world_manifest["catalogValidation"]["selectedTotal"] == len(server.S7B_PRODUCTION_WORLD_CODES)
        assert scoped_world_manifest["catalogValidation"]["spanishReadinessStatus"] == "OUT_OF_SCOPE"
        assert all(row["sourceRootCode"] != "07-spanish" for row in scoped_world_manifest["catalogValidation"]["worlds"])
        assert server.S7B_PRODUCTION_EXPECTED_UNIT_COUNTS["05-german"] == 60

        isolated_spanish_root = Path(tmp) / "OnlySpanish" / "07-Spanish"
        isolated_spanish_unit = isolated_spanish_root / "Spanish_world_unit_001"
        isolated_spanish_unit.mkdir(parents=True)
        write_unit_index(isolated_spanish_unit, "Isolated Spanish Unit 1", unit_number=1)
        blocked_manifest = server.planned_batch_manifest(str(isolated_spanish_root), {"batchAllUnits": True}, "20260101_010101_000000")
        assert blocked_manifest["blockedForRealImport"] is True
        assert blocked_manifest["preflight"]["statusCounts"]["STAGE_UNRESOLVED"] == 1
        results["s1DeploymentMetadata"] = "PASS"

        real_unit_017 = real_root / "Real_world_unit_017"
        real_unit_018 = real_root / "Real_world_unit_018"
        real_unit_019 = real_root / "Real_world_unit_019"
        real_unit_020 = real_root / "Real_world_unit_020"
        real_unit_036 = real_root / "Real_world_unit_036"
        for candidate in (real_unit_017, real_unit_018, real_unit_019, real_unit_020, real_unit_036):
            candidate.mkdir(exist_ok=True)
        write_unit_index(real_unit_017, "Real Unit 17", unit_number=17, stage="A1.2")
        write_unit_index(real_unit_018, "Real Unit 18", unit_number=18, stage="A1.2")
        write_unit_index(real_unit_019, "Real Unit 19", unit_number=19, stage="A2.1")
        write_unit_index(real_unit_020, "Real Unit 20", unit_number=20, stage="A2.1")
        write_unit_index(real_unit_036, "Real Unit 36", unit_number=36, stage="A2.2")
        a2_targets = [
            server.resolve_deployment_target(real_language, real_root, candidate, unit, server.index_meta(candidate))
            for candidate, unit in ((real_unit_019, "019"), (real_unit_020, "020"), (real_unit_023, "023"), (real_unit_036, "036"))
        ]
        assert {target["courseExternalKey"] for target in a2_targets} == {"FLW_REW_A2"}
        assert {target["deploymentStageCode"] for target in a2_targets} == {"A2"}
        mixed_stage_manifest = server.planned_batch_manifest(
            str(real_root),
            {"batchAllUnits": False, "batchUnitStart": "017", "batchUnitEnd": "020"},
            "20260101_010101_000000",
        )
        rew_groups = [group for group in mixed_stage_manifest["stageGroups"] if group["worldCode"] == "REW"]
        assert [(group["deploymentStageCode"], group["courseExternalKey"], group["unitIds"]) for group in rew_groups] == [
            ("A1", "FLW_REW_A1", ["REW-U017", "REW-U018"]),
            ("A2", "FLW_REW_A2", ["REW-U019", "REW-U020"]),
        ]
        php_importer = (server.APP_DIR / "scripts" / "import_scorm_pilot_to_moodle.php").read_text(encoding="utf-8")
        assert "const MOODLE_COURSE_ID_FLOOR = 200;" in php_importer
        assert "function ensure_moodle_course_id_floor" in php_importer
        assert "ensure_moodle_course_id_floor();" in php_importer
        assert "int $resetstart = MOODLE_COURSE_ID_FLOOR" in php_importer
        assert "function stage_course_definition" in php_importer
        assert "function resolve_stage_course_group" in php_importer
        assert "function ensure_stage_course_self_enrolment" in php_importer
        assert "function sync_stage_course_image" in php_importer
        assert "function stage_group_course_image_candidate" in php_importer
        assert "'filearea' => 'overviewfiles'" in php_importer
        assert "COURSE_IMAGE_UNCHANGED" in php_importer
        assert "WOULD_SET_COURSE_IMAGE_ON_CREATE" in php_importer
        assert "enrol_is_enabled('self')" in php_importer
        assert "$data->status = ENROL_INSTANCE_ENABLED;" in php_importer
        assert "$data->customint6 = 1;" in php_importer
        assert "ensure_stage_course_self_enrolment($created);" in php_importer
        assert "'selfEnrolment' => stage_course_self_enrolment_state($created)" in php_importer
        assert "function filepool_retry" in php_importer
        assert "function scorm_filepool_failure_is_retryable" in php_importer
        assert "[S5 FILEPOOL_RETRY]" in php_importer
        assert "filePoolRetryResult" in php_importer
        assert "function recover_orphaned_filepool_temp" in php_importer
        assert "function cleanup_redundant_filepool_temps" in php_importer
        assert "function mapping_predates_recreated_course" in php_importer
        assert "staleSectionMappingRecovered" in php_importer
        assert "staleScormMappingRecovered" in php_importer
        assert "STAGE_COURSE_RECREATED_AFTER_MAPPING" in php_importer
        assert "COURSE_IDNUMBER_CONFLICT" in php_importer
        assert "UNIT_SECTION_PENDING_S4" in php_importer
        import_by_language_body = php_importer.split("function import_by_language", 1)[1].split("function preview_course_map", 1)[0]
        assert "resolve_stage_course_group" in import_by_language_body
        assert "import_item(" not in import_by_language_body
        assert "find_or_create_pilot_section(" not in import_by_language_body
        assert "clear_courses_above_id(" not in import_by_language_body
        assert "delete_course(" not in import_by_language_body
        assert "course_delete_module(" not in import_by_language_body
        assert "s7_enforces_unique_unit_for_add_new" in import_by_language_body
        results["s3StageCourseResolver"] = "PASS"

        frontend_source = (server.APP_DIR / "static" / "app.js").read_text(encoding="utf-8")
        assert "function exportResultDisclosureState" in frontend_source
        assert 'key: "raw-log"' in frontend_source
        assert "preserveDisclosureState: true" in frontend_source
        assert "function batchFailedUnitDetails" in frontend_source
        assert "function formatBatchFailedUnit" in frontend_source
        assert "Unit Moodle deployments failed:" in frontend_source
        assert "Failed Unit details:" in frontend_source
        assert "Moodle deployment was safely blocked before changes" in frontend_source

        assert "function unit_section_definition" in php_importer
        assert "function resolve_unit_section" in php_importer
        assert "function enforce_unit_section_order" in php_importer
        assert "FLW_UNIT_KEY:" in php_importer
        assert "UNIT_SECTION_DUPLICATE" in php_importer
        assert "UNIT_SECTION_TARGET_MISSING" in php_importer
        assert "UNIT_STAGE_MOVE_REQUIRED" in php_importer
        assert "SCORM_PENDING_S5" in php_importer
        assert "resolve_unit_section" in import_by_language_body
        assert "import_item(" not in import_by_language_body
        assert "find_or_create_pilot_section(" not in import_by_language_body
        results["s4UnitSectionResolver"] = "PASS"

        s2_root = Path(tmp) / "S2SmartCourses" / "02-Real"
        s2_unit = s2_root / "Real_world_unit_023"
        s2_unit.mkdir(parents=True)
        seven_lessons = [
            {"id": f"l{i}", "title": f"Lesson {i}", "questions": [{"id": f"q{i:03d}", "type": "practice"}]}
            for i in range(1, 8)
        ]
        seven_lessons[2]["questions"] = [{"id": f"q3{i:03d}", "type": "practice"} for i in range(1, 21)]
        write_s2_unit_index(s2_unit, lessons=seven_lessons, title="S2 Stable Unit")
        s2_export_dir = Path(tmp) / "s2_exports"
        s2_options = {"root": str(s2_root), "launchFile": "index.html", "exportDir": str(s2_export_dir), "title": "S2 Stable Unit"}
        s2_first = server.export_scorm(s2_unit, s2_options)
        s2_second = server.export_scorm(s2_unit, {**s2_options, "exportDir": str(Path(tmp) / "s2_exports_2")})

        def s2_identity_tuple(report: dict):
            components = [
                (item["componentId"], item["scoIdentifier"], item["kind"], item["sourceId"])
                for item in report["componentMappings"]
            ]
            return (
                report["scormManifestIdentifier"],
                report["scormActivityExternalKey"],
                components,
            )

        assert s2_identity_tuple(s2_first) == s2_identity_tuple(s2_second)
        assert s2_first["scormManifestIdentifier"] == "FLW_REW_U023_SCORM12"
        assert s2_first["scormActivityExternalKey"] == "REW-U023-UNITSCORM"
        assert any(item["componentId"] == "REW-U023-L01" and item["scoIdentifier"] == "FLW_REW_U023_L01" for item in s2_first["componentMappings"])
        assert any(item["componentId"] == "REW-U023-VOCAB" for item in s2_first["componentMappings"])
        assert any(item["componentId"] == "REW-U023-WATCH" for item in s2_first["componentMappings"])
        assert any(item["componentId"] == "REW-U023-RESULT" for item in s2_first["componentMappings"])
        assert s2_first["lessonScoCount"] == 7
        assert s2_first["sectionScoCount"] > 1
        assert s2_first["flwNavigatorPrimary"] is True
        assert s2_first["flwNavigatorInjectedCount"] == s2_first["sectionScoCount"]
        assert s2_first["resumeStorage"] == ["cmi.core.lesson_location", "cmi.suspend_data"]
        assert s2_first["moodleScoLaunchMechanism"] == "/mod/scorm/player.php?scoid=<moodle scorm_scoes.id>"
        assert not any("-Q" in item["componentId"] for item in s2_first["componentMappings"])
        assert any(item["parentComponentId"] == "REW-U023-L03" and item["trackAsSeparateSco"] is False for item in s2_first["microActivityMappings"])
        with zipfile.ZipFile(s2_first["zipPath"]) as package:
            scorm_runtime = package.read("assets/scorm/scorm_api.js").decode("utf-8")
            assert "FLWScormRecordComponent" in scorm_runtime
            assert "cmi.core.lesson_location" in scorm_runtime
            assert "cmi.suspend_data" in scorm_runtime
            assert "cmi.core.session_time" in scorm_runtime
            assert "FLW_SKIP_SCORM_INIT" in scorm_runtime
            lesson_one_html = package.read("scos/lesson-l01.html").decode("utf-8")
            assert "flw-unit-navigator-config" in lesson_one_html
            assert '"currentComponentId":"REW-U023-L01"' in lesson_one_html
            assert '"scoIdentifier":"FLW_REW_U023_L02"' in lesson_one_html
            assert "Previous" in lesson_one_html and "Next" in lesson_one_html and "Lessons" in lesson_one_html
            assert "Moodle adlnav stable identifier map" in lesson_one_html
            assert "player.php" in lesson_one_html and "scoid" in lesson_one_html
            assert "body > nav:not(#flw-unit-navigator)" in lesson_one_html
            assert "body > nav,\n" not in lesson_one_html
            assert "decodeMoodleUrl" in lesson_one_html
            assert 'new URL(href, window.location.href).href' in lesson_one_html
            assert '"navigatorVersion":10' in lesson_one_html
            assert 'flw-nav-progress' in lesson_one_html
            assert 'flw-nav-panel' in lesson_one_html
            assert 'display: block !important;' in lesson_one_html
            assert 'max-width: none !important;' in lesson_one_html
            assert 'overflow: visible !important;' in lesson_one_html
            assert 'nav{max-width:1180px;display:flex;align-items:center;gap:8px;overflow:auto}' in lesson_one_html
            assert 'Open lesson list' in lesson_one_html
            assert 'aria-expanded' in lesson_one_html
            assert 'inline: "nearest"' in lesson_one_html
            assert '@view-transition' in lesson_one_html
            assert 'flw-nav-booting' in lesson_one_html
            assert 'prefetchLocalComponent(previousComponent)' in lesson_one_html
            assert 'navigateLocal(href)' in lesson_one_html
            assert 'transition-background' in lesson_one_html
            assert "decodeEntities(urlMatch[1])" not in lesson_one_html
            assert "extractObjectAt" in lesson_one_html
            assert '"([0-9]+)"\\\\s*:\\\\s*\\\\{[\\\\s\\\\S]{0,1600}?' not in lesson_one_html
            assert "isMoodleActivityAutoLaunch" in lesson_one_html
            assert "lastComponentId" in lesson_one_html
            assert "currentStorageKey" in lesson_one_html
            assert "frameElement" in lesson_one_html
            assert "hideMoodleNativeScormToc" in lesson_one_html
            assert "installFramedImageModalCentering" in lesson_one_html
            assert "centerVisibleImageModals" in lesson_one_html
            assert "data-flw-visible-frame-centered" in lesson_one_html
            assert "setImageViewerScrollLock" in lesson_one_html
            assert "data-flw-image-viewer-open" in lesson_one_html
            assert "preventViewerScroll" in lesson_one_html
            assert "data-flw-viewer-vertical-lift" in lesson_one_html
            assert 'data-flw-viewer-vertical-lift", "0"' in lesson_one_html
            assert "unobstructedParentViewport" in lesson_one_html
            assert "data-flw-viewer-viewport-top" in lesson_one_html
            assert "data-flw-viewer-viewport-bottom" in lesson_one_html
            assert "mediaMaxWidth" in lesson_one_html
            assert "mediaMaxHeight" in lesson_one_html
            assert 'media.style.setProperty("position", "absolute", "important")' in lesson_one_html
            assert 'media.style.setProperty("width", "auto", "important")' in lesson_one_html
            assert 'media.style.setProperty("height", "auto", "important")' in lesson_one_html
            assert "button[id*='close' i]" in lesson_one_html
            assert "FLW_SKIP_SCORM_INIT" in lesson_one_html
            assert lesson_one_html.find('flw-unit-navigator-config') < lesson_one_html.find("FLW_SCORM_CONFIG")
            assert "SCO" not in visible_text(lesson_one_html).upper()
            nav_runtime = lesson_one_html.split('<script id="flw-unit-navigator-script">', 1)[1].split("</script>", 1)[0]
            nav_runtime_path = Path(tmp) / "flw_navigator_runtime.js"
            nav_runtime_path.write_text(nav_runtime, encoding="utf-8")
            results["s2bNavigatorRuntimeJs"] = node_check(nav_runtime_path)

        renamed_lessons = [dict(item) for item in seven_lessons]
        renamed_lessons[1]["title"] = "Discussing the weather"
        write_s2_unit_index(s2_unit, lessons=renamed_lessons, title="S2 Stable Unit")
        s2_renamed = server.export_scorm(s2_unit, {**s2_options, "exportDir": str(Path(tmp) / "s2_exports_renamed")})
        assert {(item["componentId"], item["scoIdentifier"]) for item in s2_renamed["componentMappings"]} == {
            (item["componentId"], item["scoIdentifier"]) for item in s2_first["componentMappings"]
        }
        assert any(item["componentId"] == "REW-U023-L02" and "Discussing the weather" in item["title"] for item in s2_renamed["componentMappings"])

        reordered_lessons = [renamed_lessons[0], renamed_lessons[2], renamed_lessons[1], *renamed_lessons[3:]]
        write_s2_unit_index(s2_unit, lessons=reordered_lessons, title="S2 Stable Unit")
        s2_reordered = server.export_scorm(s2_unit, {**s2_options, "exportDir": str(Path(tmp) / "s2_exports_reordered")})
        assert {(item["componentId"], item["scoIdentifier"]) for item in s2_reordered["componentMappings"]} == {
            (item["componentId"], item["scoIdentifier"]) for item in s2_first["componentMappings"]
        }
        reordered_order = [item["componentId"] for item in s2_reordered["componentMappings"] if item["kind"] == "lesson"]
        assert reordered_order[:3] == ["REW-U023-L01", "REW-U023-L03", "REW-U023-L02"]

        changed_lessons = [dict(item) for item in reordered_lessons]
        changed_lessons[1] = {**changed_lessons[1], "questions": [{"id": "q3new002"}, {"id": "q3new001"}]}
        write_s2_unit_index(s2_unit, lessons=changed_lessons, title="S2 Stable Unit", extra_text="content revision")
        s2_changed = server.export_scorm(s2_unit, {**s2_options, "exportDir": str(Path(tmp) / "s2_exports_changed")})
        assert s2_changed["scormManifestIdentifier"] == s2_first["scormManifestIdentifier"]
        assert {(item["componentId"], item["scoIdentifier"]) for item in s2_changed["componentMappings"]} == {
            (item["componentId"], item["scoIdentifier"]) for item in s2_first["componentMappings"]
        }
        assert s2_changed["packageContentSha256"] != s2_first["packageContentSha256"]
        assert not any(item["trackAsSeparateSco"] for item in s2_changed["microActivityMappings"])

        generic_project_unit = Path(tmp) / "S2SmartCourses" / "06-Japanese" / "JW3_U023_A2_model"
        generic_project_unit.mkdir(parents=True)
        (generic_project_unit / "index.html").write_text(
            '<!doctype html><html><head><title>Project Unit</title></head><body>'
            '<h1>Japanese World</h1><section id="start"><h2>Start</h2></section>'
            '<section id="project"><h2>Project</h2><p>Make a project.</p></section>'
            '<section id="result"><h2>Result</h2></section></body></html>',
            encoding="utf-8",
        )
        generic_project_export = server.export_scorm(
            generic_project_unit,
            {"root": str(generic_project_unit.parent), "launchFile": "index.html", "exportDir": str(Path(tmp) / "s2_project_exports")},
        )
        assert any(item["componentId"] == "JPW-U023-PROJECT" for item in generic_project_export["componentMappings"])
        assert any(item["componentId"] == "JPW-U023-RESULT" for item in generic_project_export["componentMappings"])
        with zipfile.ZipFile(s2_first["zipPath"]) as package:
            manifest = package.read("imsmanifest.xml").decode("utf-8")
            assert 'identifier="FLW_REW_U023_L03"' in manifest
            assert 'identifier="FLW_REW_U023_SCORM12"' in manifest
        results["s2ScormIdentity"] = "PASS"

        copied_folder = server.copy_unit_package(root, unit, "002", "Unit 2 New", "folder")
        assert copied_folder["outputType"] == "folder"
        assert (Path(copied_folder["path"]) / "index.html").exists()
        results["copyFolder"] = "PASS"

        zip_source = root / "Adventure_world_unit_003.zip"
        with zipfile.ZipFile(zip_source, "w") as package:
            package.writestr(
                "Adventure_world_unit_003/index.html",
                '<html><head><title>Unit 3</title></head><body><h1>Unit 3</h1><script>window.UNIT_DATA={"unit":3,"title":"Unit 3","lessons":[{"id":"l1","title":"One"}]};</script></body></html>',
            )
        extracted = server.extract_unit_archive(root, zip_source)
        copied_zip = server.copy_unit_package(root, extracted, "004", "Unit 4 Zip", "zip")
        assert copied_zip["outputType"] == "zip" and copied_zip["zipTest"] == "PASS"
        results["copyZip"] = "PASS"

        edits = server.normalized_visual_edits(
            [
                {"selector": "a.lesson", "action": "setLink", "href": "lesson-2.html"},
                {
                    "selector": "section.hero",
                    "action": "setCustomStyle",
                    "custom": {"background": "#fff", "borderColor": "#123456", "padding": "20px", "radius": "18px", "shadow": True},
                },
            ]
        )
        assert [edit["action"] for edit in edits] == ["setLink", "setCustomStyle"]
        runtime = server.visual_runtime_block(edits).split("<script>", 1)[1].split("</script>", 1)[0]
        runtime_path = Path(tmp) / "visual_runtime.js"
        runtime_path.write_text(runtime, encoding="utf-8")
        results["visualRuntimeJs"] = node_check(runtime_path)

    results["frontendJs"] = node_check(APP_DIR / "static" / "app.js")
    index_html = (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (APP_DIR / "static" / "app.js").read_text(encoding="utf-8")
    style_css = (APP_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "Export / FLW Import" in index_html
    assert 'id="exportToFlwBtn"' in index_html
    assert 'id="moodleUrl"' in index_html
    assert 'id="moodlePhpPath"' in index_html
    assert 'id="moodleConfigPath"' in index_html
    assert 'id="moodleTargetSummary"' in index_html
    assert 'id="flwImportMode"' in index_html
    assert 'id="previewFlwImportBtn"' in index_html
    assert "Add New Unit" in index_html
    assert "Moodle Destination" in index_html
    assert 'id="batchFlwImportMode"' in index_html
    assert 'id="batchProductionScope"' in index_html
    assert 'id="batchWorldScope"' in index_html
    assert 'id="batchSpecificWorld"' in index_html
    assert ".export-grid.active" in style_css
    assert "overscroll-behavior: contain" in style_css
    assert "scrollbar-gutter: stable" in style_css
    assert "Current production: 7 worlds" in index_html
    assert 'id="batchImportToFlwBtn"' in index_html
    assert 'id="importCompletedDryRunBtn"' in index_html
    assert 'id="previewBatchCoursesBtn"' in index_html
    assert 'id="cancelBatchJobBtn"' in index_html
    assert 'id="resumeBatchJobBtn"' in index_html
    assert "Clear and Add" not in index_html
    assert "Rebuild Selected FLW Scope" in index_html
    assert 'value="clear_add"' in index_html
    assert "/api/export-scorm-to-flw" in app_js
    assert "previewSingleFlwDestination" in app_js
    assert "previewStateHash" in app_js
    assert "Moodle Destination" in app_js
    assert "use Copy Unit first" in app_js
    assert "/api/batch-export-scorm-to-flw" in app_js
    assert "/api/batch-preview-flw-courses" in app_js
    assert "/api/cancel-batch-job" in app_js
    assert "/api/resume-batch-job" in app_js
    assert "/api/promotable-batch-dry-run" in app_js
    assert "reusableCompletedDryRunJobId" in app_js
    assert "importCompletedDryRunPackages" in app_js
    assert "reuseCompletedDryRunExports" in app_js
    assert "setExportResultPanel" in app_js
    assert "renderMoodleTargetSummaryFromSingle" in app_js
    assert "batchFlwImportMode" in app_js
    assert "batchProductionScope" in app_js
    assert "batchWorldScope" in app_js
    assert "batchSpecificWorld" in app_js
    assert "The Course Editor server is not reachable" in app_js
    assert "seven_world_production" in app_js
    assert "clear_add" in app_js
    assert "PREVIEW_REQUIRED" in app_js
    assert "Preview Moodle Course / Unit-Section Mapping" in index_html
    php_importer = (APP_DIR / "scripts" / "import_scorm_pilot_to_moodle.php").read_text(encoding="utf-8")
    assert "['planned', 'exported']" in php_importer
    assert "$data->skipview = SCORM_SKIPVIEW_ALWAYS;" in php_importer
    assert "$data->hidetoc = SCORM_TOC_DISABLED;" in php_importer
    assert "$data->nav = SCORM_NAV_DISABLED;" in php_importer
    assert "$data->displayattemptstatus = SCORM_DISPLAY_ATTEMPTSTATUS_NO;" in php_importer
    assert "function s6_add_new_unit_already_exists_result" in php_importer
    assert "UNIT_ALREADY_EXISTS" in php_importer
    assert "function s6_preview_state_hash" in php_importer
    assert "function s7_is_batch_mapping_preview" in php_importer
    assert "function s8_decorate_rebuild_result" in php_importer
    assert "function s8_rebuild_summary_counts" in php_importer
    assert "SAFE_SCOPED_REBUILD" in php_importer
    assert "REBUILD_WITH_SUPERSESSION" in php_importer
    assert "BLOCKED_STAGE_CONFLICT" in php_importer
    assert "--expect-preview-state" in php_importer
    import_by_language_body = php_importer.split("function import_by_language", 1)[1].split("function preview_course_map", 1)[0]
    assert "clear_course_for_overwrite(" not in import_by_language_body
    assert "clear_courses_above_id(" not in import_by_language_body
    assert "reset_course_id_sequence(" not in import_by_language_body
    assert "delete_course(" not in import_by_language_body
    assert "course_delete_module(" not in import_by_language_body
    assert "s6_is_single_direct_import" in import_by_language_body
    server_py = (APP_DIR / "server.py").read_text(encoding="utf-8")
    assert "SINGLE_IMPORT_LOCKS" in server_py
    assert "IMPORT_ALREADY_RUNNING" in server_py
    assert "acquire_s7_batch_import_locks" in server_py
    assert "S7_EXPECTED_WORLD_UNIT_COUNTS" in server_py
    assert "S7B_PRODUCTION_WORLD_CODES" in server_py
    assert "S7B_PRODUCTION_EXPECTED_UNIT_COUNTS" in server_py
    assert "S8_SAFE_REBUILD_MODE" in server_py
    assert "PREVIEW_REQUIRED" in server_py
    assert "/api/promotable-batch-dry-run" in server_py
    assert "find_promotable_completed_dry_run_job" in server_py
    assert "stdoutLogPath" in server_py
    assert "EDITOR_BACKEND_PROCESS_ENDED" in server_py
    assert "reuseInterruptedExports" in server_py
    assert "daemon=False" in server_py
    assert "SCORM_EXPORT_IDENTITY_MISMATCH" in server_py
    assert "scorm_export_identity_mismatches" in server_py
    batch_job_import_body = server_py.split("def run_flw_import_for_job", 1)[1].split("def run_batch_job", 1)[0]
    assert "stdout=subprocess.PIPE" not in batch_job_import_body
    assert "--expect-preview-state" in batch_job_import_body
    assert "singleImportRequest" in server_py
    assert "moodleUrl" in app_js
    assert "Resume interrupted import" in app_js
    launcher_ps1 = (APP_DIR / "Start Course Editor.ps1").read_text(encoding="utf-8")
    launcher_bat = (APP_DIR / "Start Course Editor.bat").read_text(encoding="utf-8")
    assert "Start-Process" in launcher_ps1
    assert "-WindowStyle Hidden" in launcher_ps1
    assert '"-u"' in launcher_ps1
    assert "Python311" in launcher_ps1
    assert "OwningProcess" in launcher_ps1
    assert "/api/config" in launcher_ps1
    assert "server-stdout.log" in launcher_ps1
    assert "Start Course Editor.ps1" in launcher_bat
    results["directFlwUi"] = "PASS"
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
