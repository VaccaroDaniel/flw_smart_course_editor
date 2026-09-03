from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import server  # noqa: E402


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def compact_key(value: str) -> str:
    return re.sub(r"\W+", "", (value or "").casefold(), flags=re.UNICODE)


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rendered_page(page, path: Path) -> list[str]:
    errors: list[str] = []

    def on_page_error(exc):
        errors.append(str(exc))

    page.on("pageerror", on_page_error)
    page.goto(file_url(path), wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1400)
    return errors


def visible_text_for_selectors(page, selectors: list[str], *, open_details: bool = True) -> str:
    return norm_text(
        page.evaluate(
            """
            ({selectors, openDetails}) => {
              const out = [];
              for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                  if (openDetails) {
                    if (el.tagName && el.tagName.toLowerCase() === 'details') el.open = true;
                    el.querySelectorAll && el.querySelectorAll('details').forEach(d => d.open = true);
                    const parent = el.closest && el.closest('details');
                    if (parent) parent.open = true;
                  }
                  const cs = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  if (cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                    out.push(el.innerText || el.textContent || '');
                  }
                }
              }
              return out.join('\\n');
            }
            """,
            {"selectors": selectors, "openDetails": open_details},
        )
    )


def selector_visibility(page, selectors: list[str]) -> list[dict[str, Any]]:
    return page.evaluate(
        """
        selectors => {
          const rows = [];
          for (const selector of selectors) {
            const matches = Array.from(document.querySelectorAll(selector));
            rows.push({
              selector,
              count: matches.length,
              visibleCount: matches.filter(el => {
                const cs = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              }).length,
              textLength: matches.map(el => (el.innerText || el.textContent || '').trim()).join(' ').length
            });
          }
          return rows;
        }
        """,
        selectors,
    )


def media_status(page) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const mediaSrc = el => el.currentSrc || el.src || el.getAttribute('src') || '';
          const isVisible = el => {
            const rect = el.getBoundingClientRect();
            const cs = window.getComputedStyle(el);
            return cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
          };
          const imageRows = Array.from(document.images).map(img => ({
            tag: 'img',
            src: mediaSrc(img),
            attr: img.getAttribute('src') || '',
            alt: img.getAttribute('alt') || '',
            complete: img.complete,
            naturalWidth: img.naturalWidth || 0,
            naturalHeight: img.naturalHeight || 0,
            visible: isVisible(img)
          })).filter(row => row.attr && !row.attr.startsWith('data:'));
          const avRows = Array.from(document.querySelectorAll('audio, video, audio source, video source')).map(el => ({
            tag: el.tagName.toLowerCase(),
            src: mediaSrc(el),
            attr: el.getAttribute('src') || ''
          })).filter(row => row.attr && !row.attr.startsWith('data:') && row.attr !== '#');
          return {
            images: imageRows,
            brokenImages: imageRows.filter(row => row.visible && (row.naturalWidth <= 0 || row.naturalHeight <= 0)),
            media: avRows
          };
        }
        """
    )


def local_media_missing(root: Path, html_path: Path, media: dict[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    base_dir = html_path.parent
    base_tag = ""
    try:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        tag = soup.find("base")
        if tag and tag.get("href"):
            base_tag = str(tag.get("href"))
    except Exception:
        base_tag = ""
    if base_tag and not re.match(r"^[a-z][a-z0-9+.-]*:", base_tag, flags=re.I):
        base_dir = (base_dir / base_tag).resolve()
    for row in media.get("media") or []:
        attr = str(row.get("attr") or "").strip()
        if not attr or attr.startswith(("data:", "http://", "https://", "blob:", "javascript:")):
            continue
        candidate = (base_dir / attr.split("#", 1)[0].split("?", 1)[0]).resolve()
        if not candidate.exists():
            missing.append({"tag": str(row.get("tag") or ""), "src": attr, "resolved": str(candidate)})
    return missing


def source_html_for_item(item: dict[str, Any]) -> str:
    unit_path = Path(item["unitPath"])
    launch = item.get("export", {}).get("launchFile") or "index.html"
    return (unit_path / launch).read_text(encoding="utf-8", errors="ignore")


def structured_sections(unit_path: Path, item: dict[str, Any]) -> list[dict[str, Any]]:
    lessons = server.unit_lessons(unit_path)
    sections: list[dict[str, Any]] = []
    launch_files = list(item.get("export", {}).get("sectionLaunchFiles") or [])
    cursor = 0

    source_html = (unit_path / "index.html").read_text(encoding="utf-8", errors="ignore")
    unit_data = server.extract_json_object(source_html, "window.UNIT_DATA=")
    fixed = server.unit_fixed_sections(unit_data)
    opening = [section for section in fixed if section["section"] == "words"]
    closing = [section for section in fixed if section["section"] != "words"]

    def add_fixed(section: dict[str, Any]) -> None:
        nonlocal cursor
        launch = launch_files[cursor] if cursor < len(launch_files) else ""
        cursor += 1
        section_id = {"words": "words", "watch": "watch", "progress": "progress"}.get(section["section"], section["id"])
        sections.append(
            {
                "id": section_id,
                "title": section["title"],
                "kind": section["section"],
                "sourceTargets": [server.css_id(section_id)],
                "launchTargets": [server.css_id(section_id)],
                "topSelectors": [".hero"],
                "launchFile": launch,
            }
        )

    for section in opening:
        add_fixed(section)

    for lesson in lessons:
        launch = launch_files[cursor] if cursor < len(launch_files) else ""
        cursor += 1
        sections.append(
            {
                "id": lesson["id"],
                "title": f"Lesson {lesson['number']}: {lesson['title']}",
                "kind": "lesson",
                "sourceTargets": [f"#lesson-root > details.lesson:nth-of-type({lesson['number']})"],
                "launchTargets": ["#lesson-root > details.lesson"],
                "topSelectors": [".hero"],
                "launchFile": launch,
            }
        )

    for section in closing:
        add_fixed(section)

    return sections


def generic_sections(item: dict[str, Any]) -> list[dict[str, Any]]:
    source_html = source_html_for_item(item)
    launch_files = list(item.get("export", {}).get("sectionLaunchFiles") or [])
    sections: list[dict[str, Any]] = []
    for idx, section in enumerate(server.generic_sco_sections(source_html)):
        show = list(section.get("showSelectors") or [server.css_id(section["id"])])
        top = list(section.get("topSelectors") or [])
        current_targets = list(section.get("openSelectors") or [])
        if not current_targets:
            current_targets = [selector for selector in show if selector not in top] or [server.css_id(section["id"])]
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "kind": section.get("kind") or "section",
                "sourceTargets": current_targets,
                "launchTargets": current_targets,
                "topSelectors": top,
                "showSelectors": show,
                "hideSelectors": list(section.get("hideSelectors") or []),
                "launchFile": launch_files[idx] if idx < len(launch_files) else "",
            }
        )
    return sections


def sections_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    unit_path = Path(item["unitPath"])
    source_html = source_html_for_item(item)
    if server.find_json_object_span(source_html, "window.UNIT_DATA="):
        return structured_sections(unit_path, item)
    return generic_sections(item)


def representative_snippets(text: str, limit: int = 6) -> list[str]:
    pieces = []
    for raw in re.split(r"(?<=[.!?。！？])\s+|\n+| {2,}", norm_text(text)):
        piece = norm_text(raw)
        if len(piece) < 18:
            continue
        if len(piece) > 130:
            piece = piece[:130].rsplit(" ", 1)[0] or piece[:130]
        key = compact_key(piece)
        if len(key) < 12:
            continue
        if key not in {compact_key(p) for p in pieces}:
            pieces.append(piece)
        if len(pieces) >= limit:
            break
    return pieces


def compare_item(pw, item: dict[str, Any], tmp_root: Path) -> dict[str, Any]:
    label = item.get("label") or item.get("code") or "unit"
    source_root = Path(item["unitPath"])
    source_index = source_root / (item.get("export", {}).get("launchFile") or "index.html")
    zip_path = Path(item["export"]["zipPath"])
    extract_root = tmp_root / re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_root)

    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1400})
    source_page = context.new_page()
    source_errors = rendered_page(source_page, source_index)
    source_page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")

    sections = sections_for_item(item)
    section_results: list[dict[str, Any]] = []
    all_target_selectors = []
    for section in sections:
        all_target_selectors.extend(section["launchTargets"])
    all_target_selectors = list(dict.fromkeys(all_target_selectors))

    source_media = media_status(source_page)
    source_missing_media = local_media_missing(source_root, source_index, source_media)

    for section in sections:
        launch_file = section.get("launchFile") or ""
        launch_path = extract_root / launch_file
        row: dict[str, Any] = {
            "id": section["id"],
            "title": section["title"],
            "kind": section["kind"],
            "launchFile": launch_file,
            "ok": True,
            "issues": [],
        }
        if not launch_file or not launch_path.exists():
            row["ok"] = False
            row["issues"].append("Launch file is missing from exported package.")
            section_results.append(row)
            continue

        launch_page = context.new_page()
        launch_errors = rendered_page(launch_page, launch_path)
        launch_page.evaluate("document.querySelectorAll('details').forEach(d => { if (getComputedStyle(d).display !== 'none') d.open = true; })")

        source_text = visible_text_for_selectors(source_page, section["sourceTargets"])
        launch_text = visible_text_for_selectors(launch_page, section["launchTargets"])
        full_launch_text = norm_text(launch_page.inner_text("body"))
        source_snippets = representative_snippets(source_text)
        matched_snippets = [snippet for snippet in source_snippets if compact_key(snippet) in compact_key(full_launch_text)]

        if len(source_text) < 24:
            row["ok"] = False
            row["issues"].append("Source target selector produced too little text; selector may be wrong.")
        if len(launch_text) < 24:
            row["ok"] = False
            row["issues"].append("Imported SCO target displays too little text.")
        if source_snippets and not matched_snippets:
            row["ok"] = False
            row["issues"].append("No representative source text snippet appears in the SCO display.")

        top = list(section.get("topSelectors") or [])
        if top:
            top_visibility = selector_visibility(launch_page, top)
            missing_top = [v for v in top_visibility if v["count"] == 0 or v["visibleCount"] == 0 or v["textLength"] < 10]
            if missing_top:
                row["ok"] = False
                row["issues"].append("Top/hero selector is missing or hidden in the SCO.")
            row["topVisibility"] = top_visibility

        other_selectors = [selector for selector in all_target_selectors if selector not in set(section["launchTargets"])]
        other_visibility = selector_visibility(launch_page, other_selectors)
        visible_others = [
            v for v in other_visibility
            if v["visibleCount"] > 0 and v["textLength"] > 40
        ]
        if visible_others:
            row["ok"] = False
            row["issues"].append("Other lesson/section targets are visible in this SCO.")
        row["visibleOtherTargets"] = visible_others[:8]

        launch_media = media_status(launch_page)
        broken_images = [m for m in launch_media.get("brokenImages") or [] if m.get("attr")]
        missing_media = local_media_missing(extract_root, launch_path, launch_media)
        if broken_images:
            row["ok"] = False
            row["issues"].append(f"{len(broken_images)} image(s) failed to load in this SCO.")
        if missing_media:
            row["ok"] = False
            row["issues"].append(f"{len(missing_media)} audio/video source file(s) are missing in this SCO.")

        row.update(
            {
                "sourceTextLength": len(source_text),
                "launchTextLength": len(launch_text),
                "sourceSnippets": source_snippets[:3],
                "matchedSnippetCount": len(matched_snippets),
                "pageErrors": launch_errors[:5],
                "brokenImages": broken_images[:8],
                "missingMedia": missing_media[:8],
            }
        )
        if launch_errors:
            row["ok"] = False
            row["issues"].append("JavaScript page error occurred while rendering the SCO.")
        section_results.append(row)
        launch_page.close()

    source_page.close()
    context.close()
    browser.close()

    return {
        "label": label,
        "code": item.get("code"),
        "unitPath": str(source_root),
        "zipPath": str(zip_path),
        "expectedScoCount": len(sections),
        "manifestScoCount": item.get("export", {}).get("scoCount"),
        "ok": all(row["ok"] for row in section_results) and not source_errors and not source_missing_media,
        "sourcePageErrors": source_errors[:8],
        "sourceMissingMedia": source_missing_media[:8],
        "sections": section_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render-compare source FLW unit packages and generated SCORM SCO launch pages.")
    parser.add_argument("--manifest", required=True, help="pilot_manifest.json path")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = read_manifest(manifest_path)
    report: dict[str, Any] = {
        "kind": "smartcourses_scorm_display_consistency",
        "manifestPath": str(manifest_path),
        "items": [],
    }
    with tempfile.TemporaryDirectory(prefix="flw_scorm_display_") as tmp:
        tmp_root = Path(tmp)
        with sync_playwright() as pw:
            for item in manifest.get("items") or []:
                if item.get("status") != "exported":
                    continue
                result = compare_item(pw, item, tmp_root)
                report["items"].append(result)

    report["summary"] = {
        "items": len(report["items"]),
        "passed": sum(1 for item in report["items"] if item["ok"]),
        "failed": sum(1 for item in report["items"] if not item["ok"]),
        "sections": sum(len(item["sections"]) for item in report["items"]),
        "failedSections": sum(1 for item in report["items"] for section in item["sections"] if not section["ok"]),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"[report] {output}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for item in report["items"]:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"[{status}] {item['label']} sections={len(item['sections'])}")
        for section in item["sections"]:
            if not section["ok"]:
                print(f"  - {section['launchFile']}: {'; '.join(section['issues'])}")
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
