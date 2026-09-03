from __future__ import annotations

import argparse
import base64
import copy
import csv
import datetime as dt
import hashlib
import html
import json
import mimetypes
import os
import posixpath
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
import xml.etree.ElementTree as ET

from moodle_import_support import BATCH_TERMINAL_STATUSES, FLW_LANGUAGE_ROOTS
from scorm_gui_support import configure_logger, fmt_bytes


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
LOGGER, LOG_FILE = configure_logger(APP_DIR)
DEFAULT_ROOT = Path(r"D:\WinPro.Delta\Projects\SmartCourses\01-Adventure")
DEFAULT_MOODLE_URL = os.environ.get("FLW_MOODLE_URL", "https://192.168.129.79")
MOODLE_PHP_EXE = Path(os.environ.get("FLW_MOODLE_PHP", r"D:\Dev\MoodleWindowsInstaller-latest-501\server\php\php.exe"))
MOODLE_CONFIG_PATH = Path(os.environ.get("FLW_MOODLE_CONFIG", r"D:\Dev\MoodleWindowsInstaller-latest-501\server\moodle\public\config.php"))
MOODLE_IMPORT_SCRIPT = APP_DIR / "scripts" / "import_scorm_pilot_to_moodle.php"
FLW_COURSE_MAP_PATH = APP_DIR / "flw_moodle_course_map.json"
UNPACKED_ZIP_DIR = ".scorm_gui_unpacked"
SETTINGS_FILE = "settings.json"
PREVIEW_ROOTS: dict[str, Path] = {}
BATCH_JOBS: dict[str, dict] = {}
BATCH_JOBS_LOCK = threading.Lock()
BATCH_JOBS_DIR = APP_DIR / "batch_jobs"
BATCH_JOB_PRIVATE_KEYS = {"thread", "process"}
SINGLE_IMPORT_LOCKS: dict[str, threading.Lock] = {}
SINGLE_IMPORT_LOCKS_LOCK = threading.Lock()
FLW_SINGLE_IMPORT_MODES = {"overwrite", "add_new"}
FLW_BATCH_IMPORT_MODES = {"overwrite", "add_new", "clear_add"}
S8_SAFE_REBUILD_MODE = "clear_add"
S7_EXPECTED_WORLD_UNIT_COUNTS = {
    "01-adventure": 72,
    "02-real": 108,
    "03-russian": 120,
    "04-chinese": 132,
    "05-german": 72,
    "06-japanese": 60,
    "07-spanish": 48,
    "08-french": 48,
}
S7B_SEVEN_WORLD_PRODUCTION_SCOPE = "seven_world_production"
S7B_PRODUCTION_WORLD_CODES = {
    "01-adventure",
    "02-real",
    "03-russian",
    "04-chinese",
    "05-german",
    "06-japanese",
    "08-french",
}
S7B_PRODUCTION_EXPECTED_UNIT_COUNTS = {
    **{code: count for code, count in S7_EXPECTED_WORLD_UNIT_COUNTS.items() if code in S7B_PRODUCTION_WORLD_CODES},
    "05-german": 60,
}
S7_STAGE_ORDER = {
    "PREA1": 0,
    "PRE-A1": 0,
    "A1": 10,
    "A2": 20,
    "B1": 30,
    "B2": 40,
    "C1": 50,
    "C2": 60,
}
SCORM_STRUCTURE_VERSION = 2
PREFLIGHT_RESOLVED = "RESOLVED"
PREFLIGHT_STAGE_UNRESOLVED = "STAGE_UNRESOLVED"
PREFLIGHT_STAGE_CONFLICT = "STAGE_CONFLICT"
PREFLIGHT_WORLD_UNRESOLVED = "WORLD_UNRESOLVED"
PREFLIGHT_INVALID_CONFIG = "INVALID_CONFIG"
PREFLIGHT_SOURCE_ROOT_NOT_FOUND = "SOURCE_ROOT_NOT_FOUND"
BLOCKING_PREFLIGHT_STATUSES = {
    PREFLIGHT_STAGE_UNRESOLVED,
    PREFLIGHT_STAGE_CONFLICT,
    PREFLIGHT_WORLD_UNRESOLVED,
    PREFLIGHT_INVALID_CONFIG,
    PREFLIGHT_SOURCE_ROOT_NOT_FOUND,
}
MAX_TEXT_BYTES = 5_000_000
MAX_IMPORT_BYTES = 250_000_000
VISUAL_EDIT_START = "<!-- FLW_VISUAL_EDITS_START -->"
VISUAL_EDIT_END = "<!-- FLW_VISUAL_EDITS_END -->"
BLOCK_STYLE_CSS = ".flw-style-card{background:#fff!important;border:1px solid #d8e3ec!important;border-radius:18px!important;box-shadow:0 16px 34px rgba(32,54,74,.14)!important;padding:18px!important}.flw-style-highlight{background:linear-gradient(135deg,#fff7cf,#fffdf2)!important;border:1px solid #f0ce68!important;border-radius:16px!important;padding:16px!important;box-shadow:0 10px 24px rgba(169,109,36,.12)!important}.flw-style-note{background:#eef7ff!important;border-left:7px solid #2f7db7!important;border-radius:14px!important;padding:16px!important}.flw-style-tip{background:#edf9f1!important;border-left:7px solid #35a66b!important;border-radius:14px!important;padding:16px!important}.flw-style-warning{background:#fff1ef!important;border-left:7px solid #d1534a!important;border-radius:14px!important;padding:16px!important}.flw-style-quote{background:#f7f5ff!important;border-left:7px solid #7765cf!important;border-radius:14px!important;padding:16px 18px!important;font-style:italic!important}.flw-style-hero{background:linear-gradient(135deg,#255f92,#38a2c7)!important;color:#fff!important;border-radius:22px!important;padding:24px!important;box-shadow:0 18px 40px rgba(37,95,146,.22)!important}.flw-style-soft{background:#f5f8fb!important;border:1px solid #d9e3eb!important;border-radius:14px!important;padding:14px!important}.flw-style-custom{background:var(--flw-custom-bg,inherit)!important;border-color:var(--flw-custom-border,currentColor)!important;border-style:solid!important;border-width:var(--flw-custom-border-width,1px)!important;border-radius:var(--flw-custom-radius,12px)!important;padding:var(--flw-custom-padding,14px)!important;box-shadow:var(--flw-custom-shadow,none)!important}"
TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".htm",
    ".js",
    ".json",
    ".md",
    ".txt",
    ".vtt",
    ".xml",
}

COURSE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

SKIP_EXPORT_DIRS = {
    ".git",
    ".scorm_gui_backups",
    ".scorm_staging",
    ".scorm_gui_zip_backups",
    UNPACKED_ZIP_DIR,
    "__pycache__",
    "scorm_exports",
}

REPACK_SKIP_DIRS = {
    ".git",
    ".scorm_gui_backups",
    ".scorm_staging",
    ".scorm_gui_zip_backups",
    UNPACKED_ZIP_DIR,
    "__pycache__",
    "scorm_exports",
}


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    return value


def root_from_value(value: str | None) -> Path:
    raw = value or str(DEFAULT_ROOT)
    path = Path(raw).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def normalize_moodle_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AppError(f"Invalid Moodle URL: {value}")
    normalized = raw.rstrip("/")
    return normalized


def default_moodle_url() -> str:
    saved = load_settings().get("moodleUrl")
    if isinstance(saved, str) and saved.strip():
        try:
            return normalize_moodle_url(saved)
        except AppError:
            pass
    return normalize_moodle_url(DEFAULT_MOODLE_URL)


def path_from_setting(value: str | None, default: Path) -> Path:
    raw = str(value or "").strip()
    path = Path(raw).expanduser() if raw else default
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def default_moodle_php_path() -> Path:
    saved = load_settings().get("moodlePhpPath")
    return path_from_setting(saved if isinstance(saved, str) else None, MOODLE_PHP_EXE)


def default_moodle_config_path() -> Path:
    saved = load_settings().get("moodleConfigPath")
    return path_from_setting(saved if isinstance(saved, str) else None, MOODLE_CONFIG_PATH)


def moodle_target_from_options(options: dict | None = None) -> dict:
    options = options or {}
    moodle_url = normalize_moodle_url(options.get("moodleUrl") or default_moodle_url())
    php_path = path_from_setting(options.get("moodlePhpPath"), default_moodle_php_path())
    config_path = path_from_setting(options.get("moodleConfigPath"), default_moodle_config_path())
    return {
        "moodleUrl": moodle_url,
        "moodlePhpPath": php_path,
        "moodleConfigPath": config_path,
    }


def normalize_flw_import_mode(options: dict | None = None, *, batch: bool = False) -> str:
    options = options or {}
    raw = (
        options.get("batchFlwImportMode")
        if batch and options.get("batchFlwImportMode") is not None
        else options.get("flwImportMode")
    )
    cleaned = str(raw or "overwrite").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "addnew": "add_new",
        "add_new_unit": "add_new",
        "addnewunit": "add_new",
        "add": "add_new",
        "new": "add_new",
        "clearandadd": "clear_add",
        "clear_and_add": "clear_add",
        "clear_add_new": "clear_add",
        "rebuild": "clear_add",
        "rebuild_selected_flw_scope": "clear_add",
        "rebuild_selected_units": "clear_add",
    }
    mode = aliases.get(cleaned, cleaned)
    allowed = FLW_BATCH_IMPORT_MODES if batch else FLW_SINGLE_IMPORT_MODES
    if mode not in allowed:
        label = "batch FLW import" if batch else "FLW import"
        choices = ", ".join(sorted(allowed))
        raise AppError(f"Invalid {label} mode: {raw or ''}. Expected one of: {choices}.")
    return mode


def s8_is_safe_rebuild_mode(import_mode: str | None) -> bool:
    return str(import_mode or "").strip().lower() == S8_SAFE_REBUILD_MODE


def s8_expected_rebuild_preview_hash(options: dict | None = None) -> str:
    options = options or {}
    return str(
        options.get("batchPreviewStateHash")
        or options.get("previewStateHash")
        or options.get("expectedPreviewStateHash")
        or ""
    ).strip()


def primary_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "AdventureScormEditor" / SETTINGS_FILE
    return APP_DIR / f".{SETTINGS_FILE}"


def fallback_settings_path() -> Path:
    return APP_DIR / f".{SETTINGS_FILE}"


def settings_path() -> Path:
    fallback = fallback_settings_path()
    if fallback.exists():
        return fallback
    return primary_settings_path()


def load_settings() -> dict:
    paths = [settings_path()]
    primary = primary_settings_path()
    if primary not in paths:
        paths.append(primary)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def save_settings(settings: dict) -> dict:
    safe = {}
    for key in ("root", "exportDir", "moodleUrl", "moodlePhpPath", "moodleConfigPath"):
        value = settings.get(key)
        if isinstance(value, str) and value.strip():
            if key == "moodleUrl":
                safe[key] = normalize_moodle_url(value)
            elif key in {"moodlePhpPath", "moodleConfigPath"}:
                safe[key] = str(path_from_setting(value, Path(value)))
            else:
                safe[key] = value.strip()
    errors = []
    paths = [settings_path()]
    fallback = fallback_settings_path()
    if fallback not in paths:
        paths.append(fallback)
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")
            return safe
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    raise AppError("Could not save settings. " + " | ".join(errors), 500)
    return safe


def update_saved_paths(
    root: str | Path | None = None,
    export_dir: str | Path | None = None,
    moodle_url: str | None = None,
    moodle_php_path: str | None = None,
    moodle_config_path: str | None = None,
) -> dict:
    settings = load_settings()
    if root:
        root_path = root_from_value(str(root))
        if root_path.exists() and root_path.is_dir():
            root_path = detect_content_root(root_path)
        settings["root"] = str(root_path)
    if export_dir:
        settings["exportDir"] = str(root_from_value(str(export_dir)))
    if moodle_url:
        settings["moodleUrl"] = normalize_moodle_url(moodle_url)
    if moodle_php_path:
        settings["moodlePhpPath"] = str(path_from_setting(moodle_php_path, MOODLE_PHP_EXE))
    if moodle_config_path:
        settings["moodleConfigPath"] = str(path_from_setting(moodle_config_path, MOODLE_CONFIG_PATH))
    return save_settings(settings)


def ensure_root(value: str | None) -> Path:
    root = root_from_value(value) if isinstance(value, str) and value.strip() else default_content_root()
    if not root.exists() or not root.is_dir():
        raise AppError(f"Content root not found: {root}", 404)
    return detect_content_root(root)


def unit_number_from_name(name: str) -> str | None:
    stem = Path(str(name or "")).stem
    match = re.search(r"unit[_\-\s]?(\d{1,3})(?!\d)", stem, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"(?:^|[_\-\s])u(\d{1,3})(?!\d)", stem, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"(\d{3})(?!\d)", stem)
    if not match:
        return None
    return f"{int(match.group(1)):03d}"


def unit_number_from_path(path: Path) -> str:
    number = unit_number_from_name(path.name)
    if number:
        return number
    number = unit_number_from_name(path.parent.name)
    if number:
        return number
    match = re.search(r"(\d{1,3})", path.name)
    return f"{int(match.group(1)):03d}" if match else "000"


def is_unit_dir(path: Path) -> bool:
    return path.is_dir() and bool(unit_number_from_name(path.name)) and (path / "index.html").exists()


def is_unit_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".zip" and bool(unit_number_from_name(path.name))


def archive_cache_dir(root: Path) -> Path:
    return root / UNPACKED_ZIP_DIR


def fallback_archive_cache_dir(root: Path) -> Path:
    root_key = hashlib.sha1(str(root).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return APP_DIR / "unit_cache" / root_key


def has_unit_dirs(root: Path) -> bool:
    try:
        return any(is_unit_dir(child) for child in root.iterdir())
    except OSError:
        return False


def has_unit_archives(root: Path) -> bool:
    try:
        return any(is_unit_archive(child) for child in root.iterdir())
    except OSError:
        return False


def detect_content_root(root: Path) -> Path:
    if has_unit_dirs(root) or has_unit_archives(root):
        return root

    preferred = [root / "Version_2", root / "Version_1"]
    for candidate in preferred:
        if candidate.is_dir() and (has_unit_dirs(candidate) or has_unit_archives(candidate)):
            return candidate.resolve()

    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and (has_unit_dirs(child) or has_unit_archives(child)):
            return child.resolve()
    return root


def default_content_root() -> Path:
    saved = load_settings().get("root")
    if isinstance(saved, str) and saved.strip():
        saved_root = root_from_value(saved)
        if saved_root.exists() and saved_root.is_dir():
            return detect_content_root(saved_root)
    if DEFAULT_ROOT.exists() and DEFAULT_ROOT.is_dir():
        return detect_content_root(DEFAULT_ROOT)
    return DEFAULT_ROOT


def default_export_dir() -> Path:
    saved = load_settings().get("exportDir")
    if isinstance(saved, str) and saved.strip():
        return root_from_value(saved)
    return default_content_root() / "scorm_exports"


def ensure_writable_output_dir(preferred: Path, fallback_parent: Path, purpose: str) -> tuple[Path, str]:
    def probe(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / f".flw_write_test_{uuid.uuid4().hex}.tmp"
        probe_path.write_text("ok", encoding="utf-8")
        try:
            probe_path.unlink()
        except OSError:
            pass

    try:
        probe(preferred)
        return preferred, ""
    except OSError as exc:
        fallback = fallback_parent / preferred.name
        try:
            probe(fallback)
        except OSError as fallback_exc:
            raise AppError(
                f"{purpose} folder is not writable: {preferred}. "
                f"Fallback folder is also not writable: {fallback}. "
                f"Original error: {exc}. Fallback error: {fallback_exc}.",
                500,
            ) from fallback_exc
        return fallback, f"{purpose} folder was not writable: {preferred}. Used fallback folder: {fallback}."


def select_directory(initial_dir: str | None = None, title: str = "Select folder") -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise AppError("The native directory picker is unavailable on this Python installation", 500) from exc

    initial = root_from_value(initial_dir) if initial_dir else default_content_root()
    if not initial.is_dir():
        initial = initial.parent if initial.parent.is_dir() else Path.home()

    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=window,
            title=title,
            initialdir=str(initial),
            mustexist=True,
        )
    finally:
        window.destroy()
    return str(Path(selected).resolve()) if selected else ""


def safe_join(base: Path, rel: str) -> Path:
    if rel is None:
        raise AppError("Missing path")
    normalized = unquote(rel).replace("\\", "/").lstrip("/")
    parts = Path(normalized).parts
    if any(part == ".." for part in parts):
        raise AppError("Path may not contain ..")
    target = (base / normalized).resolve()
    base_resolved = base.resolve()
    if not target.is_relative_to(base_resolved):
        raise AppError("Path escapes the selected unit")
    return target


def find_unit_dir(root: Path, number: str) -> Path | None:
    if not root.exists() or not root.is_dir():
        return None
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if is_unit_dir(child) and unit_number_from_name(child.name) == number:
            return child.resolve()
    return None


def find_unit_archive(root: Path, number: str) -> Path | None:
    if not root.exists() or not root.is_dir():
        return None
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if is_unit_archive(child) and unit_number_from_name(child.name) == number:
            return child.resolve()
    return None


def zip_index_member(zip_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(zip_path) as package:
            names = [name.replace("\\", "/") for name in package.namelist()]
    except zipfile.BadZipFile:
        return None
    if "index.html" in names:
        return "index.html"
    candidates = [name for name in names if name.lower().endswith("/index.html")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda value: (value.count("/"), value.lower()))[0]


def extracted_unit_root(extract_root: Path) -> Path | None:
    if (extract_root / "index.html").exists():
        return extract_root
    candidates = sorted(
        [path.parent for path in extract_root.rglob("index.html") if path.is_file()],
        key=lambda path: (len(path.relative_to(extract_root).parts), path.as_posix().lower()),
    )
    return candidates[0] if candidates else None


def validate_zip_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        return normalized
    pure = Path(normalized)
    if pure.is_absolute() or any(part in {"..", ""} for part in pure.parts):
        raise AppError(f"Unsafe path inside ZIP: {name}")
    return normalized


def extract_unit_archive(root: Path, archive: Path) -> Path:
    index_member = zip_index_member(archive)
    if not index_member:
        raise AppError(f"Unit archive has no index.html: {archive.name}")

    target: Path | None = None
    errors: list[str] = []
    for cache in (archive_cache_dir(root), fallback_archive_cache_dir(root)):
        candidate = cache / archive.stem
        existing = extracted_unit_root(candidate) if candidate.exists() else None
        if existing:
            return existing.resolve()
        if candidate.exists():
            quarantine = cache / f"{archive.stem}.invalid_{now_stamp()}_{uuid.uuid4().hex[:8]}"
            try:
                shutil.move(str(candidate), str(quarantine))
            except OSError as exc:
                errors.append(f"{candidate}: {exc}")
                continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            target = candidate
            break
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
            continue
    if target is None:
        raise AppError(
            f"Could not prepare an unpack cache for {archive.name}. " + " | ".join(errors),
            500,
        )

    try:
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                normalized = validate_zip_member_name(info.filename)
                if not normalized or normalized.endswith("/"):
                    continue
                output = (target / normalized).resolve()
                if not output.is_relative_to(target.resolve()):
                    raise AppError(f"Unsafe path inside ZIP: {info.filename}")
                output.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, output.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                ensure_writable(output)
    except Exception:
        existing = extracted_unit_root(target)
        if existing:
            return existing.resolve()
        raise

    extracted = extracted_unit_root(target)
    if not extracted:
        raise AppError(f"Unpacked archive has no index.html: {archive.name}")
    return extracted.resolve()


def selected_unit_archive(root: Path, selected_unit: Path) -> Path | None:
    archive = find_unit_archive(root, unit_number_from_path(selected_unit))
    if not archive:
        return None
    try:
        selected_resolved = selected_unit.resolve()
        cache_resolved = archive_cache_dir(root).resolve()
    except OSError:
        return None
    if selected_resolved.is_relative_to(cache_resolved):
        return archive
    return None


def zip_content_prefix(archive: Path) -> str:
    index_member = zip_index_member(archive) or "index.html"
    return posixpath.dirname(index_member.replace("\\", "/"))


def should_skip_repack_file(path: Path, unit_path: Path) -> bool:
    rel_parts = path.relative_to(unit_path).parts
    if not rel_parts:
        return False
    if any(part in REPACK_SKIP_DIRS for part in rel_parts):
        return True
    if path.suffix.lower() in {".pyc", ".pyo", ".zip"}:
        return True
    return False


def copy_original_zip_entries_outside_prefix(source_zip: Path, target_zip: zipfile.ZipFile, prefix: str) -> int:
    if not prefix:
        return 0
    preserved = 0
    prefix = prefix.strip("/")
    prefix_root = f"{prefix}/"
    with zipfile.ZipFile(source_zip) as original:
        for info in original.infolist():
            normalized = validate_zip_member_name(info.filename)
            if not normalized or normalized == prefix or normalized.startswith(prefix_root):
                continue
            if info.is_dir():
                target_zip.writestr(info, b"")
            else:
                target_zip.writestr(info, original.read(info.filename))
            preserved += 1
    return preserved


def repack_unit_archive(root: Path, selected_unit: Path) -> dict:
    archive = selected_unit_archive(root, selected_unit)
    if not archive:
        raise AppError("This unit was not opened from a source ZIP, so there is no ZIP to update.")
    if not (selected_unit / "index.html").exists():
        raise AppError(f"Cannot save ZIP because selected unit has no index.html: {selected_unit}")

    prefix = zip_content_prefix(archive)
    backup_dir = root / ".scorm_gui_zip_backups" / now_stamp()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / archive.name
    shutil.copy2(archive, backup_path)
    ensure_writable(backup_path)

    temp_zip = archive.with_name(f".{archive.stem}.{uuid.uuid4().hex[:8]}.tmp.zip")
    written = 0
    preserved = 0
    try:
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as package:
            preserved = copy_original_zip_entries_outside_prefix(archive, package, prefix)
            for path in sorted(selected_unit.rglob("*"), key=lambda p: p.relative_to(selected_unit).as_posix().lower()):
                if not path.is_file() or should_skip_repack_file(path, selected_unit):
                    continue
                rel = path.relative_to(selected_unit).as_posix()
                arcname = posixpath.join(prefix, rel) if prefix else rel
                package.write(path, arcname)
                written += 1
        with zipfile.ZipFile(temp_zip) as package:
            bad = package.testzip()
            if bad is not None:
                raise AppError(f"Repacked ZIP failed validation at: {bad}")
        ensure_writable(archive)
        os.replace(temp_zip, archive)
        ensure_writable(archive)
    except Exception:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass
        raise

    return {
        "unit": unit_number_from_path(selected_unit),
        "zipPath": str(archive),
        "backupPath": str(backup_path),
        "selectedPath": str(selected_unit),
        "internalPrefix": prefix,
        "fileCount": written,
        "preservedOutsidePrefix": preserved,
        "zipBytes": archive.stat().st_size,
        "zipTest": "PASS",
    }


def normalize_unit_number(value: str | int | None) -> str:
    match = re.search(r"(\d{1,3})", str(value or ""))
    if not match:
        raise AppError("Target unit number is required")
    number = int(match.group(1))
    if number < 1 or number > 999:
        raise AppError("Target unit number must be between 001 and 999")
    return f"{number:03d}"


def renamed_unit_name(source_name: str, target_number: str) -> str:
    base = Path(str(source_name or "")).stem
    if not base:
        return f"Unit_{target_number}"

    def padded(match: re.Match) -> str:
        width = max(3, len(match.group(2)))
        return f"{match.group(1)}{target_number.zfill(width)}"

    replacements = (
        r"(unit[_\-\s]?)(\d{1,3})(?!\d)",
        r"((?:^|[_\-\s])u)(\d{1,3})(?!\d)",
    )
    for pattern in replacements:
        updated, count = re.subn(pattern, padded, base, count=1, flags=re.IGNORECASE)
        if count:
            return updated

    updated, count = re.subn(r"(\d{3})(?!\d)", target_number, base, count=1)
    if count:
        return updated
    return f"{base}_unit_{target_number}"


def unit_number_exists(root: Path, number: str) -> bool:
    cache = archive_cache_dir(root)
    return bool(find_unit_dir(root, number) or find_unit_archive(root, number) or find_unit_dir(cache, number))


def copy_unit_ignore(_folder: str, names: list[str]) -> set[str]:
    skipped: set[str] = set()
    for name in names:
        if name in REPACK_SKIP_DIRS:
            skipped.add(name)
            continue
        if Path(name).suffix.lower() in {".pyc", ".pyo", ".zip"}:
            skipped.add(name)
    return skipped


def ensure_writable_tree(root: Path) -> None:
    ensure_writable(root)
    for path in root.rglob("*"):
        ensure_writable(path)


def replace_unit_label_numbers(text: str, old_number: str, target_number: str) -> str:
    old_int = str(int(old_number))
    target_int = str(int(target_number))
    replacements = (
        (rf"\bUnit\s+{re.escape(old_number)}\b", f"Unit {target_number}"),
        (rf"\bUnit\s+{re.escape(old_int)}\b", f"Unit {target_int}"),
        (rf"\bU{re.escape(old_number)}\b", f"U{target_number}"),
        (rf"\bU{re.escape(old_int)}\b", f"U{target_int}"),
        (rf"\bunit_{re.escape(old_number)}\b", f"unit_{target_number}"),
        (rf"\bunit-{re.escape(old_number)}\b", f"unit-{target_number}"),
    )
    updated = text
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
    return updated


def update_unit_data_number_fields(data: dict, target_number: str, old_number: str, target_title: str | None = None) -> bool:
    changed = False
    number_int = int(target_number)
    for key in ("unit", "unitNumber", "unitNo", "unit_no", "unitId", "unit_id"):
        if key not in data:
            continue
        previous = data.get(key)
        data[key] = number_int if isinstance(previous, int) and not isinstance(previous, bool) else target_number
        changed = changed or data[key] != previous
    if "unit" not in data:
        data["unit"] = number_int
        changed = True

    for key in ("title", "unitTitle", "name"):
        if isinstance(data.get(key), str):
            previous = data[key]
            data[key] = target_title if target_title and key in {"title", "unitTitle"} else replace_unit_label_numbers(previous, old_number, target_number)
            changed = changed or data[key] != previous
    return changed


def update_copied_index_metadata(unit_path: Path, old_number: str, target_number: str, target_title: str | None = None) -> bool:
    index = unit_path / "index.html"
    if not index.exists():
        return False
    text = read_text(index)
    changed = False
    span = find_json_object_span(text, "window.UNIT_DATA=")
    if span:
        try:
            data = json.loads(text[span[0] : span[1]])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and update_unit_data_number_fields(data, target_number, old_number, target_title):
            compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            text = text[: span[0]] + compact + text[span[1] :]
            changed = True

    def replace_simple_tag(match: re.Match) -> str:
        inner = html.escape(target_title) if target_title else replace_unit_label_numbers(match.group(2), old_number, target_number)
        return f"{match.group(1)}{inner}{match.group(3)}"

    for tag in ("title", "h1"):
        before = text
        text, count = re.subn(
            rf"(<{tag}\b[^>]*>)(.*?)(</{tag}>)",
            replace_simple_tag,
            text,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        changed = changed or (bool(count) and text != before)

    if changed:
        write_text(index, text)
    return changed


def update_copied_manifest_metadata(unit_path: Path, source_name: str, target_name: str, old_number: str, target_number: str) -> bool:
    manifest = unit_path / "imsmanifest.xml"
    if not manifest.exists():
        return False
    text = read_text(manifest)
    updated = text.replace(source_name, target_name)
    updated = replace_unit_label_numbers(updated, old_number, target_number)
    if updated != text:
        write_text(manifest, updated)
        return True
    return False


def write_unit_zip_from_folder(unit_path: Path, zip_path: Path, prefix: str) -> dict:
    if zip_path.exists():
        raise AppError(f"Target ZIP already exists: {zip_path.name}")
    temp_zip = zip_path.with_name(f".{zip_path.stem}.{uuid.uuid4().hex[:8]}.tmp.zip")
    prefix = prefix.strip("/")
    written = 0
    try:
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(unit_path.rglob("*"), key=lambda p: p.relative_to(unit_path).as_posix().lower()):
                if not path.is_file() or should_skip_repack_file(path, unit_path):
                    continue
                rel = path.relative_to(unit_path).as_posix()
                arcname = posixpath.join(prefix, rel) if prefix else rel
                package.write(path, arcname)
                written += 1
        with zipfile.ZipFile(temp_zip) as package:
            bad = package.testzip()
            if bad is not None:
                raise AppError(f"Copied ZIP failed validation at: {bad}")
        os.replace(temp_zip, zip_path)
        ensure_writable(zip_path)
    except Exception:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass
        raise
    return {"fileCount": written, "zipBytes": zip_path.stat().st_size, "zipTest": "PASS"}


def renamed_zip_prefix(prefix: str, source_name: str, target_name: str, target_number: str) -> str:
    prefix = prefix.strip("/")
    if not prefix:
        return ""
    parts = prefix.split("/")
    leaf = parts[-1]
    if unit_number_from_name(leaf):
        parts[-1] = renamed_unit_name(leaf, target_number)
    elif leaf == source_name:
        parts[-1] = target_name
    else:
        parts[-1] = renamed_unit_name(leaf, target_number)
    return "/".join(parts)


def copy_unit_package(root: Path, selected_unit: Path, target_unit: str | int | None, target_title: str | None = None, output_type: str = "auto") -> dict:
    target_number = normalize_unit_number(target_unit)
    old_number = unit_number_from_path(selected_unit)
    output_type = str(output_type or "auto").strip().lower()
    if output_type not in {"auto", "zip", "folder"}:
        raise AppError("Copy output type must be auto, zip, or folder")
    target_title = str(target_title or "").strip() or None
    if target_number == old_number:
        raise AppError("Choose a different target unit number")
    if unit_number_exists(root, target_number):
        raise AppError(f"Unit {target_number} already exists")
    if not (selected_unit / "index.html").exists():
        raise AppError(f"Cannot copy unit because index.html is missing: {selected_unit}")

    archive = selected_unit_archive(root, selected_unit)
    source_name = archive.stem if archive else selected_unit.name
    target_name = renamed_unit_name(source_name, target_number)
    metadata_updated = False
    manifest_updated = False

    if archive:
        prefix = zip_content_prefix(archive)
        target_prefix = renamed_zip_prefix(prefix, source_name, target_name, target_number)
        if output_type in {"auto", "zip"}:
            target_archive = root / f"{target_name}.zip"
            target_cache = archive_cache_dir(root) / target_archive.stem
            target_selected = target_cache / target_prefix if target_prefix else target_cache
            if target_archive.exists():
                raise AppError(f"Target ZIP already exists: {target_archive.name}")
            if target_cache.exists():
                raise AppError(f"Target unpacked cache already exists: {target_cache}")
            try:
                target_selected.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(selected_unit, target_selected, ignore=copy_unit_ignore)
                ensure_writable_tree(target_selected)
                metadata_updated = update_copied_index_metadata(target_selected, old_number, target_number, target_title)
                manifest_updated = update_copied_manifest_metadata(
                    target_selected,
                    prefix or source_name,
                    target_prefix or target_name,
                    old_number,
                    target_number,
                )
                zip_stats = write_unit_zip_from_folder(target_selected, target_archive, target_prefix)
            except Exception:
                if target_cache.exists():
                    try:
                        shutil.rmtree(target_cache)
                    except OSError:
                        pass
                raise
            return {
                "unit": target_number,
                "sourceUnit": old_number,
                "source": "zip",
                "outputType": "zip",
                "sourcePath": str(selected_unit),
                "sourceArchivePath": str(archive),
                "path": str(target_selected),
                "archivePath": str(target_archive),
                "internalPrefix": target_prefix,
                "name": target_name,
                "title": target_title or "",
                "metadataUpdated": metadata_updated,
                "manifestUpdated": manifest_updated,
                **zip_stats,
            }

    if not archive and output_type == "zip":
        target_archive = root / f"{target_name}.zip"
        target_cache = archive_cache_dir(root) / target_archive.stem
        target_selected = target_cache / target_name
        if target_archive.exists():
            raise AppError(f"Target ZIP already exists: {target_archive.name}")
        if target_cache.exists():
            raise AppError(f"Target unpacked cache already exists: {target_cache}")
        try:
            target_selected.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(selected_unit, target_selected, ignore=copy_unit_ignore)
            ensure_writable_tree(target_selected)
            metadata_updated = update_copied_index_metadata(target_selected, old_number, target_number, target_title)
            manifest_updated = update_copied_manifest_metadata(target_selected, source_name, target_name, old_number, target_number)
            zip_stats = write_unit_zip_from_folder(target_selected, target_archive, target_name)
        except Exception:
            if target_cache.exists():
                try:
                    shutil.rmtree(target_cache)
                except OSError:
                    pass
            raise
        return {
            "unit": target_number,
            "sourceUnit": old_number,
            "source": "folder",
            "outputType": "zip",
            "sourcePath": str(selected_unit),
            "sourceArchivePath": "",
            "path": str(target_selected),
            "archivePath": str(target_archive),
            "internalPrefix": target_name,
            "name": target_name,
            "title": target_title or "",
            "metadataUpdated": metadata_updated,
            "manifestUpdated": manifest_updated,
            **zip_stats,
        }

    target_path = root / target_name
    if target_path.exists():
        raise AppError(f"Target folder already exists: {target_path.name}")
    try:
        shutil.copytree(selected_unit, target_path, ignore=copy_unit_ignore)
        ensure_writable_tree(target_path)
        metadata_updated = update_copied_index_metadata(target_path, old_number, target_number, target_title)
        manifest_updated = update_copied_manifest_metadata(target_path, source_name, target_name, old_number, target_number)
    except Exception:
        if target_path.exists():
            try:
                shutil.rmtree(target_path)
            except OSError:
                pass
        raise
    return {
        "unit": target_number,
        "sourceUnit": old_number,
        "source": "zip" if archive else "folder",
        "outputType": "folder",
        "sourcePath": str(selected_unit),
        "sourceArchivePath": str(archive) if archive else "",
        "path": str(target_path),
        "archivePath": "",
        "internalPrefix": "",
        "name": target_name,
        "title": target_title or "",
        "metadataUpdated": metadata_updated,
        "manifestUpdated": manifest_updated,
        "fileCount": scan_unit_counts(target_path)["files"],
        "zipBytes": 0,
        "zipTest": "",
    }


def unit_dir(root: Path, unit: str) -> Path:
    match = re.search(r"(\d{1,3})", str(unit or ""))
    if not match:
        raise AppError("Missing unit number")
    number = f"{int(match.group(1)):03d}"

    direct = find_unit_dir(root, number)
    if direct:
        return direct

    cached = find_unit_dir(archive_cache_dir(root), number)
    if cached:
        return cached

    fallback_cached = find_unit_dir(fallback_archive_cache_dir(root), number)
    if fallback_cached:
        return fallback_cached

    archive = find_unit_archive(root, number)
    if archive:
        return extract_unit_archive(root, archive)

    raise AppError(f"Unit {number} not found under {root}", 404)


def preview_root_for_request(unit: str, explicit_root: str | None) -> Path:
    number = unit_number_from_name(unit) or unit_number_from_path(Path(str(unit)))
    if explicit_root:
        root = ensure_root(explicit_root)
        PREVIEW_ROOTS[number] = root
        return root
    remembered = PREVIEW_ROOTS.get(number)
    if remembered and remembered.exists() and remembered.is_dir():
        return remembered
    root = ensure_root(None)
    PREVIEW_ROOTS[number] = root
    return root


def read_text(path: Path, max_bytes: int = MAX_TEXT_BYTES) -> str:
    size = path.stat().st_size
    if size > max_bytes:
        raise AppError(f"File is too large for the text editor: {size} bytes")
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def ensure_writable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass


def find_json_object_span(text: str, marker: str) -> tuple[int, int] | None:
    start = text.find(marker)
    if start < 0:
        if marker == "window.UNIT_DATA=":
            match = re.search(r"window\s*\.\s*UNIT_DATA\s*=", text)
            if not match:
                return None
            start = match.start()
        else:
            return None
    brace = text.find("{", start)
    if brace < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for pos in range(brace, len(text)):
        char = text[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return brace, pos + 1
    return None


def extract_json_object(text: str, marker: str) -> dict:
    span = find_json_object_span(text, marker)
    if not span:
        return {}
    candidate = text[span[0] : span[1]]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {}


def first_match(pattern: str, text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str:
    match = re.search(pattern, text, flags)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def clean_display_text(value: str) -> str:
    text = str(value or "")
    if "${" in text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n·-–—")
    return text


def extract_embedded_json(text: str, element_id: str) -> dict:
    safe_id = re.escape(element_id)
    match = re.search(
        rf"<script\b(?=[^>]*\bid=['\"]{safe_id}['\"])[^>]*>(.*?)</script>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return {}
    raw = html.unescape(match.group(1)).strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_unit_meta_data(text: str) -> dict:
    return (
        extract_json_object(text, "window.UNIT_DATA=")
        or extract_embedded_json(text, "unit-data")
        or extract_embedded_json(text, "unit-json")
    )


def empty_meta(name: str) -> dict:
    meta = {
        "htmlTitle": "",
        "title": name,
        "stage": "",
        "sourceStage": "",
        "cefr": "",
        "deploymentStage": "",
        "deploymentStageCode": "",
        "worldCode": "",
        "mission": "",
        "course": "",
        "unit": "",
    }
    return meta


def index_meta_from_text(name: str, text: str) -> dict:
    meta = empty_meta(name)
    unit_data = extract_unit_meta_data(text)
    meta["htmlTitle"] = clean_display_text(first_match(r"<title[^>]*>(.*?)</title>", text))
    h1 = clean_display_text(first_match(r"<h1[^>]*>(.*?)</h1>", text))
    meta["title"] = (
        clean_display_text(str(unit_data.get("title") or ""))
        or meta["htmlTitle"]
        or h1
        or name
    )
    meta["stage"] = str(unit_data.get("stage") or unit_data.get("cefr") or "")
    meta["sourceStage"] = str(unit_data.get("stage") or unit_data.get("cefr") or unit_data.get("level") or "")
    meta["cefr"] = str(unit_data.get("cefr") or "")
    meta["deploymentStage"] = str(
        unit_data.get("deploymentStage")
        or unit_data.get("deployment_stage")
        or unit_data.get("moodleDeploymentStage")
        or unit_data.get("moodle_stage")
        or ""
    )
    meta["deploymentStageCode"] = str(
        unit_data.get("deploymentStageCode")
        or unit_data.get("deployment_stage_code")
        or unit_data.get("moodleDeploymentStageCode")
        or ""
    )
    meta["worldCode"] = str(unit_data.get("worldCode") or unit_data.get("world") or "")
    meta["mission"] = clean_display_text(str(unit_data.get("mission") or first_match(r'<p[^>]*class="[^"]*mission[^"]*"[^>]*>(.*?)</p>', text)))
    meta["course"] = clean_display_text(str(unit_data.get("course") or unit_data.get("courseTitle") or ""))
    meta["unit"] = str(unit_data.get("unit") or "")
    return meta


def stage_from_json_sidecar(path: Path) -> tuple[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    for key in ("deploymentStageCode", "deploymentStage", "stage", "sourceStage", "cefr", "level", "band"):
        value = first_text_value(data.get(key))
        if value:
            return value, path.name
    status = data.get("status")
    if isinstance(status, dict):
        for key in ("deploymentStageCode", "deploymentStage", "stage", "sourceStage", "cefr", "level", "band"):
            value = first_text_value(status.get(key))
            if value:
                return value, path.name
    standard = first_text_value(data.get("standard"))
    normalized = normalize_deployment_stage(standard)
    if normalized:
        return standard, path.name
    return "", ""


def stage_from_markdown_sidecar(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "", ""
    patterns = [
        r"(?im)^\s*[-*]?\s*Band\s*:\s*([^\r\n]+)",
        r"(?im)^\s*[-*]?\s*CEFR\s*(?:band)?\s*:\s*([^\r\n]+)",
        r"(?im)^\s*[-*]?\s*Level\s*:\s*([^\r\n]+)",
        r"(?im)^\s*[-*]?\s*Stage\s*:\s*([^\r\n]+)",
        r"(?im)^\s*[-*]?\s*Standard\s*:\s*([^\r\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = clean_display_text(match.group(1))
            if normalize_deployment_stage(value):
                return value, path.name
    return "", ""


def package_sidecar_stage(unit_path: Path) -> tuple[str, str]:
    candidates = [
        unit_path / "CEFR_KP_map.md",
        unit_path / "manifest.json",
        unit_path / "moodle_manifest.json",
        unit_path / "README.md",
        unit_path / "package_integrity.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix.lower() == ".json":
            value, source = stage_from_json_sidecar(path)
        else:
            value, source = stage_from_markdown_sidecar(path)
        if value and normalize_deployment_stage(value):
            return value, source
    return "", ""


def index_meta(unit_path: Path) -> dict:
    index = unit_path / "index.html"
    if not index.exists():
        return empty_meta(unit_path.name)
    meta = index_meta_from_text(unit_path.name, read_text(index))
    sidecar_stage, sidecar_source = package_sidecar_stage(unit_path)
    if sidecar_stage:
        if not meta.get("sourceStage"):
            meta["sourceStage"] = sidecar_stage
        if not meta.get("stage"):
            meta["stage"] = sidecar_stage
        if not meta.get("cefr"):
            normalized = normalize_deployment_stage(sidecar_stage)
            if normalized:
                meta["cefr"] = normalized
        meta["sourceStageSource"] = sidecar_source
    return meta


def zip_sidecar_stage(zip_path: Path, index_member: str) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(zip_path) as package:
            names = set(package.namelist())
            base = posixpath.dirname(index_member)
            candidates = [
                posixpath.join(base, "CEFR_KP_map.md"),
                posixpath.join(base, "manifest.json"),
                posixpath.join(base, "moodle_manifest.json"),
                posixpath.join(base, "README.md"),
                posixpath.join(base, "package_integrity.json"),
            ]
            for member in candidates:
                if member not in names:
                    continue
                raw = package.read(member).decode("utf-8", errors="ignore")
                suffix = Path(member).suffix.lower()
                tmp_value = ""
                if suffix == ".json":
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = {}
                    if isinstance(data, dict):
                        for key in ("deploymentStageCode", "deploymentStage", "stage", "sourceStage", "cefr", "level", "band"):
                            tmp_value = first_text_value(data.get(key))
                            if tmp_value:
                                break
                        status = data.get("status") if not tmp_value else None
                        if isinstance(status, dict):
                            for key in ("deploymentStageCode", "deploymentStage", "stage", "sourceStage", "cefr", "level", "band"):
                                tmp_value = first_text_value(status.get(key))
                                if tmp_value:
                                    break
                        if not tmp_value:
                            standard = first_text_value(data.get("standard"))
                            if normalize_deployment_stage(standard):
                                tmp_value = standard
                else:
                    for pattern in (
                        r"(?im)^\s*[-*]?\s*Band\s*:\s*([^\r\n]+)",
                        r"(?im)^\s*[-*]?\s*CEFR\s*(?:band)?\s*:\s*([^\r\n]+)",
                        r"(?im)^\s*[-*]?\s*Level\s*:\s*([^\r\n]+)",
                        r"(?im)^\s*[-*]?\s*Stage\s*:\s*([^\r\n]+)",
                        r"(?im)^\s*[-*]?\s*Standard\s*:\s*([^\r\n]+)",
                    ):
                        match = re.search(pattern, raw)
                        if match:
                            tmp_value = clean_display_text(match.group(1))
                            break
                if tmp_value and normalize_deployment_stage(tmp_value):
                    return tmp_value, posixpath.basename(member)
    except Exception:
        return "", ""
    return "", ""


def zip_index_meta(zip_path: Path) -> dict:
    index_member = zip_index_member(zip_path)
    if not index_member:
        return empty_meta(zip_path.stem)
    try:
        with zipfile.ZipFile(zip_path) as package:
            data = package.read(index_member)
    except Exception:
        return empty_meta(zip_path.stem)
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    meta = index_meta_from_text(zip_path.stem, text)
    sidecar_stage, sidecar_source = zip_sidecar_stage(zip_path, index_member)
    if sidecar_stage:
        if not meta.get("sourceStage"):
            meta["sourceStage"] = sidecar_stage
        if not meta.get("stage"):
            meta["stage"] = sidecar_stage
        if not meta.get("cefr"):
            normalized = normalize_deployment_stage(sidecar_stage)
            if normalized:
                meta["cefr"] = normalized
        meta["sourceStageSource"] = sidecar_source
    return meta


def scan_unit_counts(unit_path: Path) -> dict:
    counts = {
        "files": 0,
        "bytes": 0,
        "images": 0,
        "audio": 0,
        "video": 0,
        "csv": 0,
        "json": 0,
        "html": 0,
    }
    for path in unit_path.rglob("*"):
        if not path.is_file():
            continue
        counts["files"] += 1
        try:
            counts["bytes"] += path.stat().st_size
        except OSError:
            pass
        ext = path.suffix.lower()
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
            counts["images"] += 1
        elif ext in {".mp3", ".m4a", ".wav", ".ogg"}:
            counts["audio"] += 1
        elif ext in {".mp4", ".webm", ".mov"}:
            counts["video"] += 1
        elif ext == ".csv":
            counts["csv"] += 1
        elif ext == ".json":
            counts["json"] += 1
        elif ext in {".html", ".htm"}:
            counts["html"] += 1
    return counts


def scan_zip_counts(zip_path: Path) -> dict:
    counts = {
        "files": 0,
        "bytes": 0,
        "images": 0,
        "audio": 0,
        "video": 0,
        "csv": 0,
        "json": 0,
        "html": 0,
    }
    try:
        with zipfile.ZipFile(zip_path) as package:
            for info in package.infolist():
                if info.is_dir():
                    continue
                counts["files"] += 1
                counts["bytes"] += info.file_size
                ext = Path(info.filename).suffix.lower()
                if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
                    counts["images"] += 1
                elif ext in {".mp3", ".m4a", ".wav", ".ogg"}:
                    counts["audio"] += 1
                elif ext in {".mp4", ".webm", ".mov"}:
                    counts["video"] += 1
                elif ext == ".csv":
                    counts["csv"] += 1
                elif ext == ".json":
                    counts["json"] += 1
                elif ext in {".html", ".htm"}:
                    counts["html"] += 1
    except Exception:
        pass
    return counts


def list_units(root: Path) -> list[dict]:
    units = []
    seen: set[str] = set()
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not is_unit_dir(child):
            continue
        number = unit_number_from_name(child.name)
        if not number:
            continue
        seen.add(number)
        meta = index_meta(child)
        counts = scan_unit_counts(child)
        units.append(
            {
                "number": number,
                "name": child.name,
                "path": str(child),
                "source": "folder",
                "title": meta.get("title") or child.name,
                "stage": meta.get("stage") or "",
                "mission": meta.get("mission") or "",
                "hasIndex": (child / "index.html").exists(),
                "hasManifest": (child / "imsmanifest.xml").exists(),
                "modified": dt.datetime.fromtimestamp(child.stat().st_mtime).isoformat(timespec="seconds"),
                "counts": counts,
            }
        )

    cache = archive_cache_dir(root)
    for archive in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not is_unit_archive(archive):
            continue
        number = unit_number_from_name(archive.name)
        if not number or number in seen:
            continue
        unpacked = find_unit_dir(cache, number)
        if unpacked:
            meta = index_meta(unpacked)
            counts = scan_unit_counts(unpacked)
            path = str(unpacked)
            has_index = (unpacked / "index.html").exists()
            has_manifest = (unpacked / "imsmanifest.xml").exists()
        else:
            meta = zip_index_meta(archive)
            counts = scan_zip_counts(archive)
            path = str(archive)
            has_index = bool(zip_index_member(archive))
            has_manifest = False
            try:
                with zipfile.ZipFile(archive) as package:
                    has_manifest = any(name.replace("\\", "/").lower().endswith("imsmanifest.xml") for name in package.namelist())
            except Exception:
                pass
        seen.add(number)
        units.append(
            {
                "number": number,
                "name": archive.stem,
                "path": path,
                "archivePath": str(archive),
                "source": "zip",
                "title": meta.get("title") or archive.stem,
                "stage": meta.get("stage") or "",
                "mission": meta.get("mission") or "",
                "hasIndex": has_index,
                "hasManifest": has_manifest,
                "modified": dt.datetime.fromtimestamp(archive.stat().st_mtime).isoformat(timespec="seconds"),
                "counts": counts,
            }
        )
    return sorted(units, key=lambda item: item["number"])


def editable_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS and path.stat().st_size <= MAX_TEXT_BYTES


def file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "image"
    if ext in {".mp3", ".m4a", ".wav", ".ogg"}:
        return "audio"
    if ext in {".mp4", ".webm", ".mov"}:
        return "video"
    if ext == ".csv":
        return "csv"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def list_unit_files(unit_path: Path) -> list[dict]:
    rows = []
    unit_number = unit_number_from_path(unit_path)
    for path in sorted(unit_path.rglob("*"), key=lambda p: p.relative_to(unit_path).as_posix().lower()):
        if not path.is_file():
            continue
        rel = path.relative_to(unit_path).as_posix()
        stat = path.stat()
        rows.append(
            {
                "path": rel,
                "name": path.name,
                "size": stat.st_size,
                "modified": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "kind": file_kind(path),
                "editable": editable_file(path),
                "previewUrl": f"/preview/{unit_number}/{rel}",
            }
        )
    return rows


def asset_folder_for_kind(kind: str, filename: str = "") -> str:
    normalized = str(kind or "").strip().lower()
    ext = Path(filename or "").suffix.lower()
    if normalized == "image" or ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "assets/images"
    if normalized == "audio" or ext in {".mp3", ".m4a", ".wav", ".ogg"}:
        return "assets/audio"
    if normalized == "video" or ext in {".mp4", ".webm", ".mov"}:
        return "assets/video"
    return "assets"


def safe_import_filename(filename: str) -> str:
    name = Path(str(filename or "asset")).name
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "-", Path(name).stem).strip(" .-_") or "asset"
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", Path(name).suffix).lower()
    if len(stem) > 90:
        stem = stem[:90].rstrip(" .-_") or "asset"
    return f"{stem}{suffix}"


def unique_asset_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for index in range(2, 1000):
        next_candidate = folder / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    return folder / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"


def import_unit_asset(unit_path: Path, filename: str, content_base64: str, kind: str = "") -> dict:
    safe_name = safe_import_filename(filename)
    if "," in content_base64 and content_base64.split(",", 1)[0].lower().startswith("data:"):
        content_base64 = content_base64.split(",", 1)[1]
    try:
        content = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise AppError("Imported file data is not valid base64") from exc
    if not content:
        raise AppError("Imported file is empty")
    if len(content) > MAX_IMPORT_BYTES:
        raise AppError(f"Imported file is too large: {fmt_bytes(len(content))}")
    folder_rel = asset_folder_for_kind(kind, safe_name)
    folder = safe_join(unit_path, folder_rel)
    folder.mkdir(parents=True, exist_ok=True)
    target = unique_asset_path(folder, safe_name)
    target.write_bytes(content)
    ensure_writable(target)
    rel = target.relative_to(unit_path).as_posix()
    return {
        "path": rel,
        "name": target.name,
        "kind": file_kind(target),
        "size": len(content),
        "folder": folder_rel,
    }


def list_unit_backups(unit_path: Path) -> list[dict]:
    base = unit_path / ".scorm_gui_backups"
    if not base.exists():
        return []
    rows = []
    for path in sorted(base.rglob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) < 2:
            continue
        stamp = parts[0]
        target_rel = Path(*parts[1:]).as_posix()
        stat = path.stat()
        rows.append(
            {
                "stamp": stamp,
                "path": target_rel,
                "backupPath": path.relative_to(unit_path).as_posix(),
                "size": stat.st_size,
                "modified": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "kind": file_kind(path),
            }
        )
    return rows[:300]


def restore_unit_backup(unit_path: Path, stamp: str, target_rel: str) -> dict:
    stamp = re.sub(r"[^0-9_]", "", str(stamp or ""))
    if not stamp:
        raise AppError("Choose a backup timestamp to restore")
    target_rel = clean_ref(target_rel)
    if not target_rel:
        raise AppError("Choose a backed-up file to restore")
    backup = safe_join(unit_path / ".scorm_gui_backups", f"{stamp}/{target_rel}")
    if not backup.exists() or not backup.is_file():
        raise AppError(f"Backup was not found: {stamp}/{target_rel}", 404)
    target = safe_join(unit_path, target_rel)
    current_backup = backup_file(unit_path, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    ensure_writable(target)
    return {
        "path": target_rel,
        "stamp": stamp,
        "restoredFrom": backup.relative_to(unit_path).as_posix(),
        "currentBackup": current_backup,
        "size": target.stat().st_size,
        "kind": file_kind(target),
    }


class LocalReferenceParser(HTMLParser):
    REF_ATTRS = {"src", "href", "poster", "data-src"}

    def __init__(self):
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key and key.lower() in self.REF_ATTRS and value:
                self.refs.append(value)


def clean_ref(ref: str) -> str:
    value = (ref or "").strip()
    if not value or value.startswith("#"):
        return ""
    low = value.lower()
    if low.startswith(("http:", "https:", "data:", "mailto:", "tel:", "javascript:", "blob:")):
        return ""
    value = value.split("#", 1)[0].split("?", 1)[0].strip()
    if not value or value.startswith("/"):
        return ""
    return unquote(value)


def html_refs(text: str) -> list[str]:
    parser = LocalReferenceParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    refs = list(parser.refs)
    refs.extend(re.findall(r"url\(([^)]+)\)", text, flags=re.IGNORECASE))
    cleaned = []
    for ref in refs:
        ref = ref.strip().strip("\"'")
        ref = clean_ref(ref)
        if ref:
            cleaned.append(ref)
    return sorted(set(cleaned))


def course_image_reference_candidates(text: str) -> list[tuple[str, str]]:
    """Return likely Unit cover images in deterministic preference order."""
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(reference, source: str) -> None:
        cleaned = clean_ref(str(reference or ""))
        if not cleaned or "${" in cleaned or Path(cleaned).suffix.lower() not in COURSE_IMAGE_EXTENSIONS:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append((cleaned, source))

    # A literal <img> is the strongest signal for the Unit's first learner-facing
    # picture. Regex is intentional here: many FLW Units build their markup in a
    # JavaScript template literal, which HTMLParser treats as script text.
    for tag_match in re.finditer(r"<img\b[^>]*>", text, flags=re.IGNORECASE | re.DOTALL):
        source_match = re.search(
            r"\bsrc\s*=\s*(?:([\"'])(.*?)\1|([^\s>]+))",
            tag_match.group(0),
            flags=re.IGNORECASE | re.DOTALL,
        )
        if source_match:
            add(html.unescape(source_match.group(2) or source_match.group(3) or ""), "html_img")

    # Dynamic templates often use ${UNIT.images.img01}; embedded JSON retains
    # author order and normally lists the opening/cover image first.
    unit_data = extract_unit_meta_data(text)

    def add_data_images(value) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                add_data_images(nested)
        elif isinstance(value, list):
            for nested in value:
                add_data_images(nested)
        elif isinstance(value, str):
            add(value, "unit_data")

    add_data_images(unit_data)

    # CSS backgrounds are a useful fallback for Units whose hero has no <img>.
    for url_match in re.finditer(r"url\(\s*([^)]+?)\s*\)", text, flags=re.IGNORECASE | re.DOTALL):
        add(url_match.group(1).strip().strip("\"'"), "css_url")
    return candidates


def normalized_package_reference(reference: str, launch_file: str = "index.html") -> str:
    cleaned = clean_ref(reference)
    if not cleaned:
        return ""
    launch_dir = posixpath.dirname(str(launch_file or "index.html").replace("\\", "/").lstrip("/"))
    normalized = posixpath.normpath(posixpath.join(launch_dir, cleaned)).replace("\\", "/")
    if normalized in {"", ".", ".."} or normalized.startswith("../") or normalized.startswith("/"):
        return ""
    return normalized


def first_unit_course_image(unit_path: Path, launch_file: str = "index.html") -> dict | None:
    """Select the first usable raster image that will be present in a SCORM ZIP."""
    launch_path = safe_join(unit_path, launch_file)
    candidates: list[tuple[str, str, str]] = []
    if launch_path.exists() and launch_path.is_file():
        source_html = read_text(launch_path)
        for reference, selection_source in course_image_reference_candidates(source_html):
            package_path = normalized_package_reference(reference, launch_file)
            if package_path:
                candidates.append((package_path, selection_source, reference))

    seen: set[str] = set()
    for package_path, selection_source, source_reference in candidates:
        key = package_path.casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            image_path = safe_join(unit_path, package_path)
        except AppError:
            continue
        if not image_path.is_file() or image_path.suffix.lower() not in COURSE_IMAGE_EXTENSIONS:
            continue
        return {
            "packagePath": package_path,
            "filename": image_path.name,
            "extension": image_path.suffix.lower(),
            "mimeType": mimetypes.guess_type(image_path.name)[0] or "application/octet-stream",
            "size": image_path.stat().st_size,
            "sha256": file_sha256(image_path),
            "selectionSource": selection_source,
            "sourceReference": source_reference,
        }

    fallback_paths = sorted(
        (
            path
            for path in unit_path.rglob("*")
            if path.is_file()
            and path.suffix.lower() in COURSE_IMAGE_EXTENSIONS
            and not any(part in SKIP_EXPORT_DIRS for part in path.relative_to(unit_path).parts)
            and not path.relative_to(unit_path).as_posix().startswith("assets/scorm/")
        ),
        key=lambda path: path.relative_to(unit_path).as_posix().casefold(),
    )
    if not fallback_paths:
        return None
    image_path = fallback_paths[0]
    package_path = image_path.relative_to(unit_path).as_posix()
    return {
        "packagePath": package_path,
        "filename": image_path.name,
        "extension": image_path.suffix.lower(),
        "mimeType": mimetypes.guess_type(image_path.name)[0] or "application/octet-stream",
        "size": image_path.stat().st_size,
        "sha256": file_sha256(image_path),
        "selectionSource": "sorted_asset_fallback",
        "sourceReference": package_path,
    }


def ref_kind(ref: str) -> str:
    ext = Path(str(ref or "").split("#", 1)[0].split("?", 1)[0]).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return "image"
    if ext in {".mp3", ".m4a", ".wav", ".ogg"}:
        return "audio"
    if ext in {".mp4", ".webm", ".mov"}:
        return "video"
    if ext in {".css", ".js", ".json", ".csv", ".xml", ".html", ".htm"}:
        return "text"
    return "link"


def validate_unit(unit_path: Path) -> dict:
    issues: list[dict] = []
    warnings: list[dict] = []
    missing_refs: list[dict] = []
    stats = scan_unit_counts(unit_path)
    meta = index_meta(unit_path)
    index = unit_path / "index.html"

    if not index.exists():
        issues.append({"level": "error", "message": "index.html is missing"})
    else:
        text = read_text(index)
        missing_refs = []
        for ref in html_refs(text):
            try:
                target = safe_join(unit_path, ref)
            except AppError:
                warnings.append({"level": "warning", "message": f"Skipped unusual reference: {ref}"})
                continue
            if not target.exists():
                missing_refs.append(ref)
        for ref in missing_refs[:200]:
            issues.append({"level": "error", "message": f"Missing local reference: {ref}"})
        if len(missing_refs) > 200:
            issues.append({"level": "error", "message": f"{len(missing_refs) - 200} more missing references hidden"})
        try:
            read_unit_data(unit_path)
        except AppError as exc:
            warnings.append({"level": "warning", "message": str(exc)})

    for csv_path in unit_path.rglob("*.csv"):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                next(csv.reader(handle), None)
        except Exception as exc:
            rel = csv_path.relative_to(unit_path).as_posix()
            issues.append({"level": "error", "message": f"CSV read error in {rel}: {exc}"})

    if stats["images"] == 0:
        warnings.append({"level": "warning", "message": "No image assets found"})
    if stats["video"] == 0:
        warnings.append({"level": "warning", "message": "No video assets found"})

    return {
        "unit": unit_number_from_path(unit_path),
        "title": meta.get("title") or "",
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "missingRefs": [{"ref": ref, "kind": ref_kind(ref)} for ref in missing_refs],
        "stats": stats,
    }


def backup_file(unit_path: Path, target: Path) -> str | None:
    if not target.exists():
        return None
    rel = target.relative_to(unit_path)
    stamp = now_stamp()
    backup_dir = unit_path / ".scorm_gui_backups" / stamp
    backup = backup_dir / rel
    for index in range(2, 1000):
        if not backup.exists():
            break
        backup_dir = unit_path / ".scorm_gui_backups" / f"{stamp}_{index:02d}"
        backup = backup_dir / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    return str(backup)


def replace_index_reference(unit_path: Path, old_ref: str, new_ref: str) -> dict:
    old_ref = clean_ref(old_ref)
    new_ref = clean_ref(new_ref)
    if not old_ref:
        raise AppError("Missing broken reference to replace")
    if not new_ref:
        raise AppError("Choose a replacement reference")
    replacement_target = safe_join(unit_path, new_ref)
    if not replacement_target.exists():
        raise AppError(f"Replacement does not exist in this unit: {new_ref}", 404)
    index = unit_path / "index.html"
    if not index.exists():
        raise AppError("index.html is missing", 404)
    text = read_text(index)
    count = text.count(old_ref)
    if not count:
        raise AppError(f"Reference was not found in index.html: {old_ref}", 404)
    backup = backup_file(unit_path, index)
    write_text(index, text.replace(old_ref, new_ref))
    return {"oldRef": old_ref, "newRef": new_ref, "count": count, "backup": backup}


def read_csv_file(path: Path) -> dict:
    text = read_text(path)
    rows = list(csv.DictReader(text.splitlines()))
    headers = list(rows[0].keys()) if rows else []
    if not headers:
        sample = next(csv.reader(text.splitlines()), [])
        headers = sample
    return {"headers": headers, "rows": rows}


def write_csv_file(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def read_unit_data(unit_path: Path) -> dict:
    index = unit_path / "index.html"
    if not index.exists():
        raise AppError("index.html is missing", 404)
    text = read_text(index)
    span = find_json_object_span(text, "window.UNIT_DATA=")
    if not span:
        raise AppError("window.UNIT_DATA was not found in index.html", 404)
    try:
        data = json.loads(text[span[0] : span[1]])
    except json.JSONDecodeError as exc:
        raise AppError(f"window.UNIT_DATA is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AppError("window.UNIT_DATA must be a JSON object")
    return data


def unit_data_summary(data: dict) -> dict:
    return {
        "course": data.get("course") or "",
        "unit": data.get("unit") or "",
        "title": data.get("title") or "",
        "stage": data.get("stage") or data.get("cefr") or "",
        "vocab": len(data.get("vocab") or []),
        "lessons": len(data.get("lessons") or []),
        "watch": len(data.get("watch") or []),
        "practiceSets": len(data.get("practice") or {}) if isinstance(data.get("practice"), dict) else 0,
    }


def write_unit_data(unit_path: Path, data: dict) -> str | None:
    if not isinstance(data, dict):
        raise AppError("Unit data must be a JSON object")
    index = unit_path / "index.html"
    if not index.exists():
        raise AppError("index.html is missing", 404)
    text = read_text(index)
    span = find_json_object_span(text, "window.UNIT_DATA=")
    if not span:
        raise AppError("window.UNIT_DATA was not found in index.html", 404)
    backup = backup_file(unit_path, index)
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    write_text(index, text[: span[0]] + compact + text[span[1] :])
    return backup


def visual_runtime_block(edits: list[dict]) -> str:
    edits_json = json.dumps(edits, ensure_ascii=False, separators=(",", ":"))
    return f"""{VISUAL_EDIT_START}
<script>
(function(){{
  window.FLW_VISUAL_EDITS={edits_json};
  var visualStyleClasses=["flw-style-card","flw-style-highlight","flw-style-note","flw-style-tip","flw-style-warning","flw-style-quote","flw-style-hero","flw-style-soft","flw-style-custom"];
  var applying=false;
  function insertedSelector(id){{return '[data-flw-insert-id="'+String(id).replace(/"/g,'\\\\"')+'"]';}}
  function movedSelector(id){{return '[data-flw-move-id="'+String(id).replace(/"/g,'\\\\"')+'"]';}}
  function movableTarget(el){{
    return el&&el.closest("details.lesson,section.panel,section[id],article,figure,footer,.footer,[role='contentinfo'],.hero,.study-wide,.practice-wide,.word-card,.quiz-card,.script-line,.model,.box")||el;
  }}
  function styleTarget(el){{return movableTarget(el);}}
  function applyBlockStyle(el,style){{
    if(!el||!el.classList)return;
    visualStyleClasses.forEach(function(cls){{el.classList.remove(cls);}});
    ["--flw-custom-bg","--flw-custom-border","--flw-custom-padding","--flw-custom-radius","--flw-custom-shadow"].forEach(function(name){{try{{el.style.removeProperty(name);}}catch(err){{}}}});
    el.removeAttribute("data-flw-block-style");
    if(!style||style==="none")return;
    el.classList.add("flw-style-"+style);
    el.setAttribute("data-flw-block-style",style);
  }}
  function applyCustomStyle(el,custom){{
    if(!el||!el.classList)return;
    applyBlockStyle(el,"custom");
    custom=custom||{{}};
    if(custom.background)el.style.setProperty("--flw-custom-bg",custom.background);
    if(custom.borderColor)el.style.setProperty("--flw-custom-border",custom.borderColor);
    if(custom.padding)el.style.setProperty("--flw-custom-padding",custom.padding);
    if(custom.radius)el.style.setProperty("--flw-custom-radius",custom.radius);
    el.style.setProperty("--flw-custom-shadow",custom.shadow?"0 14px 30px rgba(32,54,74,.18)":"none");
  }}
  function linkTarget(el){{return el&&(el.closest&&el.closest("a[href]")||(el.tagName&&el.tagName.toLowerCase()==="a"?el:null));}}
  function moveToParentStart(el){{
    if(!el||!el.parentElement)return;
    var first=Array.from(el.parentElement.children).find(function(node){{return node.nodeType===1&&node!==el;}});
    if(first&&first!==el)el.parentElement.insertBefore(el,first);
  }}
  function applyVisualEdit(edit){{
    if(!edit||!edit.selector)return;
    var action=edit.action||((edit.html!==undefined)?"replaceHtml":((edit.text!==undefined)?"setText":""));
    if(action==="moveToTop"){{
      var marked=edit.id?document.querySelector(movedSelector(edit.id)):null;
      var target=marked||movableTarget(document.querySelector(edit.selector));
      if(!target)return;
      if(edit.id)target.setAttribute("data-flw-move-id",edit.id);
      moveToParentStart(target);
      return;
    }}
    var el=document.querySelector(edit.selector);
    if(action==="setBlockStyle"){{
      applyBlockStyle(styleTarget(el),edit.style||"none");
      return;
    }}
    if(action==="setCustomStyle"){{
      applyCustomStyle(styleTarget(el),edit.custom||{{}});
      return;
    }}
    if(action==="setLink"){{
      var link=linkTarget(el);
      if(link&&edit.href!==undefined)link.setAttribute("href",edit.href);
      return;
    }}
    if(action==="insertAfter"){{
      if(!el||!edit.html||!edit.id||document.querySelector(insertedSelector(edit.id)))return;
      el.insertAdjacentHTML("afterend",'<div class="flw-inserted-block" data-flw-insert-id="'+String(edit.id).replace(/"/g,'&quot;')+'">'+edit.html+'</div>');
      return;
    }}
    if(!el)return;
    if(action==="remove"){{
      el.remove();
      return;
    }}
    if(action==="setImage"){{
      if(el.tagName&&el.tagName.toLowerCase()==="img"){{
        if(edit.src!==undefined)el.setAttribute("src",edit.src);
        if(edit.alt!==undefined)el.setAttribute("alt",edit.alt);
      }}
      return;
    }}
    if(action==="setMedia"){{
      var mediaTarget=el;
      if(el.tagName&&el.tagName.toLowerCase()==="source")mediaTarget=el.parentElement||el;
      if(el.tagName&&el.tagName.toLowerCase()!=="source"){{var source=el.querySelector&&el.querySelector("source");if(source)el=source;}}
      if(edit.src!==undefined)el.setAttribute("src",edit.src);
      if(mediaTarget&&mediaTarget.load)try{{mediaTarget.load();}}catch(err){{}}
      return;
    }}
    if(action==="replaceHtml"&&edit.html!==undefined&&el.innerHTML!==edit.html){{
      el.innerHTML=edit.html;
      return;
    }}
    if(action==="setText"&&edit.text!==undefined&&el.textContent!==edit.text){{
      el.textContent=edit.text;
      if(el.matches&&el.matches("button,[role='button']")){{el.setAttribute("title",edit.text);el.setAttribute("aria-label",edit.text);}}
    }}
  }}
  function applyVisualEdits(){{
    if(applying)return;
    applying=true;
    try{{
      (window.FLW_VISUAL_EDITS||[]).forEach(applyVisualEdit);
    }}finally{{
      applying=false;
    }}
  }}
  window.FLWApplyVisualEdits=applyVisualEdits;
  function schedule(){{clearTimeout(window.FLW_VISUAL_EDIT_TIMER);window.FLW_VISUAL_EDIT_TIMER=setTimeout(applyVisualEdits,60);}}
  if(!document.getElementById("flw-visual-block-style-css")){{
    var style=document.createElement("style");
    style.id="flw-visual-block-style-css";
    style.textContent={json.dumps(BLOCK_STYLE_CSS)};
    document.head.appendChild(style);
  }}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",schedule);else schedule();
  window.addEventListener("load",schedule);
  try{{new MutationObserver(schedule).observe(document.body,{{childList:true,subtree:true}});}}catch(err){{}}
}}());
</script>
{VISUAL_EDIT_END}"""


def read_visual_edits(unit_path: Path) -> list[dict]:
    index = unit_path / "index.html"
    if not index.exists():
        return []
    text = read_text(index)
    block_match = re.search(
        re.escape(VISUAL_EDIT_START) + r"(.*?)" + re.escape(VISUAL_EDIT_END),
        text,
        flags=re.DOTALL,
    )
    if not block_match:
        return []
    block = block_match.group(1)
    match = re.search(r"window\.FLW_VISUAL_EDITS\s*=\s*(\[.*?\]);", block, flags=re.DOTALL)
    if not match:
        return []
    try:
        edits = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return edits if isinstance(edits, list) else []


def normalized_visual_edits(edits: list[dict]) -> list[dict]:
    rows = []
    for edit in edits or []:
        if not isinstance(edit, dict):
            continue
        selector = str(edit.get("selector") or "").strip()
        if not selector:
            continue
        action = str(edit.get("action") or "").strip()
        if not action:
            if "html" in edit:
                action = "replaceHtml"
            elif "text" in edit:
                action = "setText"
        row = {"selector": selector, "action": action}
        if action == "replaceHtml" and "html" in edit:
            row["html"] = str(edit.get("html") or "")
        elif action == "setText" and "text" in edit:
            row["text"] = str(edit.get("text") or "")
        elif action == "setImage":
            src = str(edit.get("src") or "").strip().replace("\\", "/")
            if not src:
                continue
            row["src"] = src
            if "alt" in edit:
                row["alt"] = str(edit.get("alt") or "")
        elif action == "setMedia":
            src = str(edit.get("src") or "").strip().replace("\\", "/")
            if not src:
                continue
            row["src"] = src
        elif action == "setLink":
            href = str(edit.get("href") or "").strip().replace("\\", "/")
            if not href:
                continue
            row["href"] = href[:500]
        elif action == "remove":
            pass
        elif action == "insertAfter":
            html_value = str(edit.get("html") or "").strip()
            insert_id = str(edit.get("id") or uuid.uuid4().hex).strip()
            if not html_value:
                continue
            row["html"] = html_value
            row["id"] = insert_id
        elif action == "moveToTop":
            row["id"] = str(edit.get("id") or uuid.uuid4().hex).strip()
        elif action == "setBlockStyle":
            style = str(edit.get("style") or "none").strip()
            if style not in {"none", "card", "highlight", "note", "tip", "warning", "quote", "hero", "soft"}:
                continue
            row["style"] = style
        elif action == "setCustomStyle":
            incoming_custom = edit.get("custom") if isinstance(edit.get("custom"), dict) else {}
            custom: dict[str, str | bool] = {}
            for key in ("background", "borderColor", "padding", "radius"):
                value = str(incoming_custom.get(key) or "").strip()
                if value and len(value) <= 80 and not re.search(r"[;{}<>]", value):
                    custom[key] = value
            custom["shadow"] = bool(incoming_custom.get("shadow"))
            row["custom"] = custom
        else:
            continue
        rows.append(row)
    return rows


def visual_edit_key(edit: dict) -> str:
    action = edit.get("action") or ""
    if action == "insertAfter":
        return f"insertAfter::{edit.get('selector')}::{edit.get('id')}"
    if action == "moveToTop":
        return f"moveToTop::{edit.get('selector')}"
    return f"{action}::{edit.get('selector')}"


def write_visual_edits(unit_path: Path, edits: list[dict]) -> str | None:
    index = unit_path / "index.html"
    if not index.exists():
        raise AppError("index.html is missing", 404)
    text = read_text(index)
    backup = backup_file(unit_path, index)
    cleaned = re.sub(
        re.escape(VISUAL_EDIT_START) + r".*?" + re.escape(VISUAL_EDIT_END),
        "",
        text,
        flags=re.DOTALL,
    ).rstrip()
    edits = normalized_visual_edits(edits)
    if edits:
        block = "\n" + visual_runtime_block(edits) + "\n"
        if re.search(r"</body\s*>", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(
                r"</body\s*>",
                lambda match: block + match.group(0),
                cleaned,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            cleaned += block
    write_text(index, cleaned)
    return backup


def merge_visual_edits(unit_path: Path, incoming: list[dict], mode: str = "merge") -> tuple[list[dict], str | None]:
    incoming = normalized_visual_edits(incoming)
    if mode == "clear":
        backup = write_visual_edits(unit_path, [])
        return [], backup
    if mode == "replace":
        backup = write_visual_edits(unit_path, incoming)
        return incoming, backup
    by_selector = {visual_edit_key(edit): edit for edit in read_visual_edits(unit_path)}
    for edit in incoming:
        by_selector[visual_edit_key(edit)] = edit
    merged = list(by_selector.values())
    backup = write_visual_edits(unit_path, merged)
    return merged, backup


VISUAL_EDIT_BRIDGE = r"""
<script>
(function(){
  var editableSelector="h1,h2,h3,h4,h5,h6,p,li,dt,dd,figcaption,caption,th,td,label,legend,summary,button,a,[role='button'],footer,.footer,[role='contentinfo'],.copyright,.credits,span,strong,em,b,i,u,small,mark,code,.study-line,.line,.reading-sentence,.meaning,.eg,.note,.aim,.mission,.title,.subtitle,.caption,.question,.answer,.option,.feedback,.instruction,.prompt,.label,.badge";
  var blockedSelector="script,style,input,textarea,select,option,video,audio,canvas,svg,iframe,object,embed,img,.modal,.audio-btn,[hidden],[aria-hidden='true']";
  var selectableSelector="img,audio,video,source,section.panel,details.lesson,article,figure,.hero,.hero-card,.study-wide,.practice-wide,.word-card,.quiz-card,.script-line,.model,.box,"+editableSelector;
  var interactiveTextSelector="button,a,[role='button'],summary";
  var visualStyleClasses=["flw-style-card","flw-style-highlight","flw-style-note","flw-style-tip","flw-style-warning","flw-style-quote","flw-style-hero","flw-style-soft","flw-style-custom"];
  var editables=[];
  var selectedEl=null;
  var inputTimer=null;
  var applyingVisualOp=false;
  function esc(value){if(window.CSS&&CSS.escape)return CSS.escape(value);return String(value).replace(/[^a-zA-Z0-9_-]/g,function(ch){return '\\\\'+ch.charCodeAt(0).toString(16)+' ';});}
  function uniqueSelector(el){
    if(el.id)return "#"+esc(el.id);
    var parts=[];
    while(el&&el.nodeType===1&&el!==document.body){
      var part=el.tagName.toLowerCase();
      if(el.classList.length){
        part+="."+Array.from(el.classList).filter(function(cls){return !cls.startsWith("flw-visual-")&&!cls.startsWith("active")&&!cls.startsWith("selected");}).slice(0,2).map(esc).join(".");
      }
      var same=Array.from(el.parentNode?el.parentNode.children:[]).filter(function(node){return node.tagName===el.tagName;});
      if(same.length>1)part+=":nth-of-type("+(same.indexOf(el)+1)+")";
      parts.unshift(part);
      var selector=parts.join(">");
      try{if(document.querySelectorAll(selector).length===1)return selector;}catch(err){}
      el=el.parentElement;
    }
    return parts.join(">");
  }
  function isVisible(el){
    if(!el||!el.ownerDocument||el.closest("[hidden],[aria-hidden='true']"))return false;
    var style=window.getComputedStyle?window.getComputedStyle(el):null;
    if(style&&(style.display==="none"||style.visibility==="hidden"||Number(style.opacity)===0))return false;
    return !!(el.getClientRects&&el.getClientRects().length);
  }
  function ownText(el){
    return Array.from(el.childNodes||[]).filter(function(node){return node.nodeType===3;}).map(function(node){return node.nodeValue||"";}).join(" ").replace(/\s+/g," ").trim();
  }
  function isLooseTextHost(el){
    if(!el||!ownText(el))return false;
    if(el.matches("html,body,main,section,article,aside,header,nav,.nav,[role='navigation'],ul,ol,table,thead,tbody,tfoot,tr,details"))return false;
    if((el.textContent||"").trim().length>600)return false;
    return true;
  }
  function hasEditableAncestor(el){
    return editables.some(function(candidate){return candidate!==el&&candidate.contains(el);});
  }
  function addEditable(el){
    if(!isCandidate(el)||hasEditableAncestor(el)||editables.indexOf(el)!==-1)return;
    editables.push(el);
  }
  function isCandidate(el){
    if(!el||el.closest(blockedSelector)||!isVisible(el))return false;
    if(el.querySelector(blockedSelector))return false;
    var text=(el.textContent||"").trim();
    if(el.dataset&&el.dataset.flwEditSelector&&el.dataset.flwOriginalHtml!==undefined)return true;
    if(text.length<1||text.length>1200)return false;
    return true;
  }
  function sanitizeHtml(html){
    var template=document.createElement("template");
    template.innerHTML=html;
    template.content.querySelectorAll("script,style,iframe,object,embed,link,meta").forEach(function(node){node.remove();});
    template.content.querySelectorAll("*").forEach(function(node){
      Array.from(node.attributes).forEach(function(attr){
        if(/^on/i.test(attr.name))node.removeAttribute(attr.name);
        if(/^data-flw/i.test(attr.name))node.removeAttribute(attr.name);
        if(attr.name==="contenteditable"||attr.name==="spellcheck")node.removeAttribute(attr.name);
      });
      if(node.classList){
        ["flw-visual-editable","flw-visual-selected"].forEach(function(cls){node.classList.remove(cls);});
      }
    });
    return template.innerHTML;
  }
  function sourceValue(el){
    var tag=(el.tagName||"").toLowerCase();
    if(tag==="img"||tag==="audio"||tag==="video"){
      return el.getAttribute("src")||(el.querySelector&&el.querySelector("source")&&el.querySelector("source").getAttribute("src"))||"";
    }
    if(tag==="source")return el.getAttribute("src")||"";
    return "";
  }
  function linkTarget(el){return el&&(el.closest&&el.closest("a[href]")||(el.tagName&&el.tagName.toLowerCase()==="a"?el:null));}
  function hrefValue(el){var link=linkTarget(el);return link?link.getAttribute("href")||"":"";}
  function styleTarget(el){
    return el&&el.closest("details.lesson,section.panel,section[id],article,figure,footer,.footer,[role='contentinfo'],.hero,.study-wide,.practice-wide,.word-card,.quiz-card,.script-line,.model,.box")||el;
  }
  function styleValue(el){
    var target=styleTarget(el);
    return target&&target.dataset?target.dataset.flwBlockStyle||"none":"none";
  }
  function applyBlockStyle(el,style){
    if(!el||!el.classList)return;
    visualStyleClasses.forEach(function(cls){el.classList.remove(cls);});
    ["--flw-custom-bg","--flw-custom-border","--flw-custom-padding","--flw-custom-radius","--flw-custom-shadow"].forEach(function(name){try{el.style.removeProperty(name);}catch(err){}});
    if(el.dataset)delete el.dataset.flwBlockStyle;
    el.removeAttribute("data-flw-block-style");
    if(!style||style==="none")return;
    el.classList.add("flw-style-"+style);
    el.setAttribute("data-flw-block-style",style);
  }
  function applyCustomStyle(el,custom){
    if(!el||!el.classList)return;
    applyBlockStyle(el,"custom");
    custom=custom||{};
    if(custom.background)el.style.setProperty("--flw-custom-bg",custom.background);
    if(custom.borderColor)el.style.setProperty("--flw-custom-border",custom.borderColor);
    if(custom.padding)el.style.setProperty("--flw-custom-padding",custom.padding);
    if(custom.radius)el.style.setProperty("--flw-custom-radius",custom.radius);
    el.style.setProperty("--flw-custom-shadow",custom.shadow?"0 14px 30px rgba(32,54,74,.18)":"none");
  }
  function selectedInfo(el){
    if(!el)return null;
    if(!el.dataset.flwEditSelector)el.dataset.flwEditSelector=uniqueSelector(el);
    return {
      selector:el.dataset.flwEditSelector,
      tag:(el.tagName||"").toLowerCase(),
      text:(el.textContent||"").trim().slice(0,220),
      src:sourceValue(el),
      href:hrefValue(el),
      alt:el.tagName&&el.tagName.toLowerCase()==="img"?el.getAttribute("alt"):"",
      style:styleValue(el),
      html:sanitizeHtml(el.outerHTML||"")
    };
  }
  function selectElement(el){
    if(!el)return;
    if(selectedEl)selectedEl.classList.remove("flw-visual-selected");
    selectedEl=el;
    selectedEl.classList.add("flw-visual-selected");
    window.parent.postMessage({type:"flw-visual-selection",selection:selectedInfo(selectedEl)},"*");
  }
  function insertedSelector(id){return '[data-flw-insert-id="'+String(id).replace(/"/g,'\\\\"')+'"]';}
  function movedSelector(id){return '[data-flw-move-id="'+String(id).replace(/"/g,'\\\\"')+'"]';}
  function movableTarget(el){
    return el&&el.closest("details.lesson,section.panel,section[id],article,figure,footer,.footer,[role='contentinfo'],.hero,.study-wide,.practice-wide,.word-card,.quiz-card,.script-line,.model,.box")||el;
  }
  function moveToParentStart(el){
    if(!el||!el.parentElement)return;
    var first=Array.from(el.parentElement.children).find(function(node){return node.nodeType===1&&node!==el;});
    if(first&&first!==el)el.parentElement.insertBefore(el,first);
  }
  function applyVisualOp(op){
    if(!op||!op.selector)return;
    applyingVisualOp=true;
    var action=op.action||((op.html!==undefined)?"replaceHtml":((op.text!==undefined)?"setText":""));
    try{
    if(action==="moveToTop"){
      var marked=op.id?document.querySelector(movedSelector(op.id)):null;
      var target=marked||movableTarget(document.querySelector(op.selector));
      if(!target)return;
      if(op.id)target.setAttribute("data-flw-move-id",op.id);
      moveToParentStart(target);
      return;
    }
    var el=document.querySelector(op.selector);
    if(action==="setBlockStyle"){
      applyBlockStyle(styleTarget(el),op.style||"none");
      if(selectedEl)window.parent.postMessage({type:"flw-visual-selection",selection:selectedInfo(selectedEl)},"*");
      return;
    }
    if(action==="setCustomStyle"){
      applyCustomStyle(styleTarget(el),op.custom||{});
      if(selectedEl)window.parent.postMessage({type:"flw-visual-selection",selection:selectedInfo(selectedEl)},"*");
      return;
    }
    if(action==="setLink"){
      var link=linkTarget(el);
      if(link&&op.href!==undefined)link.setAttribute("href",op.href);
      if(selectedEl)window.parent.postMessage({type:"flw-visual-selection",selection:selectedInfo(selectedEl)},"*");
      return;
    }
    if(action==="insertAfter"){
      if(!el||!op.html||!op.id||document.querySelector(insertedSelector(op.id)))return;
      el.insertAdjacentHTML("afterend",'<div class="flw-inserted-block" data-flw-insert-id="'+String(op.id).replace(/"/g,'&quot;')+'">'+op.html+'</div>');
      return;
    }
    if(!el)return;
    if(action==="remove"){
      el.remove();
      if(selectedEl===el)selectedEl=null;
      return;
    }
    if(action==="setImage"){
      if(el.tagName&&el.tagName.toLowerCase()==="img"){
        if(op.src!==undefined)el.setAttribute("src",op.src);
        if(op.alt!==undefined)el.setAttribute("alt",op.alt||"");
      }
      return;
    }
    if(action==="setMedia"){
      var mediaTarget=el;
      if(el.tagName&&el.tagName.toLowerCase()==="source")mediaTarget=el.parentElement||el;
      if(el.tagName&&el.tagName.toLowerCase()!=="source"){var source=el.querySelector&&el.querySelector("source");if(source)el=source;}
      if(op.src!==undefined)el.setAttribute("src",op.src);
      if(mediaTarget&&mediaTarget.load)try{mediaTarget.load();}catch(err){}
      return;
    }
    if(action==="replaceHtml"&&op.html!==undefined){el.innerHTML=op.html;return;}
    if(action==="setText"&&op.text!==undefined){
      el.textContent=op.text;
      if(el.matches&&el.matches("button,[role='button']")){el.setAttribute("title",op.text);el.setAttribute("aria-label",op.text);}
    }
    }finally{applyingVisualOp=false;}
  }
  function markTextChanged(el, source){
    if(applyingVisualOp)return;
    if(!el||!el.dataset||!el.dataset.flwEditSelector)return;
    clearTimeout(inputTimer);
    inputTimer=setTimeout(function(){
      var edit=null;
      if(el.innerHTML!==el.dataset.flwOriginalHtml)edit={selector:el.dataset.flwEditSelector,html:sanitizeHtml(el.innerHTML)};
      window.parent.postMessage({type:"flw-visual-text-change",selection:selectedInfo(el),edit:edit,source:source||"input"},"*");
    },80);
  }
  function execCommand(command){
    try{
      document.execCommand(command,false,null);
      if(selectedEl)markTextChanged(selectedEl,command);
      return true;
    }catch(err){
      return false;
    }
  }
  function scan(resetOriginal){
    editables=[];
    document.querySelectorAll(editableSelector).forEach(addEditable);
    document.querySelectorAll("body *").forEach(function(el){
      if(isLooseTextHost(el))addEditable(el);
    });
    editables.forEach(function(el){
      if(!el.dataset.flwEditSelector)el.dataset.flwEditSelector=uniqueSelector(el);
      if(resetOriginal||!el.dataset.flwOriginalHtml)el.dataset.flwOriginalHtml=el.innerHTML;
    });
    return editables.length;
  }
  function enable(){
    scan(true);
    editables.forEach(function(el){
      el.contentEditable="true";
      el.spellcheck=false;
      el.classList.add("flw-visual-editable");
    });
    document.body.classList.add("flw-visual-editing");
    window.parent.postMessage({type:"flw-visual-enabled",count:editables.length},"*");
  }
  function disable(){
    editables.forEach(function(el){
      el.removeAttribute("contenteditable");
      el.classList.remove("flw-visual-editable");
    });
    if(selectedEl)selectedEl.classList.remove("flw-visual-selected");
    selectedEl=null;
    document.body.classList.remove("flw-visual-editing");
    window.parent.postMessage({type:"flw-visual-disabled"},"*");
  }
  function collect(){
    scan(false);
    var edits=[];
    editables.forEach(function(el){
      if(el.innerHTML!==el.dataset.flwOriginalHtml){
        edits.push({selector:el.dataset.flwEditSelector,html:sanitizeHtml(el.innerHTML)});
      }
    });
    window.parent.postMessage({type:"flw-visual-edits",edits:edits},"*");
  }
  function toggleEditableMap(){
    scan(false);
    document.body.classList.toggle("flw-show-editable-map");
    window.parent.postMessage({type:"flw-visual-map",shown:document.body.classList.contains("flw-show-editable-map"),count:editables.length},"*");
  }
  function selectRelative(direction){
    if(!selectedEl)return;
    scan(false);
    var next=null;
    if(direction==="parent"){
      next=selectedEl.parentElement&&selectedEl.parentElement.closest(selectableSelector);
      if(next===selectedEl)next=selectedEl.parentElement&&selectedEl.parentElement.parentElement&&selectedEl.parentElement.parentElement.closest(selectableSelector);
    }else if(direction==="child"){
      next=Array.from(selectedEl.querySelectorAll(selectableSelector)).find(function(el){return el!==selectedEl&&isVisible(el);});
    }
    if(next)selectElement(next);
  }
  window.addEventListener("message",function(event){
    var msg=event.data||{};
    if(msg.type==="flw-enable-visual-edit")enable();
    if(msg.type==="flw-disable-visual-edit")disable();
    if(msg.type==="flw-collect-visual-edits")collect();
    if(msg.type==="flw-toggle-editable-map")toggleEditableMap();
    if(msg.type==="flw-select-relative")selectRelative(msg.direction);
    if(msg.type==="flw-apply-visual-op")applyVisualOp(msg.op);
    if(msg.type==="flw-undo")execCommand("undo");
    if(msg.type==="flw-redo")execCommand("redo");
  });
  document.addEventListener("input",function(event){
    if(!document.body.classList.contains("flw-visual-editing"))return;
    var target=event.target&&event.target.closest(".flw-visual-editable");
    if(target)markTextChanged(target,"input");
  },true);
  document.addEventListener("keydown",function(event){
    if(!document.body.classList.contains("flw-visual-editing"))return;
    if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
    var key=String(event.key||"").toLowerCase();
    if(key==="z"&&event.shiftKey){event.preventDefault();execCommand("redo");}
    else if(key==="z"){event.preventDefault();execCommand("undo");}
    else if(key==="y"){event.preventDefault();execCommand("redo");}
  },true);
  document.addEventListener("click",function(event){
    if(!document.body.classList.contains("flw-visual-editing"))return;
    var editableTarget=event.target&&event.target.closest(".flw-visual-editable");
    var target=editableTarget||(event.target&&event.target.closest(selectableSelector));
    if(!target||target.closest("input,textarea,select,.modal"))return;
    if(target.matches&&target.matches("audio,video,source")){
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    }
    if(target.matches(interactiveTextSelector)||event.target.closest(interactiveTextSelector)){
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      setTimeout(function(){try{target.focus({preventScroll:true});}catch(err){try{target.focus();}catch(ignore){}}},0);
    }
    selectElement(target);
  },true);
  var style=document.createElement("style");
  style.textContent=".flw-visual-editing .flw-visual-editable{outline:2px dashed #d29a30;outline-offset:2px;cursor:text;user-select:text}.flw-visual-editing .flw-visual-editable:focus{outline:3px solid #255f92;background:#fffbe8}.flw-visual-editing .flw-visual-selected{outline:4px solid #255f92!important;outline-offset:4px!important;box-shadow:0 0 0 4px rgba(37,95,146,.18)!important}.flw-show-editable-map .flw-visual-editable{outline:3px solid rgba(53,166,107,.95)!important;outline-offset:3px!important;background-image:linear-gradient(rgba(53,166,107,.08),rgba(53,166,107,.08))!important}.flw-inserted-block{margin:14px 0}.flw-style-card{background:#fff!important;border:1px solid #d8e3ec!important;border-radius:18px!important;box-shadow:0 16px 34px rgba(32,54,74,.14)!important;padding:18px!important}.flw-style-highlight{background:linear-gradient(135deg,#fff7cf,#fffdf2)!important;border:1px solid #f0ce68!important;border-radius:16px!important;padding:16px!important;box-shadow:0 10px 24px rgba(169,109,36,.12)!important}.flw-style-note{background:#eef7ff!important;border-left:7px solid #2f7db7!important;border-radius:14px!important;padding:16px!important}.flw-style-tip{background:#edf9f1!important;border-left:7px solid #35a66b!important;border-radius:14px!important;padding:16px!important}.flw-style-warning{background:#fff1ef!important;border-left:7px solid #d1534a!important;border-radius:14px!important;padding:16px!important}.flw-style-quote{background:#f7f5ff!important;border-left:7px solid #7765cf!important;border-radius:14px!important;padding:16px 18px!important;font-style:italic!important}.flw-style-hero{background:linear-gradient(135deg,#255f92,#38a2c7)!important;color:#fff!important;border-radius:22px!important;padding:24px!important;box-shadow:0 18px 40px rgba(37,95,146,.22)!important}.flw-style-soft{background:#f5f8fb!important;border:1px solid #d9e3eb!important;border-radius:14px!important;padding:14px!important}.flw-style-custom{background:var(--flw-custom-bg,inherit)!important;border-color:var(--flw-custom-border,currentColor)!important;border-style:solid!important;border-width:var(--flw-custom-border-width,1px)!important;border-radius:var(--flw-custom-radius,12px)!important;padding:var(--flw-custom-padding,14px)!important;box-shadow:var(--flw-custom-shadow,none)!important}";
  document.head.appendChild(style);
  setTimeout(function(){window.parent.postMessage({type:"flw-visual-ready",count:scan(false)},"*");},120);
}());
</script>
"""


def edit_preview_html(path: Path) -> bytes:
    text = read_text(path)
    bridge = VISUAL_EDIT_BRIDGE
    if re.search(r"</body\s*>", text, flags=re.IGNORECASE):
        text = re.sub(
            r"</body\s*>",
            lambda match: bridge + "\n" + match.group(0),
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        text += bridge
    return text.encode("utf-8")


def slug(value: str, limit: int = 70) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value or "").strip("-")
    return (cleaned[:limit].strip("-") or "package")


SCORM_JS = r"""(function () {
  var cfg = window.FLW_SCORM_CONFIG || {};
  var api = null;
  var initialized = false;
  var finished = false;
  var sessionStartedAt = Date.now();

  function findAPI(win) {
    var tries = 0;
    while (win && tries < 8) {
      if (win.API) return win.API;
      tries += 1;
      try {
        if (win.parent && win.parent !== win) {
          win = win.parent;
        } else {
          break;
        }
      } catch (err) {
        break;
      }
    }
    try {
      if (window.opener && window.opener.API) return window.opener.API;
    } catch (err) {}
    return null;
  }

  function call(name, value) {
    if (!api || typeof api[name] !== "function") return "";
    try {
      return value === undefined ? api[name]("") : api[name](value);
    } catch (err) {
      return "";
    }
  }

  function getValue(key) {
    if (!initialized) return "";
    try {
      return api.LMSGetValue(String(key)) || "";
    } catch (err) {
      return "";
    }
  }

  function setValue(key, value) {
    if (!initialized) return false;
    try {
      return api.LMSSetValue(key, String(value)) === "true";
    } catch (err) {
      return false;
    }
  }

  function scormTime(ms) {
    var totalSeconds = Math.max(0, Math.floor(ms / 1000));
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;
    function pad(value) { return value < 10 ? "0" + value : String(value); }
    return pad(hours) + ":" + pad(minutes) + ":" + pad(seconds);
  }

  function parseSuspendData(raw) {
    if (!raw) return {};
    try {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return parsed;
    } catch (err) {}
    return {};
  }

  function suspendPayload(componentId) {
    return JSON.stringify({
      schemaVersion: 1,
      lastComponentId: String(componentId || cfg.componentId || "")
    });
  }

  function recordComponent(componentId) {
    if (!initialize()) return false;
    var stableId = String(componentId || cfg.componentId || "").trim();
    if (!stableId) return false;
    setValue("cmi.core.lesson_location", stableId);
    setValue("cmi.suspend_data", suspendPayload(stableId));
    commit();
    return true;
  }

  function recordSessionTime() {
    if (!initialized) return false;
    setValue("cmi.core.session_time", scormTime(Date.now() - sessionStartedAt));
    return true;
  }

  function commit() {
    if (!initialized) return false;
    recordSessionTime();
    return call("LMSCommit", "") === "true";
  }

  function initialize() {
    if (window.FLW_SKIP_SCORM_INIT) return false;
    if (initialized) return true;
    api = findAPI(window);
    if (!api) return false;
    initialized = call("LMSInitialize", "") === "true";
    if (initialized) {
      var existingStatus = getValue("cmi.core.lesson_status");
      if (!existingStatus || existingStatus === "not attempted") {
        setValue("cmi.core.lesson_status", cfg.statusOnLaunch || "incomplete");
      }
      if (cfg.scoreOnLaunch !== undefined) setValue("cmi.core.score.raw", cfg.scoreOnLaunch);
      if (cfg.componentId) recordComponent(cfg.componentId);
      commit();
    }
    return initialized;
  }

  function complete(score) {
    if (!initialize()) return false;
    var raw = score === undefined ? (cfg.scoreOnComplete || 100) : score;
    setValue("cmi.core.score.raw", raw);
    setValue("cmi.core.lesson_status", cfg.completeStatus || "completed");
    commit();
    return true;
  }

  function finish() {
    if (finished) return;
    if (initialized) {
      recordSessionTime();
      commit();
      call("LMSFinish", "");
    }
    finished = true;
  }

  window.FLWScormInitialize = initialize;
  window.FLWScormGetValue = getValue;
  window.FLWScormSetValue = setValue;
  window.FLWScormCommit = commit;
  window.FLWScormComplete = complete;
  window.FLWScormRecordComponent = recordComponent;
  window.FLWScormReadSuspendData = function () {
    if (!initialize()) return {};
    return parseSuspendData(getValue("cmi.suspend_data"));
  };
  window.FLWScormFinish = finish;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }

  window.addEventListener("load", function () {
    window.setTimeout(function () {
      initialize();
      if (cfg.autocomplete !== false) complete(cfg.scoreOnComplete || 100);
    }, cfg.completeAfterMs || 1500);
  });
  window.addEventListener("beforeunload", finish);
}());
"""


def inject_scorm_script(index_path: Path, config: dict) -> bool:
    text = read_text(index_path)
    script_path = "assets/scorm/scorm_api.js"
    if script_path in text:
        return False
    config_json = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
    snippet = f'\n<script>window.FLW_SCORM_CONFIG={config_json};</script>\n<script src="{script_path}"></script>\n'
    if re.search(r"</body\s*>", text, flags=re.IGNORECASE):
        text = re.sub(r"</body\s*>", snippet + "</body>", text, count=1, flags=re.IGNORECASE)
    else:
        text += snippet
    write_text(index_path, text)
    return True


FLW_NAVIGATOR_VERSION = 10

FLW_NAVIGATOR_CSS = r"""@view-transition {
  navigation: auto;
}
@keyframes flw-nav-page-reveal {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes flw-nav-page-leave {
  from { opacity: 1; }
  to { opacity: .82; }
}
::view-transition-old(root) {
  animation: 90ms ease-in both flw-nav-page-leave;
}
::view-transition-new(root) {
  animation: 140ms ease-out both flw-nav-page-reveal;
}
html.flw-nav-booting body {
  opacity: 0 !important;
}
html.flw-nav-ready body {
  animation: 140ms ease-out both flw-nav-page-reveal;
}
html.flw-nav-leaving body {
  pointer-events: none !important;
  animation: 80ms ease-in both flw-nav-page-leave;
}
#flw-unit-navigator {
  display: block !important;
  position: sticky;
  top: 0;
  z-index: 9998;
  box-sizing: border-box;
  width: min(1120px, calc(100% - 16px));
  max-width: none !important;
  height: auto !important;
  min-height: 0 !important;
  margin: 6px auto 8px;
  padding: 6px;
  overflow: visible !important;
  float: none !important;
  align-items: initial !important;
  gap: normal !important;
  border: 1px solid rgba(37, 95, 146, .18);
  border-radius: 12px;
  background: rgba(250, 253, 255, .98);
  box-shadow: 0 8px 22px rgba(26, 51, 75, .12);
  color: #14314d;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#flw-unit-navigator * {
  box-sizing: border-box;
}
#flw-unit-navigator .flw-nav-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  gap: 6px;
  align-items: center;
}
#flw-unit-navigator .flw-nav-current {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 36px;
  padding: 0 6px;
  text-align: left;
}
#flw-unit-navigator .flw-nav-progress {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: 999px;
  background: #eaf4fc;
  color: #255f92;
  font-size: 11px;
  font-weight: 750;
  white-space: nowrap;
}
#flw-unit-navigator .flw-nav-title {
  display: inline-block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 750;
  font-size: 14px;
}
#flw-unit-navigator button,
#flw-unit-navigator summary {
  border-radius: 999px;
  border: 1px solid #c9d9e7;
  background: #fff;
  color: #173653;
  cursor: pointer;
  font: inherit;
}
#flw-unit-navigator button {
  min-height: 36px;
  padding: 6px 10px;
}
#flw-unit-navigator button:hover,
#flw-unit-navigator summary:hover {
  border-color: #255f92;
  background: #f3f8fd;
}
#flw-unit-navigator button:focus-visible,
#flw-unit-navigator summary:focus-visible {
  outline: 3px solid rgba(37, 95, 146, .35);
  outline-offset: 2px;
}
#flw-unit-navigator button:disabled,
#flw-unit-navigator button[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: .55;
}
#flw-unit-navigator details {
  position: static;
  margin: 0;
}
#flw-unit-navigator summary {
  display: flex;
  min-height: 36px;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  list-style: none;
  white-space: nowrap;
}
#flw-unit-navigator summary::-webkit-details-marker {
  display: none;
}
#flw-unit-navigator details[open] summary {
  border-color: #255f92;
  background: #eaf4fc;
}
#flw-unit-navigator .flw-nav-chevron {
  display: inline-block;
  font-size: 10px;
  transition: transform .15s ease;
}
#flw-unit-navigator details[open] .flw-nav-chevron {
  transform: rotate(180deg);
}
#flw-unit-navigator .flw-nav-panel {
  position: absolute;
  top: calc(100% + 5px);
  right: 0;
  left: 0;
  z-index: 2;
  max-height: min(62vh, 420px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
  border: 1px solid #c9d9e7;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 16px 38px rgba(26, 51, 75, .2);
}
#flw-unit-navigator ol {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
#flw-unit-navigator .flw-nav-item {
  width: 100%;
  justify-content: space-between;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  border-radius: 12px;
  text-align: left;
}
#flw-unit-navigator .flw-nav-item[aria-current="page"] {
  border-color: #255f92;
  background: #eaf4fc;
  font-weight: 750;
}
#flw-unit-navigator .flw-nav-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
#flw-unit-navigator .flw-nav-status {
  flex: 0 0 auto;
  color: #496477;
  font-size: 12px;
}
#flw-unit-navigator .flw-nav-message {
  min-height: 0;
  margin: 0;
  color: #6f4a00;
  font-size: 13px;
}
#flw-unit-navigator .flw-nav-message:not(:empty) {
  margin-top: 8px;
  padding: 7px 9px;
  border-radius: 8px;
  background: #fff6df;
}
@media (max-width: 620px) {
  #flw-unit-navigator {
    width: calc(100% - 8px);
    margin: 4px auto 6px;
    padding: 4px;
  }
  #flw-unit-navigator .flw-nav-row {
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    gap: 4px;
  }
  #flw-unit-navigator button,
  #flw-unit-navigator summary {
    min-width: 40px;
    min-height: 40px;
    justify-content: center;
    padding: 6px;
  }
  #flw-unit-navigator .flw-nav-current {
    min-height: 40px;
    gap: 6px;
    padding: 0 2px;
  }
  #flw-unit-navigator .flw-nav-button-label,
  #flw-unit-navigator .flw-nav-lessons-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }
  #flw-unit-navigator .flw-nav-progress {
    padding: 2px 5px;
  }
  #flw-unit-navigator ol {
    grid-template-columns: 1fr;
  }
}
@media (prefers-reduced-motion: reduce) {
  ::view-transition-old(root),
  ::view-transition-new(root),
  html.flw-nav-ready body,
  html.flw-nav-leaving body {
    animation-duration: .001ms !important;
  }
}
"""

FLW_NAVIGATOR_JS = r"""(function () {
  var documentRoot = document.documentElement;
  var revealSafetyTimer = 0;
  var transitionBackgroundKey = "";

  function revealDocument() {
    window.clearTimeout(revealSafetyTimer);
    documentRoot.classList.remove("flw-nav-booting", "flw-nav-leaving");
    documentRoot.classList.add("flw-nav-ready");
    window.setTimeout(function () {
      documentRoot.classList.remove("flw-nav-ready");
      documentRoot.style.removeProperty("background-color");
      if (transitionBackgroundKey) {
        try { window.sessionStorage.removeItem(transitionBackgroundKey); } catch (err) {}
      }
    }, 180);
  }

  documentRoot.classList.add("flw-nav-booting");
  revealSafetyTimer = window.setTimeout(revealDocument, 1600);

  var configNode = document.getElementById("flw-unit-navigator-config");
  if (!configNode) {
    revealDocument();
    return;
  }
  var cfg = {};
  try {
    cfg = JSON.parse(configNode.textContent || "{}");
  } catch (err) {
    revealDocument();
    return;
  }
  var components = Array.isArray(cfg.components) ? cfg.components : [];
  if (!components.length) {
    revealDocument();
    return;
  }
  var currentId = cfg.currentComponentId || "";
  var navState = {};
  var storageKeyBase = "flw:navigator:" + (cfg.packageIdentifier || cfg.unitId || "unit");
  transitionBackgroundKey = storageKeyBase + ":transition-background";
  try {
    var storedTransitionBackground = window.sessionStorage.getItem(transitionBackgroundKey);
    if (storedTransitionBackground) documentRoot.style.backgroundColor = storedTransitionBackground;
  } catch (err) {}

  function escapeRegExp(value) {
    return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function safeWindow(candidate) {
    try {
      return candidate && candidate.document ? candidate : null;
    } catch (err) {
      return null;
    }
  }

  function frameWindows() {
    var wins = [window];
    try {
      if (window.parent && window.parent !== window) wins.push(window.parent);
    } catch (err) {}
    try {
      if (window.top && window.top !== window.parent && window.top !== window) wins.push(window.top);
    } catch (err) {}
    return wins.filter(safeWindow);
  }

  function installFramedImageModalCentering() {
    var frame = null;
    var parentWindow = null;
    try {
      if (window.parent === window || !window.frameElement) return;
      frame = window.frameElement;
      parentWindow = window.parent;
      void parentWindow.document;
    } catch (err) {
      return;
    }

    var updateTimer = 0;
    var scrollLock = null;

    function savedInlineStyle(element, property) {
      return {
        element: element,
        property: property,
        value: element.style.getPropertyValue(property),
        priority: element.style.getPropertyPriority(property)
      };
    }

    function restoreInlineStyle(record) {
      if (record.value) {
        record.element.style.setProperty(record.property, record.value, record.priority || "");
      } else {
        record.element.style.removeProperty(record.property);
      }
    }

    function setImageViewerScrollLock(locked) {
      if (locked && !scrollLock) {
        var records = [];
        [document.documentElement, document.body, parentWindow.document.documentElement, parentWindow.document.body].forEach(function (element) {
          if (!element) return;
          ["overflow", "overscroll-behavior"].forEach(function (property) {
            records.push(savedInlineStyle(element, property));
          });
          element.style.setProperty("overflow", "hidden", "important");
          element.style.setProperty("overscroll-behavior", "none", "important");
        });
        scrollLock = {records: records};
        documentRoot.setAttribute("data-flw-image-viewer-open", "true");
      } else if (!locked && scrollLock) {
        scrollLock.records.forEach(restoreInlineStyle);
        scrollLock = null;
        documentRoot.removeAttribute("data-flw-image-viewer-open");
      }
    }

    function preventViewerScroll(event) {
      if (!scrollLock) return;
      event.preventDefault();
    }

    function preventViewerScrollKeys(event) {
      if (!scrollLock) return;
      var target = event.target;
      var tag = target && target.tagName ? target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select" || (target && target.isContentEditable)) return;
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].indexOf(event.key) >= 0) {
        event.preventDefault();
      }
    }
    function unobstructedParentViewport() {
      var width = Math.max(1, Number(parentWindow.innerWidth) || document.documentElement.clientWidth || window.innerWidth || 1);
      var height = Math.max(1, Number(parentWindow.innerHeight) || document.documentElement.clientHeight || window.innerHeight || 1);
      var bounds = {left: 0, top: 0, right: width, bottom: height};
      try {
        Array.prototype.forEach.call(parentWindow.document.querySelectorAll("body *"), function (element) {
          if (!element || element === frame || element.contains(frame)) return;
          var style = parentWindow.getComputedStyle(element);
          if (style.position !== "fixed" && style.position !== "sticky") return;
          if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return;
          var rect = element.getBoundingClientRect();
          if (rect.height <= 0 || rect.width < width * 0.5 || rect.height > height * 0.35) return;
          if (rect.left > width * 0.25 || rect.right < width * 0.75) return;
          if (rect.top <= bounds.top + 1 && rect.bottom > bounds.top && rect.bottom < height * 0.5) {
            bounds.top = Math.max(bounds.top, rect.bottom);
          }
          if (rect.bottom >= bounds.bottom - 1 && rect.top < bounds.bottom && rect.top > height * 0.5) {
            bounds.bottom = Math.min(bounds.bottom, rect.top);
          }
        });
      } catch (err) {}
      if (bounds.bottom <= bounds.top + 32) {
        bounds.top = 0;
        bounds.bottom = height;
      }
      return bounds;
    }

    function visibleFrameBounds() {
      var rect = frame.getBoundingClientRect();
      var viewport = unobstructedParentViewport();
      var visibleLeft = Math.max(viewport.left, rect.left);
      var visibleTop = Math.max(viewport.top, rect.top);
      var visibleRight = Math.min(viewport.right, rect.right);
      var visibleBottom = Math.min(viewport.bottom, rect.bottom);
      return {
        left: Math.max(0, visibleLeft - rect.left),
        top: Math.max(0, visibleTop - rect.top),
        width: Math.max(1, visibleRight - visibleLeft),
        height: Math.max(1, visibleBottom - visibleTop),
        viewportTop: viewport.top,
        viewportBottom: viewport.bottom
      };
    }

    function modalIsVisible(modal) {
      if (!modal || modal.hidden) return false;
      var style = window.getComputedStyle(modal);
      return style.display !== "none" && style.visibility !== "hidden";
    }

    function centerVisibleImageModals() {
      var selector = ".image-modal, #imageModal, .image-lightbox, .lightbox, [class*='image-modal'], [class*='image-lightbox']";
      var visibleModals = Array.prototype.filter.call(document.querySelectorAll(selector), modalIsVisible);
      setImageViewerScrollLock(visibleModals.length > 0);
      if (!visibleModals.length) return;
      var bounds = visibleFrameBounds();
      visibleModals.forEach(function (modal) {
        modal.setAttribute("data-flw-visible-frame-centered", "true");
        modal.setAttribute("data-flw-viewer-vertical-lift", "0");
        modal.setAttribute("data-flw-viewer-viewport-top", String(Math.round(bounds.viewportTop)));
        modal.setAttribute("data-flw-viewer-viewport-bottom", String(Math.round(bounds.viewportBottom)));
        modal.setAttribute("role", modal.getAttribute("role") || "dialog");
        modal.setAttribute("aria-modal", "true");
        modal.style.setProperty("position", "fixed", "important");
        modal.style.setProperty("inset", "auto", "important");
        modal.style.setProperty("left", bounds.left + "px", "important");
        modal.style.setProperty("top", bounds.top + "px", "important");
        modal.style.setProperty("width", bounds.width + "px", "important");
        modal.style.setProperty("height", bounds.height + "px", "important");
        modal.style.setProperty("align-items", "center", "important");
        modal.style.setProperty("justify-items", "center", "important");
        modal.style.setProperty("align-content", "center", "important");
        modal.style.setProperty("justify-content", "center", "important");
        modal.style.setProperty("z-index", "2147483000", "important");
        modal.style.setProperty("overflow", "hidden", "important");
        modal.style.setProperty("overscroll-behavior", "none", "important");
        modal.style.setProperty("padding", "16px", "important");
        modal.style.setProperty("box-sizing", "border-box", "important");
        var mediaMaxWidth = Math.max(1, Math.floor(bounds.width - 32));
        var mediaMaxHeight = Math.max(1, Math.floor(bounds.height - 32));
        modal.querySelectorAll("img, video").forEach(function (media) {
          var ancestor = media.parentElement;
          while (ancestor && ancestor !== modal) {
            ancestor.style.setProperty("position", "static", "important");
            ancestor.style.setProperty("transform", "none", "important");
            ancestor.style.setProperty("overflow", "visible", "important");
            ancestor = ancestor.parentElement;
          }
          media.style.setProperty("position", "absolute", "important");
          media.style.setProperty("left", "50%", "important");
          media.style.setProperty("top", "50%", "important");
          media.style.setProperty("transform", "translate(-50%, -50%)", "important");
          media.style.setProperty("width", "auto", "important");
          media.style.setProperty("height", "auto", "important");
          media.style.setProperty("max-width", mediaMaxWidth + "px", "important");
          media.style.setProperty("max-height", mediaMaxHeight + "px", "important");
          media.style.setProperty("object-fit", "contain", "important");
          media.style.setProperty("aspect-ratio", "auto", "important");
          media.style.setProperty("display", "block", "important");
          media.style.setProperty("margin", "0", "important");
          media.style.setProperty("box-sizing", "border-box", "important");
          media.style.setProperty("user-select", "none", "important");
        });
        modal.querySelectorAll(".modal-caption, figcaption, [data-modal-caption]").forEach(function (caption) {
          caption.style.setProperty("position", "absolute", "important");
          caption.style.setProperty("left", "50%", "important");
          caption.style.setProperty("bottom", "8px", "important");
          caption.style.setProperty("transform", "translateX(-50%)", "important");
          caption.style.setProperty("max-width", mediaMaxWidth + "px", "important");
          caption.style.setProperty("margin", "0", "important");
          caption.style.setProperty("padding", "4px 9px", "important");
          caption.style.setProperty("border-radius", "7px", "important");
          caption.style.setProperty("background", "rgba(7, 18, 13, .78)", "important");
          caption.style.setProperty("color", "#fff", "important");
          caption.style.setProperty("z-index", "2147483001", "important");
        });
        modal.querySelectorAll(".modal-close, .lightbox-close, [data-modal-close], [data-close], button[id*='close' i], button[aria-label*='close' i], button[aria-label='关闭']").forEach(function (button) {
          button.style.setProperty("position", "absolute", "important");
          button.style.setProperty("top", "12px", "important");
          button.style.setProperty("right", "12px", "important");
          button.style.setProperty("z-index", "2147483002", "important");
        });
      });
    }

    function scheduleModalCentering() {
      window.clearTimeout(updateTimer);
      updateTimer = window.setTimeout(centerVisibleImageModals, 0);
      window.setTimeout(centerVisibleImageModals, 60);
    }

    document.addEventListener("click", scheduleModalCentering, true);
    document.addEventListener("keydown", scheduleModalCentering, true);
    document.addEventListener("wheel", preventViewerScroll, {capture: true, passive: false});
    document.addEventListener("touchmove", preventViewerScroll, {capture: true, passive: false});
    document.addEventListener("keydown", preventViewerScrollKeys, true);
    window.addEventListener("resize", scheduleModalCentering, {passive: true});
    window.addEventListener("scroll", scheduleModalCentering, {passive: true});
    try {
      parentWindow.addEventListener("resize", scheduleModalCentering, {passive: true});
      parentWindow.addEventListener("scroll", scheduleModalCentering, true);
      parentWindow.addEventListener("wheel", preventViewerScroll, {capture: true, passive: false});
      parentWindow.addEventListener("touchmove", preventViewerScroll, {capture: true, passive: false});
      parentWindow.addEventListener("keydown", preventViewerScrollKeys, true);
    } catch (err) {}
    window.addEventListener("load", scheduleModalCentering);
    window.addEventListener("pagehide", function () { setImageViewerScrollLock(false); });
  }

  installFramedImageModalCentering();

  function hasScormApi() {
    var wins = frameWindows();
    for (var i = 0; i < wins.length; i += 1) {
      try {
        if (wins[i].API) return true;
      } catch (err) {}
    }
    return false;
  }

  function readStoredState() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(currentStorageKey()) || "{}");
      if (parsed && typeof parsed === "object") navState = parsed;
    } catch (err) {
      navState = {};
    }
    if (!navState.completed || typeof navState.completed !== "object") navState.completed = {};
  }

  function writeStoredState() {
    try {
      window.localStorage.setItem(currentStorageKey(), JSON.stringify(navState));
    } catch (err) {}
  }

  function componentById(componentId) {
    for (var i = 0; i < components.length; i += 1) {
      if (components[i].componentId === componentId) return components[i];
    }
    return null;
  }

  function readableName(component) {
    return component.label || component.title || "Lesson";
  }

  function isLocked(component) {
    return component.locked === true || String(component.availability || "").toLowerCase() === "locked";
  }

  function componentStatus(component) {
    if (isLocked(component)) return "Locked";
    if (navState.completed && navState.completed[component.componentId]) return "Completed";
    if (component.componentId === currentId) return "Current";
    var raw = String(component.status || component.state || "").toLowerCase();
    if (raw === "completed" || raw === "passed") return "Completed";
    return "Available";
  }

  function statusSymbol(status) {
    if (status === "Completed") return "✓";
    if (status === "Current") return "●";
    if (status === "Locked") return "◇";
    return "○";
  }

  function currentIndex() {
    for (var i = 0; i < components.length; i += 1) {
      if (components[i].componentId === currentId) return i;
    }
    return 0;
  }

  function sameOriginDocument(win) {
    try {
      return win && win.document ? win.document : null;
    } catch (err) {
      return null;
    }
  }

  function decodeEntities(value) {
    var box = document.createElement("textarea");
    box.innerHTML = String(value || "");
    return box.value;
  }

  function scriptVariants(text) {
    var raw = String(text || "");
    var decoded = decodeEntities(raw);
    return [
      raw,
      raw.replace(/\\"/g, '"').replace(/\\\//g, "/"),
      raw.replace(/\\\\/g, "\\").replace(/\\"/g, '"').replace(/\\\//g, "/"),
      decoded,
      decoded.replace(/\\"/g, '"').replace(/\\\//g, "/"),
      decoded.replace(/\\\\/g, "\\").replace(/\\"/g, '"').replace(/\\\//g, "/")
    ];
  }

  function decodeMoodleUrl(value) {
    return String(value || "")
      .replace(/\\\//g, "/")
      .replace(/\\"/g, '"')
      .replace(/&amp;/g, "&");
  }

  function extractObjectAt(text, openIndex) {
    var depth = 0;
    var inString = false;
    var escaped = false;
    for (var i = openIndex; i < text.length; i += 1) {
      var ch = text.charAt(i);
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (ch === "\\") {
          escaped = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }
      if (ch === '"') {
        inString = true;
      } else if (ch === "{") {
        depth += 1;
      } else if (ch === "}") {
        depth -= 1;
        if (depth === 0) return text.slice(openIndex, i + 1);
      }
    }
    return "";
  }

  function latestMoodleObjectStart(text, beforeIndex) {
    var pattern = /"([0-9]+)"\s*:\s*\{/g;
    var latest = null;
    var match = null;
    var prefix = text.slice(0, beforeIndex);
    while ((match = pattern.exec(prefix)) !== null) {
      latest = {scoid: match[1], openIndex: match.index + match[0].lastIndexOf("{")};
    }
    return latest;
  }

  function explicitMoodleMap(component) {
    var maps = [cfg.moodleScoMap];
    frameWindows().forEach(function (win) {
      try { maps.push(win.FLW_MOODLE_SCO_MAP); } catch (err) {}
    });
    for (var i = 0; i < maps.length; i += 1) {
      var map = maps[i];
      if (!map || typeof map !== "object") continue;
      var value = map[component.scoIdentifier] || map[component.componentId];
      if (!value) continue;
      if (typeof value === "object") {
        return {scoid: value.scoid || value.id || "", url: value.url || ""};
      }
      return {scoid: value, url: ""};
    }
    return null;
  }

  function adlNavFromMoodleScripts(component) {
    var identifier = component.scoIdentifier || "";
    if (!identifier) return null;
    var idPattern = escapeRegExp(identifier);
    var identifierPattern = new RegExp('"identifier"\\s*:\\s*"' + idPattern + '"', "g");
    var entryIdentifierPattern = new RegExp('"identifier"\\s*:\\s*"' + idPattern + '"');
    var docs = [];
    frameWindows().forEach(function (win) {
      var doc = sameOriginDocument(win);
      if (doc && docs.indexOf(doc) === -1) docs.push(doc);
    });
    for (var d = 0; d < docs.length; d += 1) {
      var scripts = docs[d].getElementsByTagName("script");
      for (var s = 0; s < scripts.length; s += 1) {
        var rawText = scripts[s].textContent || "";
        if (rawText.indexOf(identifier) === -1 && rawText.indexOf(identifier.replace(/_/g, "\\\\_")) === -1) continue;
        var variants = scriptVariants(rawText);
        for (var v = 0; v < variants.length; v += 1) {
          var text = variants[v];
          if (text.indexOf(identifier) === -1) continue;
          identifierPattern.lastIndex = 0;
          var idMatch = null;
          while ((idMatch = identifierPattern.exec(text)) !== null) {
            var start = latestMoodleObjectStart(text, idMatch.index);
            if (!start) continue;
            var block = extractObjectAt(text, start.openIndex);
            if (!block || !entryIdentifierPattern.test(block)) continue;
            var urlMatch = /"url"\s*:\s*"([^"]+)"/.exec(block);
            return {scoid: start.scoid, url: urlMatch ? decodeMoodleUrl(urlMatch[1]) : ""};
          }
        }
      }
    }
    return null;
  }

  function moodleWwwroot() {
    var wins = frameWindows();
    for (var i = 0; i < wins.length; i += 1) {
      try {
        if (wins[i].M && wins[i].M.cfg && wins[i].M.cfg.wwwroot) {
          return String(wins[i].M.cfg.wwwroot).replace(/\/$/, "");
        }
      } catch (err) {}
    }
    try {
      return window.parent.location.origin;
    } catch (err) {
      return "";
    }
  }

  function parentUrl() {
    var wins = frameWindows();
    for (var i = 0; i < wins.length; i += 1) {
      try {
        if (String(wins[i].location.href).indexOf("/mod/scorm/player.php") !== -1) {
          return new URL(wins[i].location.href);
        }
      } catch (err) {}
    }
    return null;
  }

  function currentStorageKey() {
    var parent = parentUrl();
    if (!parent) return storageKeyBase;
    var scormId = parent.searchParams.get("a") || "";
    var attempt = parent.searchParams.get("attempt") || "1";
    try {
      var frameSrc = window.frameElement ? window.frameElement.getAttribute("src") : "";
      if (frameSrc) {
        var frameUrl = new URL(frameSrc, parent.origin);
        scormId = scormId || frameUrl.searchParams.get("a") || "";
        attempt = parent.searchParams.get("attempt") || frameUrl.searchParams.get("attempt") || attempt || "1";
      }
    } catch (err) {}
    if (!scormId) return storageKeyBase;
    return storageKeyBase + ":moodle:" + scormId + ":attempt:" + attempt;
  }

  function isMoodleActivityAutoLaunch() {
    var parent = parentUrl();
    if (!parent) return false;
    return !parent.searchParams.get("cm") && !!parent.searchParams.get("a") && !!parent.searchParams.get("currentorg");
  }

  function hideMoodleNativeScormToc() {
    var selectors = [
      "#tochead",
      "#scorm_toc",
      "#scorm_tree",
      ".scorm_toc",
      ".scorm_tree",
      "#scorm_navpanel",
      "select[name='scoid']"
    ];
    frameWindows().forEach(function (win) {
      var doc = sameOriginDocument(win);
      if (!doc) return;
      selectors.forEach(function (selector) {
        doc.querySelectorAll(selector).forEach(function (node) {
          node.setAttribute("aria-hidden", "true");
          node.style.display = "none";
          node.style.visibility = "hidden";
          node.style.width = "0";
          node.style.height = "0";
          node.style.overflow = "hidden";
        });
      });
    });
  }

  function playerUrl(component) {
    var resolved = explicitMoodleMap(component) || adlNavFromMoodleScripts(component);
    if (!resolved || !resolved.scoid) return "";
    var root = moodleWwwroot();
    if (resolved.url && /(?:^|&)scoid=/.test(resolved.url)) {
      return root + "/mod/scorm/player.php?" + resolved.url.replace(/^\?/, "");
    }
    var parent = parentUrl();
    if (!parent && !root) return "";
    var url = new URL((root || parent.origin) + "/mod/scorm/player.php");
    if (parent) {
      ["cm", "a", "currentorg", "mode", "attempt"].forEach(function (name) {
        var value = parent.searchParams.get(name);
        if (value) url.searchParams.set(name, value);
      });
    }
    url.searchParams.set("scoid", String(resolved.scoid));
    return url.toString();
  }

  function localHref(component) {
    var href = component.localHref || component.launchFile || "";
    if (!href) return "";
    try {
      // Resolve against the actual SCO document URL, not document.baseURI.
      // Exported SCO pages use <base href="../"> for shared unit assets; allowing
      // that base element to resolve navigator links incorrectly drops "scos/".
      return new URL(href, window.location.href).href;
    } catch (err) {
      return href;
    }
  }

  function prefetchLocalComponent(component) {
    if (!component || hasScormApi()) return;
    var href = localHref(component);
    if (!href || href === window.location.href) return;
    var existing = document.querySelector('link[data-flw-prefetch="' + String(component.componentId || "").replace(/"/g, "") + '"]');
    if (existing) return;
    var link = document.createElement("link");
    link.rel = "prefetch";
    link.href = href;
    link.setAttribute("data-flw-prefetch", component.componentId || href);
    document.head.appendChild(link);
  }

  function navigateLocal(href) {
    if (!href) return;
    var nav = document.getElementById("flw-unit-navigator");
    if (nav) nav.setAttribute("aria-busy", "true");
    try {
      var bodyBackground = window.getComputedStyle(document.body).backgroundColor;
      var rootBackground = window.getComputedStyle(documentRoot).backgroundColor;
      var transitionBackground = bodyBackground && bodyBackground !== "rgba(0, 0, 0, 0)" ? bodyBackground : rootBackground;
      if (transitionBackground && transitionBackground !== "rgba(0, 0, 0, 0)") {
        documentRoot.style.backgroundColor = transitionBackground;
        window.sessionStorage.setItem(transitionBackgroundKey, transitionBackground);
      }
    } catch (err) {}
    documentRoot.classList.remove("flw-nav-ready", "flw-nav-booting");
    documentRoot.classList.add("flw-nav-leaving");
    var reducedMotion = false;
    try {
      reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (err) {}
    window.setTimeout(function () { window.location.href = href; }, reducedMotion ? 0 : 70);
  }

  function setMessage(text) {
    var message = document.querySelector("#flw-unit-navigator .flw-nav-message");
    if (message) message.textContent = text || "";
  }

  function recordCurrentComponent() {
    navState.lastComponentId = currentId;
    writeStoredState();
    if (typeof window.FLWScormRecordComponent === "function") {
      window.FLWScormRecordComponent(currentId);
    }
  }

  function redirectToStoredResumeComponent() {
    if (!isMoodleActivityAutoLaunch()) return false;
    var lastComponentId = navState.lastComponentId || "";
    if (!lastComponentId || lastComponentId === currentId) return false;
    var component = componentById(lastComponentId);
    if (!component || isLocked(component)) return false;
    var target = playerUrl(component);
    if (!target) return false;
    window.FLW_SKIP_SCORM_INIT = true;
    try {
      window.top.location.replace(target);
    } catch (err) {
      try {
        window.top.location.href = target;
      } catch (fallback) {
        window.location.href = target;
      }
    }
    return true;
  }

  function finishForNavigation() {
    try {
      if (typeof window.FLWScormCommit === "function") window.FLWScormCommit();
      if (typeof window.FLWScormFinish === "function") window.FLWScormFinish();
    } catch (err) {}
  }

  function launch(component) {
    if (!component || component.componentId === currentId) return;
    if (isLocked(component)) {
      setMessage(readableName(component) + " is locked.");
      return;
    }
    recordCurrentComponent();
    var target = playerUrl(component);
    if (target) {
      finishForNavigation();
      try {
        window.top.location.href = target;
      } catch (err) {
        window.location.href = target;
      }
      return;
    }
    if (!hasScormApi()) {
      var href = localHref(component);
      if (href) navigateLocal(href);
      return;
    }
    setMessage("This lesson link is not ready yet. Please reload the activity.");
  }

  function markCurrentCompletionFromApi() {
    var status = "";
    try {
      if (typeof window.FLWScormGetValue === "function") {
        status = String(window.FLWScormGetValue("cmi.core.lesson_status") || "").toLowerCase();
      }
    } catch (err) {}
    if (status === "completed" || status === "passed") {
      navState.completed[currentId] = true;
      writeStoredState();
      refreshStatuses();
    }
  }

  function refreshStatuses() {
    document.querySelectorAll("#flw-unit-navigator [data-flw-component-id]").forEach(function (button) {
      var component = components.find(function (item) { return item.componentId === button.getAttribute("data-flw-component-id"); });
      if (!component) return;
      var status = componentStatus(component);
      var statusNode = button.querySelector(".flw-nav-status");
      if (statusNode) statusNode.textContent = statusSymbol(status) + " " + status;
      if (component.componentId === currentId) {
        button.setAttribute("aria-current", "page");
      }
    });
  }

  function render() {
    readStoredState();
    hideMoodleNativeScormToc();
    if (redirectToStoredResumeComponent()) return;
    var index = currentIndex();
    var current = components[index] || components[0];
    currentId = current.componentId || currentId;
    var nav = document.createElement("nav");
    nav.id = "flw-unit-navigator";
    nav.setAttribute("aria-label", "Unit lesson navigation");

    var row = document.createElement("div");
    row.className = "flw-nav-row";

    var prev = document.createElement("button");
    prev.type = "button";
    prev.className = "flw-nav-prev";
    prev.innerHTML = '<span aria-hidden="true">←</span><span class="flw-nav-button-label">Previous</span>';
    var previousComponent = index > 0 ? components[index - 1] : null;
    prev.disabled = !previousComponent || isLocked(previousComponent);
    if (!previousComponent) {
      prev.setAttribute("aria-label", "No previous lesson");
      prev.title = "No previous lesson";
    } else if (isLocked(previousComponent)) {
      prev.setAttribute("aria-label", "Previous lesson is locked: " + readableName(previousComponent));
      prev.title = "Locked: " + readableName(previousComponent);
    } else {
      prev.setAttribute("aria-label", "Previous: " + readableName(previousComponent));
      prev.title = "Previous: " + readableName(previousComponent);
    }
    prev.addEventListener("click", function () { launch(components[index - 1]); });

    var center = document.createElement("div");
    center.className = "flw-nav-current";
    center.setAttribute("aria-label", "Current lesson: " + readableName(current) + ", " + (index + 1) + " of " + components.length);
    center.innerHTML = '<span class="flw-nav-progress"></span><span class="flw-nav-title"></span>';
    center.querySelector(".flw-nav-progress").textContent = (index + 1) + " of " + components.length;
    center.querySelector(".flw-nav-title").textContent = readableName(current);
    center.querySelector(".flw-nav-title").title = readableName(current);

    var next = document.createElement("button");
    next.type = "button";
    next.className = "flw-nav-next";
    next.innerHTML = '<span class="flw-nav-button-label">Next</span><span aria-hidden="true">→</span>';
    var nextComponent = index < components.length - 1 ? components[index + 1] : null;
    next.disabled = !nextComponent || isLocked(nextComponent);
    if (!nextComponent) {
      next.setAttribute("aria-label", "No next lesson");
      next.title = "No next lesson";
    } else if (isLocked(nextComponent)) {
      next.setAttribute("aria-label", "Next lesson is locked: " + readableName(nextComponent));
      next.title = "Locked: " + readableName(nextComponent);
    } else {
      next.setAttribute("aria-label", "Next: " + readableName(nextComponent));
      next.title = "Next: " + readableName(nextComponent);
    }
    next.addEventListener("click", function () { launch(components[index + 1]); });

    row.appendChild(prev);
    row.appendChild(center);

    var details = document.createElement("details");
    details.className = "flw-nav-lessons";
    var summary = document.createElement("summary");
    summary.innerHTML = '<span aria-hidden="true">☰</span><span class="flw-nav-lessons-label">Lessons</span><span class="flw-nav-chevron" aria-hidden="true">▾</span>';
    summary.setAttribute("role", "button");
    summary.setAttribute("aria-label", "Open lesson list");
    summary.setAttribute("aria-controls", "flw-nav-lesson-panel");
    summary.setAttribute("aria-expanded", "false");
    summary.title = "Open lesson list";
    details.appendChild(summary);
    var panel = document.createElement("div");
    panel.id = "flw-nav-lesson-panel";
    panel.className = "flw-nav-panel";
    var list = document.createElement("ol");
    var currentListButton = null;
    components.forEach(function (component) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      var status = componentStatus(component);
      button.type = "button";
      button.className = "flw-nav-item";
      button.setAttribute("data-flw-component-id", component.componentId || "");
      button.innerHTML = '<span class="flw-nav-name"></span><span class="flw-nav-status"></span>';
      button.querySelector(".flw-nav-name").textContent = readableName(component);
      button.querySelector(".flw-nav-status").textContent = statusSymbol(status) + " " + status;
      if (component.componentId === currentId) {
        button.setAttribute("aria-current", "page");
        currentListButton = button;
      }
      if (isLocked(component)) button.setAttribute("aria-disabled", "true");
      button.addEventListener("click", function () {
        if (component.componentId === currentId) {
          details.removeAttribute("open");
          summary.focus();
          return;
        }
        launch(component);
      });
      button.addEventListener("pointerenter", function () { prefetchLocalComponent(component); }, {once: true});
      button.addEventListener("focus", function () { prefetchLocalComponent(component); }, {once: true});
      item.appendChild(button);
      list.appendChild(item);
    });
    panel.appendChild(list);
    var message = document.createElement("div");
    message.className = "flw-nav-message";
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");
    panel.appendChild(message);
    details.appendChild(panel);
    details.addEventListener("toggle", function () {
      var isOpen = details.hasAttribute("open");
      summary.setAttribute("aria-label", isOpen ? "Close lesson list" : "Open lesson list");
      summary.setAttribute("aria-expanded", isOpen ? "true" : "false");
      summary.title = isOpen ? "Close lesson list" : "Open lesson list";
      if (isOpen && currentListButton) {
        setTimeout(function () { currentListButton.scrollIntoView({block: "nearest", inline: "nearest"}); }, 0);
      }
    });

    row.appendChild(details);
    row.appendChild(next);
    nav.appendChild(row);

    document.addEventListener("click", function (event) {
      if (details.hasAttribute("open") && !nav.contains(event.target)) details.removeAttribute("open");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && details.hasAttribute("open")) {
        details.removeAttribute("open");
        summary.focus();
      }
    });

    document.body.insertBefore(nav, document.body.firstChild);
    prefetchLocalComponent(previousComponent);
    prefetchLocalComponent(nextComponent);
    recordCurrentComponent();
    setTimeout(markCurrentCompletionFromApi, 250);
    setTimeout(markCurrentCompletionFromApi, (cfg.completionPollMs || 1800));
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(revealDocument);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
}());"""


def replace_scorm_config_html(text: str, config: dict) -> str:
    config_json = json.dumps(config, ensure_ascii=True, separators=(",", ":"))
    pattern = re.compile(
        r"<script>\s*window\.FLW_SCORM_CONFIG\s*=\s*(\{.*?\})\s*;\s*</script>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet = f"<script>window.FLW_SCORM_CONFIG={config_json};</script>"
    if pattern.search(text):
        return pattern.sub(snippet, text, count=1)
    return inject_head_fragment(text, snippet, "window.FLW_SCORM_CONFIG")


def component_display_label(sco: dict) -> str:
    key = str(sco.get("componentKey") or "").upper()
    title = clean_display_text(str(sco.get("title") or ""))
    if key == "VOCAB":
        return "Vocabulary"
    if key == "WATCH":
        return "Watch"
    if key == "PROJECT":
        return "Project"
    if key == "RESULT":
        return "Result"
    if key == "UNIT":
        return "Unit"
    match = re.match(r"L0*(\d+)$", key)
    if match:
        return f"Lesson {int(match.group(1))}"
    if title:
        title = re.sub(r"^\s*Lesson\s+0*(\d+)\s*:.*$", lambda m: f"Lesson {int(m.group(1))}", title, flags=re.IGNORECASE)
        return title
    return "Lesson"


def navigator_local_href(target_launch_file: str, current_launch_file: str) -> str:
    target = target_launch_file.replace("\\", "/").lstrip("/")
    current = current_launch_file.replace("\\", "/").lstrip("/")
    current_dir = posixpath.dirname(current)
    return posixpath.relpath(target, current_dir or ".")


def flw_navigator_config(unit_identity: dict, package_title: str, scos: list[dict], current_sco: dict) -> dict:
    current_launch = current_sco.get("launchFile", "")
    components = []
    for order, sco in enumerate(scos, start=1):
        components.append(
            {
                "componentId": sco.get("componentId", ""),
                "componentKey": sco.get("componentKey", ""),
                "kind": sco.get("kind") or "section",
                "label": component_display_label(sco),
                "title": sco.get("title", ""),
                "scoIdentifier": sco.get("scoIdentifier", ""),
                "launchFile": sco.get("launchFile", ""),
                "localHref": navigator_local_href(sco.get("launchFile", ""), current_launch),
                "displayOrder": order,
                "availability": sco.get("availability") or "available",
                "locked": bool(sco.get("locked", False)),
                "status": sco.get("status") or "",
            }
        )
    return {
        "navigatorVersion": FLW_NAVIGATOR_VERSION,
        "packageIdentifier": unit_identity.get("scormManifestIdentifier", ""),
        "unitId": unit_identity.get("unitId", ""),
        "unitTitle": package_title,
        "currentComponentId": current_sco.get("componentId", ""),
        "currentScoIdentifier": current_sco.get("scoIdentifier", ""),
        "components": components,
        "resume": {
            "schemaVersion": 1,
            "storage": ["cmi.core.lesson_location", "cmi.suspend_data"],
            "lastComponentIdField": "lastComponentId",
        },
        "moodleLaunch": {
            "endpoint": "/mod/scorm/player.php",
            "requiresNumericScoid": True,
            "resolver": "Moodle adlnav stable identifier map",
        },
    }


def inject_flw_navigator_html(text: str, config: dict) -> str:
    marker = "flw-unit-navigator-config"
    if marker in text:
        return text
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    text = inject_head_fragment(text, f'<style id="flw-unit-navigator-style">\n{FLW_NAVIGATOR_CSS}\n</style>', "flw-unit-navigator-style")
    fragment = (
        f'<script id="{marker}" type="application/json">{html.escape(config_json, quote=False)}</script>\n'
        f'<script id="flw-unit-navigator-script">\n{FLW_NAVIGATOR_JS}\n</script>'
    )
    if re.search(r"</body\s*>", text, flags=re.IGNORECASE):
        return re.sub(r"</body\s*>", lambda match: fragment + "\n" + match.group(0), text, count=1, flags=re.IGNORECASE)
    return text + "\n" + fragment


def ensure_navigator_before_scorm_runtime(text: str) -> str:
    nav_start = text.find('<script id="flw-unit-navigator-config"')
    scorm_start = text.find("<script>window.FLW_SCORM_CONFIG=")
    if nav_start < 0 or scorm_start < 0 or nav_start < scorm_start:
        return text
    nav_script_start = text.find('<script id="flw-unit-navigator-script"', nav_start)
    if nav_script_start < 0:
        return text
    nav_end = text.find("</script>", nav_script_start)
    if nav_end < 0:
        return text
    nav_end += len("</script>")
    fragment = text[nav_start:nav_end]
    text = text[:nav_start] + text[nav_end:]
    scorm_start = text.find("<script>window.FLW_SCORM_CONFIG=")
    if scorm_start < 0:
        return text + "\n" + fragment
    return text[:scorm_start] + fragment + "\n" + text[scorm_start:]


def inject_flw_navigator_file(index_path: Path, scorm_config: dict, navigator_config: dict) -> bool:
    text = read_text(index_path)
    current_scorm_config = {
        **scorm_config,
        "componentId": navigator_config.get("currentComponentId", ""),
        "scoIdentifier": navigator_config.get("currentScoIdentifier", ""),
        "unitId": navigator_config.get("unitId", ""),
        "packageIdentifier": navigator_config.get("packageIdentifier", ""),
    }
    before = text
    text = replace_scorm_config_html(text, current_scorm_config)
    text = inject_flw_navigator_html(text, navigator_config)
    text = ensure_navigator_before_scorm_runtime(text)
    if text == before:
        return False
    write_text(index_path, text)
    return True


def inject_lesson_focus_script(index_path: Path) -> bool:
    text = read_text(index_path)
    marker = "FLW_SCORM_LESSON_FOCUS"
    if marker in text:
        return False
    snippet = r"""
<script>
/* FLW_SCORM_LESSON_FOCUS */
(function () {
  function focusLesson() {
    var params = new URLSearchParams(window.location.search || "");
    var id = params.get("flw_lesson") || (window.location.hash || "").replace(/^#/, "");
    var target;
    if (!id) return;
    try {
      target = document.getElementById(id);
    } catch (err) {
      target = null;
    }
    if (!target) return;
    if (target.tagName && target.tagName.toLowerCase() === "details") target.open = true;
    target.scrollIntoView({block: "start"});
  }
  function delayedFocus(delay) {
    window.setTimeout(focusLesson, delay);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { delayedFocus(150); });
  } else {
    delayedFocus(150);
  }
  window.addEventListener("load", function () { delayedFocus(300); });
}());
</script>
"""
    if re.search(r"</body\s*>", text, flags=re.IGNORECASE):
        text = re.sub(r"</body\s*>", snippet + "\n</body>", text, count=1, flags=re.IGNORECASE)
    else:
        text += snippet
    write_text(index_path, text)
    return True


def should_skip_export(path: Path, unit_path: Path, include_source_data: bool, include_tools: bool) -> bool:
    rel_parts = path.relative_to(unit_path).parts
    if not rel_parts:
        return False
    if any(part in SKIP_EXPORT_DIRS for part in rel_parts):
        return True
    if not include_source_data and rel_parts[0] == "source_data":
        return True
    if not include_tools and rel_parts[0] == "tools":
        return True
    if path.name == "imsmanifest.xml":
        return True
    if path.suffix.lower() in {".pyc", ".zip"}:
        return True
    return False


def copy_for_export(unit_path: Path, stage: Path, include_source_data: bool, include_tools: bool) -> list[str]:
    copied = []
    for source in unit_path.rglob("*"):
        if source.is_dir():
            continue
        if should_skip_export(source, unit_path, include_source_data, include_tools):
            continue
        rel = source.relative_to(unit_path)
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        ensure_writable(target)
        copied.append(rel.as_posix())
    return sorted(copied)


def manifest_identifier(value: str, prefix: str = "ID") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._-")
    return f"{prefix}_{cleaned or uuid.uuid4().hex[:8]}"


def flw_scorm_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").upper()).strip("_")
    return cleaned or "FLW_UNKNOWN"


def flw_component_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").upper()).strip("_")
    return cleaned or "COMPONENT"


def lesson_component_key_from_source(source_id: str, fallback_number: int | None = None) -> tuple[str, str]:
    raw = str(source_id or "").strip()
    for pattern in (
        r"^l(?:esson)?[_\-\s]?0*(\d{1,3})$",
        r"^lesson[_\-\s]?0*(\d{1,3})$",
        r"^unit[_\-\s]?lesson[_\-\s]?0*(\d{1,3})$",
    ):
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            return f"L{int(match.group(1)):02d}", "source_lesson_id"
    if raw:
        return f"LESSON_{flw_component_segment(raw)}", "source_lesson_id"
    if fallback_number:
        return f"L{fallback_number:02d}", "generated_position_fallback"
    return "LESSON_UNRESOLVED", "missing_source_lesson_id"


def section_component_key(section_id: str, kind: str = "section", number: int | None = None) -> tuple[str, str]:
    if kind == "lesson":
        return lesson_component_key_from_source(section_id, number)
    raw = str(section_id or "").strip()
    normalized = re.sub(r"[^a-z0-9]+", "", raw.lower())
    aliases = {
        "word": "VOCAB",
        "words": "VOCAB",
        "vocab": "VOCAB",
        "vocabulary": "VOCAB",
        "vocabularybuilder": "VOCAB",
        "vb": "VOCAB",
        "wort": "VOCAB",
        "wortschatz": "VOCAB",
        "watch": "WATCH",
        "video": "WATCH",
        "project": "PROJECT",
        "projects": "PROJECT",
        "progress": "RESULT",
        "result": "RESULT",
        "results": "RESULT",
        "checkpoint": "RESULT",
        "check": "RESULT",
        "hskcheck": "RESULT",
        "fortschritt": "RESULT",
        "overview": "OVERVIEW",
        "start": "OVERVIEW",
        "open": "OVERVIEW",
        "cover": "OVERVIEW",
    }
    if normalized in aliases:
        return aliases[normalized], "semantic_section_id"
    if raw:
        return flw_component_segment(raw), "html_section_id"
    if number:
        return f"SECTION_{number:02d}", "generated_position_fallback"
    return "SECTION_UNRESOLVED", "missing_source_section_id"


def scorm_identity_context(unit_path: Path, options: dict | None = None) -> dict:
    options = options or {}
    root_value = options.get("root")
    root = root_from_value(str(root_value)) if root_value else unit_path.parent
    meta = index_meta(unit_path)
    unit_number = unit_number_from_path(unit_path)
    language: dict
    try:
        language = detect_flw_language(root, unit_path)
        target = resolve_deployment_target(language, root, unit_path, unit_number, meta)
    except Exception as exc:
        world_code = flw_component_segment(meta.get("worldCode") or "FLW")
        unit_id = f"{world_code}-U{unit_number}"
        target = {
            "sourceRootCode": "",
            "worldCode": world_code,
            "worldTitle": meta.get("course") or "FLW",
            "languageCode": "",
            "deploymentStageCode": "",
            "unitId": unit_id,
            "unitNumber": unit_number,
            "unitSequence": item_unit_sequence(unit_number),
            "unitTitle": meta.get("title") or unit_path.name,
            "courseExternalKey": "",
            "unitExternalKey": unit_id,
            "scormActivityExternalKey": f"{unit_id}-UNITSCORM",
            "preflightStatus": PREFLIGHT_WORLD_UNRESOLVED,
            "stageResolutionMessage": str(exc),
        }
        language = {"code": "", "label": ""}

    world_code = str(target.get("worldCode") or "FLW").strip().upper()
    unit_id = str(target.get("unitId") or f"{world_code}-U{unit_number}").strip()
    manifest_identifier_value = f"FLW_{world_code}_U{unit_number}_SCORM12"
    future_cmidnumber = flw_scorm_identifier(f"FLW_{world_code}_U{unit_number}_UNITSCORM")
    scorm_activity_external_key = str(target.get("scormActivityExternalKey") or f"{unit_id}-UNITSCORM")
    return {
        "root": str(root),
        "language": language,
        "targetMetadata": target,
        "sourceRootCode": target.get("sourceRootCode", ""),
        "worldCode": world_code,
        "worldTitle": target.get("worldTitle", ""),
        "languageCode": target.get("languageCode", ""),
        "deploymentStageCode": target.get("deploymentStageCode", ""),
        "unitId": unit_id,
        "unitNumber": unit_number,
        "unitSequence": target.get("unitSequence") or item_unit_sequence(unit_number),
        "unitTitle": target.get("unitTitle") or meta.get("title") or unit_path.name,
        "courseExternalKey": target.get("courseExternalKey", ""),
        "unitExternalKey": target.get("unitExternalKey") or unit_id,
        "scormActivityExternalKey": scorm_activity_external_key,
        "futureCmidNumber": future_cmidnumber,
        "scormManifestIdentifier": manifest_identifier_value,
        "packageIdentifierRule": "FLW_<WorldCode>_U###_SCORM12",
        "scoIdentifierRule": "FLW_<WorldCode>_U###_<ComponentKey>",
    }


def sco_identity(unit_identity: dict, kind: str, source_id: str, title: str, number: int | None = None) -> dict:
    component_key, identity_source = section_component_key(source_id, kind, number)
    unit_id = unit_identity["unitId"]
    unit_number = unit_identity["unitNumber"]
    world_code = unit_identity["worldCode"]
    component_id = f"{unit_id}-{component_key}"
    technical_id = f"FLW_{world_code}_U{unit_number}_{component_key}"
    sco_identifier = flw_scorm_identifier(technical_id)
    return {
        "componentKey": component_key,
        "componentId": component_id,
        "componentIdSource": identity_source,
        "scoIdentifier": sco_identifier,
        "itemIdentifier": sco_identifier,
        "resourceIdentifier": f"{sco_identifier}_RES",
        "parentUnitId": unit_id,
        "trackSeparately": True,
        "title": title,
    }


def unit_sco_identity(unit_identity: dict, title: str) -> dict:
    unit_number = unit_identity["unitNumber"]
    world_code = unit_identity["worldCode"]
    sco_identifier = flw_scorm_identifier(f"FLW_{world_code}_U{unit_number}_UNIT")
    return {
        "componentKey": "UNIT",
        "componentId": f"{unit_identity['unitId']}-UNIT",
        "componentIdSource": "whole_unit_fallback",
        "scoIdentifier": sco_identifier,
        "itemIdentifier": sco_identifier,
        "resourceIdentifier": f"{sco_identifier}_RES",
        "parentUnitId": unit_identity["unitId"],
        "trackSeparately": True,
        "title": title,
    }


def component_launch_name(kind: str, component_key: str) -> str:
    prefix = "lesson" if kind == "lesson" else "section"
    return f"{prefix}-{component_key.lower().replace('_', '-')}.html"


def enrich_sco_with_identity(sco: dict, unit_identity: dict, number: int | None = None) -> dict:
    identity = sco_identity(
        unit_identity,
        sco.get("identityKind") or sco.get("kind") or "section",
        sco.get("identitySourceId") or sco.get("id") or "",
        sco.get("title") or "",
        number,
    )
    sco.update(identity)
    return sco


def quoted_posix_path(path: str) -> str:
    return "/".join(quote(part) for part in path.replace("\\", "/").split("/") if part)


def launch_url_from_scos(launch_file: str, lesson_id: str, wrapper_launch_file: str | None = None) -> str:
    launch_path = launch_file.replace("\\", "/").lstrip("/")
    if wrapper_launch_file:
        wrapper_dir = posixpath.dirname(wrapper_launch_file.replace("\\", "/"))
        launch_path = posixpath.relpath(launch_path, wrapper_dir or ".")
    else:
        launch_path = f"../{launch_path}"
    path = quoted_posix_path(launch_path)
    encoded_lesson = quote(lesson_id, safe="")
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}flw_sco=lesson&flw_lesson={encoded_lesson}#{encoded_lesson}"


def lesson_launch_html(unit_title: str, lesson: dict, target_url: str) -> str:
    lesson_title = lesson.get("title") or f"Lesson {lesson.get('number')}"
    page_title = f"{unit_title} - Lesson {lesson.get('number')}: {lesson_title}"
    safe_page_title = html.escape(page_title)
    safe_target = html.escape(target_url, quote=True)
    js_target = json.dumps(target_url, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_page_title}</title>
<script>
window.location.replace({js_target});
</script>
</head>
<body>
<p><a href="{safe_target}">Open {safe_page_title}</a></p>
</body>
</html>
"""


def replace_unit_data_html(text: str, data: dict) -> str:
    span = find_json_object_span(text, "window.UNIT_DATA=")
    if not span:
        return text
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text[: span[0]] + compact + text[span[1] :]


def inject_head_fragment(text: str, fragment: str, marker: str) -> str:
    if marker in text:
        return text
    if re.search(r"</head\s*>", text, flags=re.IGNORECASE):
        return re.sub(r"</head\s*>", fragment + "\n</head>", text, count=1, flags=re.IGNORECASE)
    return fragment + "\n" + text


def inject_base_href(text: str, href: str) -> str:
    if re.search(r"<base\b", text, flags=re.IGNORECASE):
        return text
    base = f'<base href="{html.escape(href, quote=True)}">'
    if re.search(r"<head\b[^>]*>", text, flags=re.IGNORECASE):
        return re.sub(r"<head\b[^>]*>", lambda match: match.group(0) + "\n" + base, text, count=1, flags=re.IGNORECASE)
    return base + "\n" + text


TOP_NAV_HIDE_SELECTORS = [
    "body > header.top",
    "body > header.topbar",
    "body > nav.topbar",
    "body > nav.topnav",
    "body > nav:not(#flw-unit-navigator)",
    "body > .topbar",
    "body > .topnav",
    "body > .top",
    "body > .layout > aside",
    "#app > .topbar",
    "#app > .topnav",
    "#app > .top",
]


def top_nav_hide_css() -> str:
    selectors = ",\n".join(TOP_NAV_HIDE_SELECTORS)
    return f"""{selectors} {{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}}"""


def inject_top_nav_hide_style(index_path: Path, keep_top_nav_bar: bool) -> bool:
    if keep_top_nav_bar:
        return False
    text = read_text(index_path)
    marker = "flw-top-nav-sco-style"
    if marker in text:
        return False
    text = inject_head_fragment(text, f'<style id="{marker}">\n{top_nav_hide_css()}\n</style>', marker)
    write_text(index_path, text)
    return True


def lesson_sco_style(keep_top_nav_bar: bool = False) -> str:
    return section_sco_style("lessons", "flw-lesson-sco-style", keep_top_nav_bar)


def section_sco_style(active_section: str, marker: str = "flw-section-sco-style", keep_top_nav_bar: bool = False) -> str:
    visible = {
        "words": "#words",
        "lessons": "#lessons",
        "watch": "#watch",
        "progress": "#progress",
    }.get(active_section, "#lessons")
    nav_css = "" if keep_top_nav_bar else top_nav_hide_css() + "\n"
    return f"""<style id="{marker}">
{nav_css}
#words,
#lessons,
#watch,
#progress {{
  display: none !important;
}}
{visible} {{
  display: block !important;
}}
main {{
  max-width: 1140px;
  margin: 0 auto;
  padding: 16px !important;
}}
#lesson-root > details.lesson {{
  margin-top: 0;
}}
</style>"""


def lesson_only_data(unit_data: dict, lesson: dict) -> dict:
    filtered = copy.deepcopy(unit_data)
    lesson_data = copy.deepcopy(lesson.get("data") or {})
    lesson_data["id"] = lesson["id"]
    lesson_data["title"] = lesson["title"]
    lesson_data["flwScoNumber"] = lesson["number"]
    filtered["lessons"] = [lesson_data]

    practice = filtered.get("practice")
    if isinstance(practice, dict):
        filtered["practice"] = {lesson["id"]: copy.deepcopy(practice.get(lesson["id"]) or [])}
    else:
        filtered["practice"] = {lesson["id"]: []}

    filtered["vocab"] = []
    filtered["watch"] = []
    filtered["watchPractice"] = []
    return filtered


def lesson_sco_html(source_html: str, unit_title: str, lesson: dict, unit_data: dict, keep_top_nav_bar: bool = False) -> str:
    page_title = f"{unit_title} - Lesson {lesson['number']}: {lesson['title']}"
    text = replace_unit_data_html(source_html, lesson_only_data(unit_data, lesson))
    text = re.sub(
        r"<title[^>]*>.*?</title>",
        f"<title>{html.escape(page_title)}</title>",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = text.replace("Lesson ${i+1}", "Lesson ${l.flwScoNumber||i+1}")
    text = re.sub(
        r"applyUnitChrome\(\);\s*renderVocab\(\);\s*renderLessons\(\);\s*renderWatch\(\);\s*renderProgress\(\);\s*bindAudio\(\);\s*bindZoom\(\);",
        "applyUnitChrome(); renderLessons(); bindAudio(); bindZoom();",
        text,
        count=1,
    )
    text = inject_base_href(text, "../")
    return inject_head_fragment(text, lesson_sco_style(keep_top_nav_bar), "flw-lesson-sco-style")


def section_only_data(unit_data: dict, section: str) -> dict:
    filtered = copy.deepcopy(unit_data)
    filtered["lessons"] = []
    filtered["practice"] = {}

    if section == "words":
        filtered["watch"] = []
        filtered["watchPractice"] = []
        return filtered

    if section == "watch":
        filtered["vocab"] = []
        return filtered

    if section == "progress":
        filtered["vocab"] = []
        filtered["watch"] = []
        filtered["watchPractice"] = []
        return filtered

    return filtered


def section_sco_html(source_html: str, unit_title: str, section: dict, unit_data: dict, keep_top_nav_bar: bool = False) -> str:
    page_title = f"{unit_title} - {section['title']}"
    text = replace_unit_data_html(source_html, section_only_data(unit_data, section["section"]))
    text = re.sub(
        r"<title[^>]*>.*?</title>",
        f"<title>{html.escape(page_title)}</title>",
        text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"applyUnitChrome\(\);\s*renderVocab\(\);\s*renderLessons\(\);\s*renderWatch\(\);\s*renderProgress\(\);\s*bindAudio\(\);\s*bindZoom\(\);",
        section["init"],
        text,
        count=1,
    )
    text = inject_base_href(text, "../")
    return inject_head_fragment(text, section_sco_style(section["section"], "flw-section-sco-style", keep_top_nav_bar), "flw-section-sco-style")


def html_fragment_text(fragment: str) -> str:
    fragment = re.sub(r"<script\b[^>]*>.*?</script>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    fragment = re.sub(r"<style\b[^>]*>.*?</style>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return clean_display_text(html.unescape(fragment))


def html_id_attr_selector(value: str) -> str:
    return '[id="' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"]'


def css_id(value: str) -> str:
    return html_id_attr_selector(value)


def section_id_is_safe(value: str) -> bool:
    value = (value or "").strip()
    if not value or value == "#":
        return False
    if any(token in value for token in ("${", "}", "<", ">", "\"", "'")):
        return False
    return True


def script_json_by_id(source_html: str, script_id: str) -> dict:
    match = re.search(
        r"<script\b(?=[^>]*\bid\s*=\s*(['\"])" + re.escape(script_id) + r"\1)[^>]*>(.*?)</script>",
        source_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return {}
    try:
        value = json.loads(html.unescape(match.group(2).strip()))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def const_json_object(source_html: str, marker: str) -> dict:
    span = find_json_object_span(source_html, marker)
    if not span:
        return {}
    try:
        value = json.loads(source_html[span[0] : span[1]])
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def sco_section(
    section_id: str,
    title: str,
    *,
    kind: str = "section",
    show: list[str] | None = None,
    hide: list[str] | None = None,
    top: list[str] | None = None,
    open_selectors: list[str] | None = None,
    source: str = "profile",
) -> dict:
    section_id = str(section_id or "").strip()
    return {
        "id": section_id,
        "title": str(title or section_id).strip() or section_id,
        "kind": kind,
        "source": source,
        "showSelectors": show or [css_id(section_id)],
        "hideSelectors": hide or [],
        "topSelectors": top or [],
        "openSelectors": open_selectors or [],
    }


def dedupe_section_defs(sections: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for section in sections:
        section_id = str(section.get("id") or "").strip()
        if not section_id or section_id in seen:
            continue
        seen.add(section_id)
        title = str(section.get("title") or "").strip() or section_id.replace("-", " ").replace("_", " ").title()
        result.append({**section, "id": section_id, "title": title})
    return result


def lesson_index_section(
    section_id: str,
    title: str,
    parent_selector: str,
    item_selector: str,
    index_number: int,
    *,
    hide: list[str],
    top: list[str],
    source: str,
) -> dict:
    target_selector = f"{item_selector}:nth-of-type({index_number})"
    return sco_section(
        section_id,
        title,
        kind="lesson",
        show=[parent_selector, target_selector],
        hide=hide,
        top=top,
        open_selectors=[target_selector],
        source=source,
    )


def lesson_id_section(
    section_id: str,
    title: str,
    *,
    parent_selectors: list[str] | None = None,
    hide: list[str],
    top: list[str],
    source: str,
) -> dict:
    target_selector = css_id(section_id)
    return sco_section(
        section_id,
        title,
        kind="lesson",
        show=(parent_selectors or []) + [target_selector],
        hide=hide,
        top=top,
        open_selectors=[target_selector],
        source=source,
    )


def real_world_sco_sections(source_html: str) -> list[dict]:
    checkpoint_data = const_json_object(source_html, "const UNIT =")
    station_block = re.search(
        r"\bconst\s+stations\s*=\s*\[(.*?)\]\s*;",
        source_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if checkpoint_data and station_block and (
        "Real English" in source_html
        or "Real English" in str(checkpoint_data.get("course") or "")
        or isinstance(checkpoint_data.get("profile"), dict)
    ):
        station_ids = {
            "overview": "overview",
            "use": "use-of-english",
            "reading": "reading",
            "listening": "listening",
            "speaking": "speaking",
            "writing": "writing",
            "portfolio": "portfolio",
            "dictation": "dictation",
            "results": "repair-results",
        }
        station_pairs: list[tuple[str, str]] = []
        pair_pattern = re.compile(
            r"\[\s*(['\"])([A-Za-z0-9_-]+)\1\s*,\s*(['\"])(.*?)\3\s*\]",
            flags=re.DOTALL,
        )
        for match in pair_pattern.finditer(station_block.group(1)):
            station_pairs.append((match.group(2).strip(), clean_display_text(match.group(4))))
        if not station_pairs:
            title_map: dict[str, str] = {}
            titles_block = re.search(
                r"\bconst\s+titles\s*=\s*\{(.*?)\}\s*;",
                source_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if titles_block:
                title_pattern = re.compile(
                    r"(?:^|,)\s*([A-Za-z0-9_-]+)\s*:\s*(['\"])(.*?)\2",
                    flags=re.DOTALL,
                )
                title_map = {
                    match.group(1): clean_display_text(match.group(3))
                    for match in title_pattern.finditer(titles_block.group(1))
                }
            station_ids_only = [
                match.group(2)
                for match in re.finditer(r"(['\"])([A-Za-z0-9_-]+)\1", station_block.group(1))
            ]
            station_pairs = [(view_id, title_map.get(view_id, "")) for view_id in station_ids_only]

        legacy_section_identity = bool(str(checkpoint_data.get("course") or "").strip())
        sections = []
        for view_id, station_title in station_pairs:
            title = station_title or view_id.replace("-", " ").title()
            section = sco_section(
                station_ids.get(view_id, view_id),
                title,
                show=[css_id("app")],
                hide=[".part-actions .btn.secondary"],
                source="real-world-checkpoint",
            )
            section.update({"initialView": view_id, "viewIsolated": True})
            if not legacy_section_identity and view_id == "overview":
                section.update({"identitySourceId": "unit", "identityKind": "section"})
            elif legacy_section_identity and view_id in {"use", "results"}:
                section.update({"identitySourceId": view_id, "identityKind": "section"})
            sections.append(section)
        if sections:
            return dedupe_section_defs(sections)

    data = script_json_by_id(source_html, "unit-data")
    if not data or "Real English" not in str(data.get("course") or ""):
        return []
    top = [css_id("topic")]
    sections = [
        sco_section("vocab", "Vocabulary", top=top, source="real-world"),
    ]
    guides = data.get("lesson_guides")
    if isinstance(guides, list) and guides:
        for index_number, guide in enumerate(guides, start=1):
            if not isinstance(guide, dict):
                continue
            title = clean_display_text(
                f"Lesson {index_number}: {guide.get('type') or ''} - {guide.get('title') or ''}"
            )
            sections.append(
                lesson_index_section(
                    f"lesson-{index_number:02d}",
                    title or f"Lesson {index_number}",
                    css_id("lessons"),
                    "#lessonBox > details.lesson",
                    index_number,
                    hide=["#lessonBox > details.lesson"],
                    top=top,
                    source="real-world",
                )
            )
    for section_id, title in (
        ("watch", "Watch"),
        ("practice", "Practice"),
        ("progress", "Progress"),
    ):
        sections.append(sco_section(section_id, title, top=top, source="real-world"))
    sections = dedupe_section_defs(sections)
    return sections if len(sections) >= 2 else []


def russian_world_sco_sections(source_html: str) -> list[dict]:
    if "RUW2" not in source_html and "Russian World" not in source_html and "Русский" not in source_html:
        return []
    nav_titles = {item["id"]: item["title"] for item in generic_nav_sections(source_html)}
    lesson_pairs = [
        ("lesson1", nav_titles.get("vocab") or "Словарь"),
        ("lesson2", nav_titles.get("grammar") or "Грамматика"),
        ("lesson3", nav_titles.get("reading") or "Чтение"),
        ("lesson4", nav_titles.get("listening") or "Аудирование"),
        ("lesson5", nav_titles.get("speaking") or "Говорение"),
        ("lesson6", nav_titles.get("writing") or "Письмо"),
        ("lesson7", nav_titles.get("project") or "Проект"),
    ]
    top = [css_id("cover")]
    sections = [
        lesson_id_section(section_id, title, hide=["main > details.lesson"], top=top, source="russian-world")
        for section_id, title in lesson_pairs
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html)
    ]
    for section_id, title in (("watch", nav_titles.get("watch") or "Видео"), ("progress", nav_titles.get("progress") or "Прогресс")):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(sco_section(section_id, title, top=top, source="russian-world"))
    return dedupe_section_defs(sections)


def chinese_world_sco_sections(source_html: str) -> list[dict]:
    if "Chinese World" not in source_html and "中文世界" not in source_html:
        return []
    top = [css_id("open")]
    nav_titles = {item["id"]: item["title"] for item in generic_nav_sections(source_html)}
    sections: list[dict] = []
    for section_id, title in (
        ("goal", nav_titles.get("goal") or "目标 / Goals"),
        ("goals", nav_titles.get("goals") or "目标 / Goals"),
        ("vocab", nav_titles.get("vocab") or "核心词语 / Vocabulary"),
        ("unit-reader", "小对话 / Reader"),
        ("diagnostic-route", "自学诊断路线"),
        ("identity", "中文学习路线"),
    ):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(sco_section(section_id, title, top=top, source="chinese-world"))
    for index_number in range(1, 8):
        section_id = next(
            (
                candidate
                for candidate in (f"l{index_number}", f"lesson{index_number}", f"lesson-{index_number}")
                if re.search(r"\bid\s*=\s*(['\"])" + re.escape(candidate) + r"\1", source_html)
            ),
            "",
        )
        if not section_id:
            continue
        match = re.search(
            r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1[\s\S]{0,800}?<h2[^>]*>(.*?)</h2>",
            source_html,
            flags=re.IGNORECASE,
        )
        title = nav_titles.get(section_id) or f"第{index_number}课"
        if match:
            title = clean_display_text(match.group(2)) or title
        sections.append(
            lesson_id_section(
                section_id,
                title,
                hide=["main > details.foldable-lesson", "main > details.lesson", ".foldable-lesson"],
                top=top,
                source="chinese-world",
            )
        )
    for section_id, title in (("watch", "故事 / Watch"), ("hsk-check", "HSK 小检"), ("project", "Project")):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(sco_section(section_id, title, top=top, source="chinese-world"))
    sections = dedupe_section_defs(sections)
    return sections if len(sections) >= 2 else []


def german_world_sco_sections(source_html: str) -> list[dict]:
    data = script_json_by_id(source_html, "unit-json")
    if not data or "German World" not in str(data.get("course") or ""):
        return []
    top = ["#app > .hero"]
    if re.search(r"<section\s+id=\\?['\"]vb\\?['\"]", source_html, flags=re.IGNORECASE) and "lessonBox" in source_html:
        sections = [sco_section("vb", "Vocabulary Builder", top=top, source="german-world-generated")]
        lesson_matches: dict[int, tuple[str, str]] = {}
        lesson_pattern = re.compile(
            r"\blesson\(\s*(\d+)\s*,\s*(['\"])(.*?)\2\s*,\s*(['\"])(.*?)\4\s*,",
            flags=re.DOTALL,
        )
        for match in lesson_pattern.finditer(source_html):
            number = int(match.group(1))
            if number not in lesson_matches:
                lesson_matches[number] = (
                    clean_display_text(match.group(3)),
                    clean_display_text(match.group(5)),
                )
        for index_number in sorted(lesson_matches):
            lesson_type, lesson_title = lesson_matches[index_number]
            title = clean_display_text(
                f"Lesson {index_number}: {lesson_type} - {lesson_title}"
            ) or f"Lesson {index_number}"
            section = lesson_index_section(
                f"lesson-{index_number:02d}",
                title,
                css_id("lessons"),
                "#lessonBox > details.lesson",
                index_number,
                hide=["#lessonBox > details.lesson"],
                top=top,
                source="german-world-generated",
            )
            tracked_identity = {
                3: "hoeren",
                4: "lesen",
                5: "sprechen",
                6: "schreiben",
            }.get(index_number)
            if tracked_identity:
                section.update({"identitySourceId": tracked_identity, "identityKind": "section"})
            sections.append(section)
        for source_id, section_id, title in (
            ("watch", "watch", "Watch"),
            ("checkpoint", "c1-checkpoint", "C1 Checkpoint"),
            ("practice", "practice", "Practice"),
            ("progress", "progress", "Progress"),
        ):
            if re.search(r"<section\s+id=\\?['\"]" + re.escape(source_id) + r"\\?['\"]", source_html, flags=re.IGNORECASE):
                section = sco_section(
                    section_id,
                    title,
                    show=[css_id(source_id)],
                    top=top,
                    source="german-world-generated",
                )
                if source_id == "practice":
                    section.update({"identitySourceId": "ueben", "identityKind": "section"})
                sections.append(section)
        return dedupe_section_defs(sections)

    sections = [sco_section("wort", "Wortschatz", top=top, source="german-world")]
    lessons = data.get("lessons") if isinstance(data.get("lessons"), list) else []
    for index_number, lesson in enumerate(lessons, start=1):
        title = f"Lesson {index_number}"
        if isinstance(lesson, dict):
            title = clean_display_text(f"Lesson {index_number}: {lesson.get('title') or ''}") or title
        sections.append(
            lesson_index_section(
                f"lesson-{index_number:02d}",
                title,
                css_id("lernen"),
                "#lernen > details.lesson",
                index_number,
                hide=["#lernen > details.lesson", "#lernen > .card"],
                top=top,
                source="german-world",
            )
        )
    for section_id, title in (
        ("lesen", "Lesen"),
        ("hoeren", "Hören"),
        ("sprechen", "Sprechen"),
        ("schreiben", "Schreiben"),
        ("video", "Video"),
        ("ueben", "Üben"),
        ("fortschritt", "Fortschritt"),
    ):
        sections.append(sco_section(section_id, title, top=top, source="german-world"))
    return dedupe_section_defs(sections)


def japanese_world_sco_sections(source_html: str) -> list[dict]:
    if "Japanese World" not in source_html:
        return []
    top = [css_id("start")]
    sections: list[dict] = []
    if re.search(r"\bid\s*=\s*(['\"])hiragana-roadmap\1", source_html):
        sections.append(sco_section("hiragana-roadmap", "Hiragana Roadmap", top=top, source="japanese-world"))
    sections.append(
        sco_section(
            "vocab",
            "Vocabulary Dictionary",
            show=[css_id("lessons"), css_id("vocab")],
            hide=["#lessons > section.lesson", "#lessons > details"],
            top=top,
            open_selectors=[css_id("vocab")],
            source="japanese-world",
        )
    )
    for index_number in range(1, 8):
        section_id = f"l{index_number}"
        match = re.search(
            r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1[\s\S]{0,500}?<summary[^>]*>(.*?)</summary>",
            source_html,
            flags=re.IGNORECASE,
        )
        title = f"Lesson {index_number}"
        if match:
            title = clean_display_text(match.group(2)) or title
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(
                lesson_id_section(
                    section_id,
                    title,
                    parent_selectors=[css_id("lessons")],
                    hide=["#lessons > section.lesson", "#lessons > details"],
                    top=top,
                    source="japanese-world",
                )
            )
    for section_id, title in (("watch", "Watch"), ("project", "Project"), ("result", "Result")):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(sco_section(section_id, title, top=top, source="japanese-world"))
    return dedupe_section_defs(sections)


def french_world_sco_sections(source_html: str) -> list[dict]:
    data = const_json_object(source_html, "const UNIT =")
    if not data or "French World" not in str(data.get("course") or ""):
        return []
    top = [css_id("overview")]
    sections = [sco_section("vb", "Vocabulaire", top=top, source="french-world")]
    lessons = data.get("lessons") if isinstance(data.get("lessons"), list) else []
    for index_number, lesson in enumerate(lessons, start=1):
        title = f"Leçon {index_number}"
        if isinstance(lesson, dict):
            title = clean_display_text(f"Leçon {index_number}: {lesson.get('title') or ''}") or title
        sections.append(
            lesson_index_section(
                f"lesson-{index_number:02d}",
                title,
                css_id("lessons"),
                "#lessonList > details.lesson",
                index_number,
                hide=["#lessonList > details.lesson"],
                top=top,
                source="french-world",
            )
        )
    for section_id, title in (
        ("watch", "Vidéo"),
        ("practice", "108 exercices"),
        ("project", "Projet"),
        ("results", "Progrès"),
    ):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(section_id) + r"\1", source_html):
            sections.append(sco_section(section_id, title, top=top, source="french-world"))
    return dedupe_section_defs(sections)


def profile_sco_sections(source_html: str) -> list[dict]:
    for factory in (
        real_world_sco_sections,
        russian_world_sco_sections,
        chinese_world_sco_sections,
        german_world_sco_sections,
        japanese_world_sco_sections,
        french_world_sco_sections,
    ):
        sections = factory(source_html)
        if sections:
            return sections
    return []


def generic_top_selectors(source_html: str) -> list[str]:
    ids = []
    for candidate in ("overview", "topic", "open", "start", "cover"):
        if re.search(r"\bid\s*=\s*(['\"])" + re.escape(candidate) + r"\1", source_html):
            ids.append(css_id(candidate))
            break
    return ids


def generic_nav_sections(source_html: str) -> list[dict]:
    sections = []
    top = generic_top_selectors(source_html)
    pattern = re.compile(
        r"<a\b(?=[^>]*\bhref\s*=\s*(['\"])#([^'\"]+)\1)[^>]*>(.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(source_html):
        section_id = html.unescape(match.group(2)).strip()
        if not section_id_is_safe(section_id):
            continue
        title = html_fragment_text(match.group(3))
        sections.append(sco_section(section_id, title or section_id, top=top, source="nav"))
    return dedupe_section_defs(sections)


def generic_html_sections(source_html: str) -> list[dict]:
    sections = []
    top = generic_top_selectors(source_html)
    pattern = re.compile(
        r"<section\b(?=[^>]*\bid\s*=\s*(['\"])([^'\"]+)\1)([^>]*)>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(source_html):
        section_id = html.unescape(match.group(2)).strip()
        if not section_id_is_safe(section_id):
            continue
        following = source_html[match.end() : match.end() + 3000]
        heading = ""
        heading_match = re.search(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", following, flags=re.IGNORECASE | re.DOTALL)
        if heading_match:
            heading = html_fragment_text(heading_match.group(1))
        sections.append(sco_section(section_id, heading or section_id, top=top, source="section"))
    return dedupe_section_defs(sections)


def generic_sco_sections(source_html: str) -> list[dict]:
    profile_sections = profile_sco_sections(source_html)
    if profile_sections:
        return profile_sections
    nav_sections = generic_nav_sections(source_html)
    if len(nav_sections) >= 2:
        return nav_sections
    return generic_html_sections(source_html)


def generic_section_sco_style(section: dict, keep_top_nav_bar: bool = False) -> str:
    show_selectors = []
    for selector in section.get("topSelectors") or []:
        if selector and selector not in show_selectors:
            show_selectors.append(selector)
    for selector in section.get("showSelectors") or [css_id(section["id"])]:
        if selector and selector not in show_selectors:
            show_selectors.append(selector)
    detail_selectors = []
    for selector in section.get("openSelectors") or []:
        if selector and selector not in detail_selectors:
            detail_selectors.append(selector)
    if not detail_selectors:
        top_selector_set = set(section.get("topSelectors") or [])
        for selector in section.get("showSelectors") or [css_id(section["id"])]:
            if selector and selector not in top_selector_set and selector not in detail_selectors:
                detail_selectors.append(selector)
    if not detail_selectors:
        detail_selectors = show_selectors[:]
    boosted_show_selectors = [
        f"{selector}:not(#flw-sco-specificity-boost):not(#flw-sco-specificity-boost-2)"
        for selector in show_selectors
    ]
    boosted_detail_selectors = [
        f"{selector}:not(#flw-sco-specificity-boost):not(#flw-sco-specificity-boost-2)"
        for selector in detail_selectors
    ]
    hide_selectors = [] if section.get("viewIsolated") else [
        "main > section",
        "main > details",
        "main > article",
        ".content > section",
        ".content > details",
        ".content > article",
        "#app > section",
        "#lessons > section.lesson",
        "#lessons > details",
    ]
    for selector in section.get("hideSelectors") or []:
        if selector and selector not in hide_selectors:
            hide_selectors.append(selector)
    hide_css = ",\n".join(hide_selectors)
    hide_rule = f"""{hide_css} {{
  display: none !important;
}}""" if hide_css else ""
    show_css = ",\n".join(boosted_show_selectors)
    show_details_css = ",\n".join(f"{selector} details" for selector in boosted_detail_selectors)
    show_open_details_css = ",\n".join(f"{selector} details[open]" for selector in boosted_detail_selectors)
    nav_css = "" if keep_top_nav_bar else top_nav_hide_css() + "\n"
    return f"""<style id="flw-generic-section-sco-style">
{nav_css}
{hide_rule}
{show_css} {{
  display: block !important;
  visibility: visible !important;
  height: auto !important;
}}
{show_details_css} {{
  display: block !important;
}}
{show_open_details_css} {{
  display: block !important;
}}
body {{
  min-height: 100vh;
}}
main {{
  max-width: 1180px;
  margin-left: auto;
  margin-right: auto;
}}
</style>"""


def generic_section_sco_script(section: dict) -> str:
    open_selectors = section.get("openSelectors") or section.get("showSelectors") or [css_id(section["id"])]
    selector_json = json.dumps(open_selectors, ensure_ascii=False)
    return f"""<script id="flw-generic-section-sco-script">
(function(){{
  function openTarget(){{
    var selectors = {selector_json};
    selectors.forEach(function(selector){{
      document.querySelectorAll(selector).forEach(function(target){{
        if (target.tagName && target.tagName.toLowerCase() === 'details') target.open = true;
        var parent = target.closest && target.closest('details');
        if (parent) parent.open = true;
        target.querySelectorAll && target.querySelectorAll('details').forEach(function(details){{ details.open = true; }});
      }});
    }});
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', openTarget);
  window.addEventListener('load', openTarget);
  setTimeout(openTarget, 0);
  setTimeout(openTarget, 250);
  setTimeout(openTarget, 1000);
}})();
</script>"""


def generic_section_sco_html(source_html: str, unit_title: str, section: dict, keep_top_nav_bar: bool = False) -> str:
    page_title = f"{unit_title} - {section['title']}"
    text = re.sub(
        r"<title[^>]*>.*?</title>",
        f"<title>{html.escape(page_title)}</title>",
        source_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    initial_view = str(section.get("initialView") or "").strip()
    if initial_view:
        view_json = json.dumps(initial_view, ensure_ascii=True)
        text, current_replacements = re.subn(
            r"(\blet\s+current\s*=\s*)(['\"])(.*?)\2",
            lambda match: match.group(1) + view_json,
            text,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if current_replacements:
            text = re.sub(
                r"(\bfunction\s+show\s*\(\s*([A-Za-z_$][\w$]*)\s*\)\s*\{)",
                lambda match: match.group(1) + f"{match.group(2)}={view_json};",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
    text = inject_base_href(text, "../")
    fragment = generic_section_sco_style(section, keep_top_nav_bar) + "\n" + generic_section_sco_script(section)
    return inject_head_fragment(text, fragment, "flw-generic-section-sco-style")


def unit_lessons(unit_path: Path) -> list[dict]:
    index = unit_path / "index.html"
    if not index.exists():
        return []
    data = extract_json_object(read_text(index), "window.UNIT_DATA=")
    raw_lessons = data.get("lessons")
    if not isinstance(raw_lessons, list):
        return []
    lessons = []
    for index_number, lesson in enumerate(raw_lessons, start=1):
        if not isinstance(lesson, dict):
            continue
        lesson_id = str(lesson.get("id") or f"lesson-{index_number}").strip() or f"lesson-{index_number}"
        lesson_title = str(lesson.get("title") or f"Lesson {index_number}").strip() or f"Lesson {index_number}"
        lessons.append(
            {
                "number": index_number,
                "id": lesson_id,
                "title": lesson_title,
                "aim": str(lesson.get("aim") or "").strip(),
                "data": copy.deepcopy(lesson),
            }
        )
    return lessons


def unit_fixed_sections(unit_data: dict) -> list[dict]:
    sections = []
    if unit_data.get("vocab"):
        sections.append(
            {
                "id": "vocabulary",
                "title": "Vocabulary Builder",
                "section": "words",
                "launchName": "section-01-vocabulary-builder.html",
                "init": "applyUnitChrome(); renderVocab(); bindAudio(); bindZoom();",
            }
        )
    if unit_data.get("watch") or unit_data.get("watchPractice"):
        sections.append(
            {
                "id": "watch",
                "title": "Watch",
                "section": "watch",
                "launchName": "section-98-watch.html",
                "init": "applyUnitChrome(); renderWatch(); bindAudio(); bindZoom();",
            }
        )
    sections.append(
        {
            "id": "progress",
            "title": "Progress Result",
            "section": "progress",
            "launchName": "section-99-progress-result.html",
            "init": "applyUnitChrome(); renderProgress(); bindAudio(); bindZoom();",
        }
    )
    return sections


def scorm_structure_preview(unit_path: Path, options: dict | None = None) -> dict:
    options = options or {}
    meta = index_meta(unit_path)
    unit_number = unit_number_from_path(unit_path)
    title = (options.get("title") or meta.get("title") or unit_path.name).strip()
    unit_identity = scorm_identity_context(unit_path, options)
    launch_file = (options.get("launchFile") or "index.html").replace("\\", "/").lstrip("/")
    launch_path = unit_path / launch_file
    unit_data = {}
    source_html = ""
    structured_unit_data = False
    if launch_path.exists():
        try:
            source_html = read_text(launch_path)
            structured_unit_data = bool(find_json_object_span(source_html, "window.UNIT_DATA="))
            unit_data = extract_json_object(source_html, "window.UNIT_DATA=") if structured_unit_data else {}
        except AppError:
            unit_data = {}
    section_scos: list[dict] = []
    if structured_unit_data:
        lessons = unit_lessons(unit_path)
        fixed_sections = unit_fixed_sections(unit_data)
        opening_sections = [section for section in fixed_sections if section["section"] == "words"]
        closing_sections = [section for section in fixed_sections if section["section"] != "words"]
        for section in opening_sections:
            sco = enrich_sco_with_identity(
                {
                    "kind": section["section"],
                    "id": section["id"],
                    "title": section["title"],
                    "headerIncluded": True,
                    "filteredContent": True,
                },
                unit_identity,
            )
            sco["launchFile"] = f"scos/{component_launch_name(sco['kind'], sco['componentKey'])}"
            section_scos.append(sco)
        for lesson in lessons:
            sco = enrich_sco_with_identity(
                {
                    "kind": "lesson",
                    "id": lesson["id"],
                    "title": f"Lesson {lesson['number']}: {lesson['title']}",
                    "headerIncluded": True,
                    "filteredContent": True,
                },
                unit_identity,
                lesson["number"],
            )
            sco["launchFile"] = f"scos/{component_launch_name('lesson', sco['componentKey'])}"
            section_scos.append(sco)
        for section in closing_sections:
            sco = enrich_sco_with_identity(
                {
                    "kind": section["section"],
                    "id": section["id"],
                    "title": section["title"],
                    "headerIncluded": True,
                    "filteredContent": True,
                },
                unit_identity,
            )
            sco["launchFile"] = f"scos/{component_launch_name(sco['kind'], sco['componentKey'])}"
            section_scos.append(sco)
    elif source_html:
        for index_number, section in enumerate(generic_sco_sections(source_html), start=1):
            sco = enrich_sco_with_identity(
                {
                    "kind": section.get("kind") or "section",
                    "id": section["id"],
                    "title": section["title"],
                    "identityKind": section.get("identityKind") or "",
                    "identitySourceId": section.get("identitySourceId") or "",
                    "headerIncluded": True,
                    "filteredContent": True,
                },
                unit_identity,
                index_number,
            )
            sco["launchFile"] = f"scos/{component_launch_name(sco['kind'], sco['componentKey'])}"
            section_scos.append(sco)
    include_unit_sco = bool(options.get("includeUnitSco")) or not section_scos
    scos = []
    if include_unit_sco:
        unit_identity_sco = unit_sco_identity(unit_identity, title)
        scos.append(
            {
                "kind": "unit",
                "id": f"unit-{unit_number}",
                "title": title,
                "launchFile": launch_file,
                "headerIncluded": True,
                "filteredContent": False,
                **unit_identity_sco,
            }
        )
    scos.extend(section_scos)
    component_mappings = component_mappings_from_scos(section_scos, unit_identity)
    micro_activity_mappings = micro_activity_mappings_from_unit_data(unit_data, lessons if structured_unit_data else [], section_scos, unit_identity)
    return {
        "manifestSchemaVersion": 2,
        "scormStructureVersion": SCORM_STRUCTURE_VERSION,
        "unit": unit_number,
        "title": title,
        "unitId": unit_identity["unitId"],
        "worldCode": unit_identity["worldCode"],
        "deploymentStageCode": unit_identity.get("deploymentStageCode", ""),
        "courseExternalKey": unit_identity.get("courseExternalKey", ""),
        "unitExternalKey": unit_identity["unitExternalKey"],
        "scormActivityExternalKey": unit_identity["scormActivityExternalKey"],
        "futureCmidNumber": unit_identity["futureCmidNumber"],
        "scormManifestIdentifier": unit_identity["scormManifestIdentifier"],
        "launchFile": launch_file,
        "launchFileExists": launch_path.exists(),
        "includeUnitSco": include_unit_sco,
        "keepTopNavBar": bool(options.get("keepTopNavBar")),
        "scoCount": len(scos),
        "lessonScoCount": len([sco for sco in scos if sco["kind"] == "lesson"]),
        "sectionScoCount": len([sco for sco in scos if sco["kind"] != "unit"]),
        "componentMappings": component_mappings,
        "microActivityMappings": micro_activity_mappings,
        "scos": scos,
    }


def component_mappings_from_scos(scos: list[dict], unit_identity: dict) -> list[dict]:
    mappings: list[dict] = []
    for order, sco in enumerate(scos, start=1):
        mappings.append(
            {
                "componentId": sco.get("componentId", ""),
                "componentKey": sco.get("componentKey", ""),
                "componentIdSource": sco.get("componentIdSource", ""),
                "kind": sco.get("kind") or "section",
                "sourceId": sco.get("id", ""),
                "title": sco.get("title", ""),
                "scoIdentifier": sco.get("scoIdentifier", ""),
                "itemIdentifier": sco.get("itemIdentifier", ""),
                "resourceIdentifier": sco.get("resourceIdentifier", ""),
                "launchFile": sco.get("launchFile", ""),
                "parentUnitId": unit_identity["unitId"],
                "trackSeparately": True,
                "displayOrder": order,
                "displayOrderIsCanonical": False,
            }
        )
    return mappings


def stable_activity_suffix(raw_id: str, fallback_index: int) -> tuple[str, str]:
    raw = str(raw_id or "").strip()
    if raw:
        match = re.match(r"^q(?:uestion)?[_\-\s]?0*(\d{1,4})$", raw, flags=re.IGNORECASE)
        if match:
            return f"Q{int(match.group(1)):03d}", "source_activity_id"
        return flw_component_segment(raw), "source_activity_id"
    return f"Q{fallback_index:03d}", "generated_parent_sequence"


def collect_micro_activity_candidates(value, *, path: str = "") -> list[dict]:
    candidates: list[dict] = []
    if isinstance(value, list):
        for index_number, item in enumerate(value, start=1):
            if isinstance(item, dict):
                raw_id = first_text_value(
                    item.get("activityId"),
                    item.get("activityID"),
                    item.get("flwActivityId"),
                    item.get("questionId"),
                    item.get("qid"),
                    item.get("id"),
                    item.get("key"),
                )
                candidates.append({"index": index_number, "rawId": raw_id, "kind": item.get("kind") or item.get("type") or "micro-activity", "path": path})
            elif isinstance(item, (list, tuple)):
                candidates.extend(collect_micro_activity_candidates(item, path=f"{path}[{index_number}]"))
    elif isinstance(value, dict):
        for key in ("questions", "practice", "activities", "tasks", "items", "cards", "exercises"):
            if key in value:
                candidates.extend(collect_micro_activity_candidates(value.get(key), path=f"{path}.{key}" if path else key))
    return candidates


def component_sco_by_keys(scos: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for sco in scos:
        for key in (sco.get("componentKey"), sco.get("id"), sco.get("kind")):
            if key:
                mapping[str(key).lower()] = sco
    return mapping


def micro_activity_mappings_from_unit_data(unit_data: dict, lessons: list[dict], scos: list[dict], unit_identity: dict) -> list[dict]:
    if not isinstance(unit_data, dict):
        return []
    by_key = component_sco_by_keys(scos)
    mappings: list[dict] = []

    def add_candidates(parent_sco: dict | None, candidates: list[dict]) -> None:
        if not parent_sco:
            return
        parent_component_id = parent_sco.get("componentId", "")
        parent_component_key = parent_sco.get("componentKey", "")
        for fallback_index, candidate in enumerate(candidates, start=1):
            suffix, source = stable_activity_suffix(candidate.get("rawId", ""), candidate.get("index") or fallback_index)
            mappings.append(
                {
                    "activityId": f"{parent_component_id}-{suffix}",
                    "activityKey": suffix,
                    "activityIdSource": source,
                    "sourceActivityId": candidate.get("rawId", ""),
                    "kind": candidate.get("kind") or "micro-activity",
                    "parentComponentId": parent_component_id,
                    "parentComponentKey": parent_component_key,
                    "parentScoIdentifier": parent_sco.get("scoIdentifier", ""),
                    "parentUnitId": unit_identity["unitId"],
                    "trackAsSeparateSco": False,
                    "sourcePath": candidate.get("path", ""),
                }
            )

    practice = unit_data.get("practice")
    for lesson in lessons:
        lesson_component_key, _ = lesson_component_key_from_source(lesson.get("id", ""), lesson.get("number"))
        parent_sco = by_key.get(lesson_component_key.lower()) or by_key.get(str(lesson.get("id") or "").lower())
        candidates = collect_micro_activity_candidates(lesson.get("data") or {}, path=f"lessons.{lesson.get('id')}")
        if isinstance(practice, dict):
            for key in (lesson.get("id"), lesson_component_key, str(lesson.get("number"))):
                if key in practice:
                    candidates.extend(collect_micro_activity_candidates(practice.get(key), path=f"practice.{key}"))
        add_candidates(parent_sco, candidates)

    vocab_parent = by_key.get("vocab") or by_key.get("vocabulary")
    add_candidates(vocab_parent, collect_micro_activity_candidates(unit_data.get("vocab"), path="vocab"))

    watch_parent = by_key.get("watch")
    add_candidates(watch_parent, collect_micro_activity_candidates(unit_data.get("watchPractice") or unit_data.get("watch"), path="watch"))

    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for mapping in mappings:
        key = (mapping.get("parentComponentId", ""), mapping.get("activityId", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(mapping)
    return unique


def create_fixed_section_launch(
    stage: Path,
    unit_title: str,
    section: dict,
    source_html: str,
    unit_data: dict,
    unit_identity: dict | None = None,
    keep_top_nav_bar: bool = False,
) -> dict:
    unit_identity = unit_identity or scorm_identity_context(stage, {})
    base_sco = enrich_sco_with_identity(
        {
            "number": 0,
            "id": section["id"],
            "kind": section["section"],
            "title": section["title"],
        },
        unit_identity,
    )
    launch_path = f"scos/{component_launch_name(base_sco['kind'], base_sco['componentKey'])}"
    write_text(stage / launch_path, section_sco_html(source_html, unit_title, section, unit_data, keep_top_nav_bar))
    base_sco["launchFile"] = launch_path
    return base_sco


def create_lesson_launches(
    stage: Path,
    launch_file: str,
    unit_title: str,
    lessons: list[dict],
    sco_prefix: str = "scos",
    target_launch_file: str | None = None,
    identifier_prefix: str = "LESSON",
    source_html: str | None = None,
    unit_data: dict | None = None,
    unit_identity: dict | None = None,
    keep_top_nav_bar: bool = False,
) -> list[dict]:
    scos = []
    sco_prefix = sco_prefix.strip("/") or "scos"
    sco_dir = stage / sco_prefix
    target_launch_file = target_launch_file or launch_file
    unit_identity = unit_identity or scorm_identity_context(stage, {})
    for lesson in lessons:
        identity = sco_identity(unit_identity, "lesson", lesson["id"], f"Lesson {lesson['number']}: {lesson['title']}", lesson["number"])
        launch_name = component_launch_name("lesson", identity["componentKey"])
        launch_path = f"{sco_prefix}/{launch_name}"
        target_url = launch_url_from_scos(target_launch_file, lesson["id"], launch_path)
        if source_html and unit_data:
            wrapper = lesson_sco_html(source_html, unit_title, lesson, unit_data, keep_top_nav_bar)
        else:
            wrapper = lesson_launch_html(unit_title, lesson, target_url)
        (sco_dir / launch_name).parent.mkdir(parents=True, exist_ok=True)
        write_text(stage / launch_path, wrapper)
        scos.append(
            {
                "number": lesson["number"],
                "id": lesson["id"],
                "kind": "lesson",
                "title": f"Lesson {lesson['number']}: {lesson['title']}",
                "launchFile": launch_path,
                **identity,
            }
        )
    return scos


def create_generic_section_launches(
    stage: Path,
    unit_title: str,
    source_html: str,
    sco_prefix: str = "scos",
    unit_identity: dict | None = None,
    keep_top_nav_bar: bool = False,
) -> list[dict]:
    scos = []
    sco_prefix = sco_prefix.strip("/") or "scos"
    sco_dir = stage / sco_prefix
    unit_identity = unit_identity or scorm_identity_context(stage, {})
    for index_number, section in enumerate(generic_sco_sections(source_html), start=1):
        identity = sco_identity(
            unit_identity,
            section.get("identityKind") or section.get("kind") or "section",
            section.get("identitySourceId") or section["id"],
            section["title"],
            index_number,
        )
        launch_name = component_launch_name(section.get("kind") or "section", identity["componentKey"])
        launch_path = f"{sco_prefix}/{launch_name}"
        (sco_dir / launch_name).parent.mkdir(parents=True, exist_ok=True)
        write_text(stage / launch_path, generic_section_sco_html(source_html, unit_title, section, keep_top_nav_bar))
        scos.append(
            {
                "number": index_number,
                "id": section["id"],
                "kind": section.get("kind") or "section",
                "title": section["title"],
                "launchFile": launch_path,
                **identity,
            }
        )
    return scos


def manifest_xml(
    identifier: str,
    title: str,
    launch_file: str,
    files: list[str],
    lesson_scos: list[dict] | None = None,
    include_unit_sco: bool = True,
    unit_identity: dict | None = None,
) -> str:
    lesson_scos = lesson_scos or []
    file_nodes = "\n".join(f'      <file href="{html.escape(path, quote=True)}" />' for path in sorted(files))
    safe_identifier = html.escape(identifier, quote=True)
    safe_title = html.escape(title or identifier)
    safe_launch = html.escape(launch_file, quote=True)
    item_nodes = []
    resource_nodes = []
    if include_unit_sco:
        unit_sco = unit_sco_identity(unit_identity, title) if unit_identity else {
            "itemIdentifier": "ITEM1",
            "resourceIdentifier": "RES1",
        }
        safe_unit_item_id = html.escape(unit_sco["itemIdentifier"], quote=True)
        safe_unit_resource_id = html.escape(unit_sco["resourceIdentifier"], quote=True)
        item_nodes.append(
            f"""      <item identifier="{safe_unit_item_id}" identifierref="{safe_unit_resource_id}" isvisible="true">
        <title>{safe_title}</title>
      </item>"""
        )
        resource_nodes.append(
            f"""    <resource identifier="{safe_unit_resource_id}" type="webcontent" adlcp:scormtype="sco" href="{safe_launch}">
{file_nodes}
    </resource>"""
        )
    for sco in lesson_scos:
        safe_item_id = html.escape(sco["itemIdentifier"], quote=True)
        safe_resource_id = html.escape(sco["resourceIdentifier"], quote=True)
        safe_sco_title = html.escape(sco["title"] or f"Lesson {sco['number']}")
        safe_sco_launch = html.escape(sco["launchFile"], quote=True)
        sco_files = sorted(sco.get("files") or files)
        sco_file_nodes = "\n".join(f'      <file href="{html.escape(path, quote=True)}" />' for path in sco_files)
        item_nodes.append(
            f"""      <item identifier="{safe_item_id}" identifierref="{safe_resource_id}" isvisible="true">
        <title>{safe_sco_title}</title>
      </item>"""
        )
        resource_nodes.append(
            f"""    <resource identifier="{safe_resource_id}" type="webcontent" adlcp:scormtype="sco" href="{safe_sco_launch}">
{sco_file_nodes}
    </resource>"""
        )
    items_xml = "\n".join(item_nodes)
    resources_xml = "\n".join(resource_nodes)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{safe_identifier}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG1">
    <organization identifier="ORG1">
      <title>{safe_title}</title>
{items_xml}
    </organization>
  </organizations>
  <resources>
{resources_xml}
  </resources>
</manifest>
"""


def zip_stage(stage: Path, zip_path: Path) -> dict:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted([p for p in stage.rglob("*") if p.is_file()], key=lambda p: p.relative_to(stage).as_posix())
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        manifest = stage / "imsmanifest.xml"
        if manifest.exists():
            package.write(manifest, "imsmanifest.xml")
        for path in files:
            rel = path.relative_to(stage).as_posix()
            if rel == "imsmanifest.xml":
                continue
            package.write(path, rel)
    with zipfile.ZipFile(zip_path) as package:
        bad = package.testzip()
        names = package.namelist()
        manifest_ok = "imsmanifest.xml" in names
        xml_ok = False
        item_count = 0
        sco_count = 0
        if manifest_ok:
            root = ET.fromstring(package.read("imsmanifest.xml"))
            xml_ok = True
            item_count = len(root.findall(".//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}item"))
            for resource in root.findall(".//{http://www.imsproject.org/xsd/imscp_rootv1p1p2}resource"):
                scorm_type = resource.attrib.get("{http://www.adlnet.org/xsd/adlcp_rootv1p2}scormtype")
                if scorm_type == "sco":
                    sco_count += 1
    return {
        "zipPath": str(zip_path),
        "zipBytes": zip_path.stat().st_size,
        "fileCount": len(files),
        "zipTest": "PASS" if bad is None else f"FAIL: {bad}",
        "manifestAtRoot": manifest_ok,
        "manifestXmlOk": xml_ok,
        "manifestItemCount": item_count,
        "scoCount": sco_count,
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_content_sha256(stage: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted([p for p in stage.rglob("*") if p.is_file()], key=lambda p: p.relative_to(stage).as_posix()):
        rel = path.relative_to(stage).as_posix().encode("utf-8", errors="surrogateescape")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def unique_export_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}-{uuid.uuid4().hex[:8]}{suffix}")


def flw_import_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def detect_flw_language(root: Path, unit_path: Path) -> dict:
    def path_candidates(base: Path) -> list[str]:
        try:
            resolved = base.resolve()
        except OSError:
            resolved = base
        return [str(part).strip().lower() for part in resolved.parts if str(part).strip()]

    def match_path(base: Path) -> dict | None:
        candidates = path_candidates(base)
        for candidate in reversed(candidates):
            for language in FLW_LANGUAGE_ROOTS:
                markers = language_root_markers(language)
                if any(candidate == marker or candidate.startswith(marker + "-") or candidate.startswith(marker + "_") for marker in markers):
                    return {"code": language["code"], "label": language["label"]}
        for candidate in reversed(candidates):
            for language in FLW_LANGUAGE_ROOTS:
                markers = language_root_markers(language)
                if any(marker in candidate for marker in markers if len(marker) > 3):
                    return {"code": language["code"], "label": language["label"]}
        return None

    # The selected content root is authoritative. Cache folders may live under
    # an application directory whose name contains a different world's marker.
    for base in (root, unit_path):
        detected = match_path(base)
        if detected:
            return detected
    known = ", ".join(language["code"] for language in FLW_LANGUAGE_ROOTS)
    raise AppError(
        "Could not detect the FLW language course for this unit. "
        f"Please select one of the SmartCourses language roots first: {known}."
    )


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


def safe_scorm_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    cleaned = cleaned.strip("_.-")
    return cleaned or f"FLW_SCORM_{uuid.uuid4().hex[:8]}"


def normalized_source_root_code(value: str | None) -> str:
    return str(value or "").strip().lower()


def course_map_load_result(course_map_path: Path | str | None = None) -> tuple[dict | None, list[str]]:
    path = Path(course_map_path) if course_map_path else FLW_COURSE_MAP_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"Course-map config not found: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"Course-map config JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
    except OSError as exc:
        return None, [f"Course-map config could not be read: {exc}"]
    errors = validate_course_map_config(data)
    if errors:
        return data if isinstance(data, dict) else None, errors
    return data, []


def load_flw_moodle_course_map(course_map_path: Path | str | None = None) -> dict:
    data, errors = course_map_load_result(course_map_path)
    if errors or data is None:
        raise AppError("Invalid FLW Moodle course-map config: " + "; ".join(errors), 500)
    return data


def validate_course_map_config(data) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Course-map config root must be a JSON object."]
    if data.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1.")
    worlds = data.get("worlds")
    if not isinstance(worlds, dict) or not worlds:
        errors.append("worlds must be a non-empty object.")
        return errors

    seen_world_codes: dict[str, str] = {}
    for source_code, world in worlds.items():
        label = f"worlds.{source_code}"
        if not isinstance(world, dict):
            errors.append(f"{label} must be an object.")
            continue
        declared_source = normalized_source_root_code(world.get("sourceRootCode"))
        if declared_source != normalized_source_root_code(source_code):
            errors.append(f"{label}.sourceRootCode must match its worlds key.")
        for key in ("worldCode", "worldTitle", "languageCode"):
            if not str(world.get(key) or "").strip():
                errors.append(f"{label}.{key} is required.")
        world_code = str(world.get("worldCode") or "").strip().upper()
        if world_code:
            previous = seen_world_codes.get(world_code)
            if previous and previous != source_code:
                errors.append(f"worldCode {world_code} is duplicated by {previous} and {source_code}.")
            seen_world_codes[world_code] = source_code
        markers = world.get("sourceRootMarkers", [])
        if not isinstance(markers, list) or not all(isinstance(marker, str) and marker.strip() for marker in markers):
            errors.append(f"{label}.sourceRootMarkers must be a list of non-empty strings.")
        category = world.get("category", {})
        if not isinstance(category, dict):
            errors.append(f"{label}.category must be an object when present.")
        elif category.get("id") is not None:
            try:
                category_id = int(category.get("id"))
            except (TypeError, ValueError):
                errors.append(f"{label}.category.id must be an integer or null.")
            else:
                if category_id <= 0:
                    errors.append(f"{label}.category.id must be positive or null.")
        stage_policy = world.get("stagePolicy", {})
        if not isinstance(stage_policy, dict):
            errors.append(f"{label}.stagePolicy must be an object when present.")
        rules = world.get("stageRules", [])
        if not isinstance(rules, list):
            errors.append(f"{label}.stageRules must be a list.")
            continue
        ranges: list[tuple[int, int, str]] = []
        for index, rule in enumerate(rules):
            rule_label = f"{label}.stageRules[{index}]"
            if not isinstance(rule, dict):
                errors.append(f"{rule_label} must be an object.")
                continue
            stage_code = str(rule.get("stageCode") or "").strip()
            if not stage_code:
                errors.append(f"{rule_label}.stageCode is required.")
            for key in ("unitStart", "unitEnd"):
                try:
                    int(rule.get(key))
                except (TypeError, ValueError):
                    errors.append(f"{rule_label}.{key} must be an integer.")
            try:
                start = int(rule.get("unitStart"))
                end = int(rule.get("unitEnd"))
            except (TypeError, ValueError):
                continue
            if start < 1 or end < start:
                errors.append(f"{rule_label} must have 1 <= unitStart <= unitEnd.")
            for old_start, old_end, old_stage in ranges:
                if start <= old_end and old_start <= end:
                    errors.append(f"{rule_label} overlaps {old_stage} ({old_start}-{old_end}).")
            ranges.append((start, end, stage_code))
            if not str(rule.get("courseShortname") or "").strip():
                errors.append(f"{rule_label}.courseShortname is required.")
            idnumber = str(rule.get("courseIdnumber") or "").strip()
            if not idnumber:
                errors.append(f"{rule_label}.courseIdnumber is required.")
            if re.search(r"\b\d{2,}\b", idnumber):
                errors.append(f"{rule_label}.courseIdnumber must not use a Moodle numeric course id as identity.")
    return errors


def configured_worlds(course_map_path: Path | str | None = None) -> list[dict]:
    data = load_flw_moodle_course_map(course_map_path)
    return list(data.get("worlds", {}).values())


def configured_worlds_public(course_map_path: Path | str | None = None) -> list[dict]:
    data, errors = course_map_load_result(course_map_path)
    worlds = (data or {}).get("worlds", {}) if isinstance(data, dict) else {}
    rows: list[dict] = []
    for source_code, world in worlds.items():
        if not isinstance(world, dict):
            continue
        rows.append(
            {
                "sourceRootCode": source_code,
                "worldCode": world.get("worldCode", ""),
                "worldTitle": world.get("worldTitle", ""),
                "languageCode": world.get("languageCode", ""),
                "category": world.get("category", {}),
                "stageRuleCount": len(world.get("stageRules", []) if isinstance(world.get("stageRules"), list) else []),
            }
        )
    return rows if not errors else [{"preflightStatus": PREFLIGHT_INVALID_CONFIG, "errors": errors}]


def world_config_for_source(source_root_code: str, course_map: dict | None = None) -> dict | None:
    if course_map is None:
        course_map = load_flw_moodle_course_map()
    worlds = course_map.get("worlds", {}) if isinstance(course_map, dict) else {}
    world = worlds.get(normalized_source_root_code(source_root_code))
    return world if isinstance(world, dict) else None


def language_root_markers(language: dict) -> tuple[str, ...]:
    markers = {
        str(language.get("code") or "").strip().lower(),
        str(language.get("label") or "").strip().lower(),
        str(language.get("label") or "").strip().lower().replace(" ", "-"),
        str(language.get("label") or "").strip().lower().replace(" ", "_"),
        str(language.get("worldCode") or "").strip().lower(),
    }
    markers.update(str(marker).strip().lower() for marker in language.get("markers", ()) if str(marker).strip())
    return tuple(marker for marker in markers if marker)


def stage_normalization_patterns(course_map: dict | None = None) -> tuple[re.Pattern, re.Pattern]:
    normalization = (course_map or {}).get("stageNormalization", {}) if isinstance(course_map, dict) else {}
    major_pattern = str(normalization.get("majorCefrPattern") or r"^(A1|A2|B1|B2|C1|C2)(?:[._-]?[0-9]+)?$")
    pre_a1_pattern = str(normalization.get("preA1Pattern") or r"^PRE[-_ ]?A1(?:[._-]?[0-9]+)?$")
    return re.compile(major_pattern, flags=re.IGNORECASE), re.compile(pre_a1_pattern, flags=re.IGNORECASE)


def normalize_deployment_stage(value: str | None, course_map: dict | None = None, world_config: dict | None = None) -> str | None:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return None
    cleaned = raw.replace("–", "-").replace("—", "-").replace("_", "-").upper()
    cleaned = re.sub(r"\s+", "", cleaned)
    major_pattern, pre_a1_pattern = stage_normalization_patterns(course_map)
    if pre_a1_pattern.match(cleaned):
        return "Pre-A1"
    match = major_pattern.match(cleaned)
    if match:
        return match.group(1).upper()
    token_re = re.compile(r"(PRE[-_ ]?A1|A1|A2|B1|B2|C1|C2)(?:[._-]?[0-9]+)?\+?", flags=re.IGNORECASE)
    tokens = [match.group(0) for match in token_re.finditer(raw)]
    normalized_tokens: list[str] = []
    for token in tokens:
        token_cleaned = token.replace("_", "-").upper()
        if re.match(r"^PRE[-_ ]?A1", token_cleaned, flags=re.IGNORECASE):
            normalized_tokens.append("Pre-A1")
        else:
            token_match = re.match(r"^(A1|A2|B1|B2|C1|C2)", token_cleaned, flags=re.IGNORECASE)
            if token_match:
                normalized_tokens.append(token_match.group(1).upper())
    if normalized_tokens and len(set(normalized_tokens)) == 1 and token_re.match(raw):
        return normalized_tokens[0]
    return None


def external_key_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").upper()).strip("_")
    return cleaned or "UNRESOLVED"


def shortname_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").upper()).strip("-")
    return cleaned or "UNRESOLVED"


def stage_rule_for_unit(world_config: dict, unit_sequence: int) -> dict | None:
    for rule in world_config.get("stageRules", []) or []:
        try:
            start = int(rule.get("unitStart"))
            end = int(rule.get("unitEnd"))
        except (TypeError, ValueError):
            continue
        if start <= unit_sequence <= end:
            return rule
    return None


def first_text_value(*values) -> str:
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if text:
            return text
    return ""


def filename_stage_token(root: Path, unit_path: Path, world_config: dict | None, course_map: dict | None = None) -> str:
    policy = (world_config or {}).get("stagePolicy", {}) if isinstance(world_config, dict) else {}
    if not policy.get("allowFilenameStageToken"):
        return ""
    names = [unit_path.name, unit_path.parent.name]
    try:
        archive = selected_unit_archive(root, unit_path)
    except Exception:
        archive = None
    if archive:
        names.insert(0, archive.name)
    token_re = re.compile(r"(?<![A-Za-z0-9])((?:Pre[-_ ]?A1|A1|A2|B1|B2|C1|C2)(?:[._-]?[0-9]+)?)(?![A-Za-z0-9])", re.IGNORECASE)
    for name in names:
        match = token_re.search(str(name or ""))
        if match:
            return match.group(1).replace("_", ".")
    return ""


def item_unit_sequence(unit_number: str | int | None) -> int:
    match = re.search(r"(\d{1,3})", str(unit_number or ""))
    return int(match.group(1)) if match else 0


def resolve_deployment_target(
    language: dict,
    root: Path,
    unit_path: Path,
    unit_number: str | None = None,
    meta: dict | None = None,
    course_map_path: Path | str | None = None,
) -> dict:
    unit_number = parse_unit_number_option(unit_number) or unit_number_from_path(unit_path)
    unit_sequence = item_unit_sequence(unit_number)
    meta = meta or index_meta(unit_path)
    source_root_code = normalized_source_root_code(language.get("code") or language.get("sourceRootCode"))
    source_label = str(language.get("label") or source_root_code)
    title = str(meta.get("title") or unit_path.name)
    base = {
        "manifestSchemaVersion": 2,
        "sourceRootCode": source_root_code,
        "worldCode": "",
        "worldTitle": "",
        "languageCode": "",
        "sourceStage": "",
        "sourceStageSource": "",
        "explicitDeploymentStage": "",
        "deploymentStageCode": "",
        "stageResolutionStatus": PREFLIGHT_STAGE_UNRESOLVED,
        "stageResolutionSource": "",
        "stageResolutionMessage": "",
        "preflightStatus": PREFLIGHT_STAGE_UNRESOLVED,
        "unitId": "",
        "unitNumber": unit_number,
        "unitSequence": unit_sequence,
        "unitTitle": title,
        "courseExternalKey": "",
        "courseShortname": "",
        "courseIdnumber": "",
        "unitExternalKey": "",
        "scormActivityExternalKey": "",
        "moodleCategory": None,
        "moodleCategorySource": "",
    }

    course_map, errors = course_map_load_result(course_map_path)
    if errors or course_map is None:
        base.update(
            {
                "preflightStatus": PREFLIGHT_INVALID_CONFIG,
                "stageResolutionStatus": PREFLIGHT_INVALID_CONFIG,
                "stageResolutionMessage": "; ".join(errors),
                "configErrors": errors,
            }
        )
        return base

    world_config = world_config_for_source(source_root_code, course_map)
    if not world_config:
        base.update(
            {
                "preflightStatus": PREFLIGHT_WORLD_UNRESOLVED,
                "stageResolutionStatus": PREFLIGHT_WORLD_UNRESOLVED,
                "stageResolutionMessage": f"No configured FLW world matches source root {source_root_code or source_label}.",
            }
        )
        return base

    world_code = str(world_config.get("worldCode") or "").strip().upper()
    world_title = str(world_config.get("worldTitle") or "").strip()
    language_code = str(world_config.get("languageCode") or "").strip()
    category = world_config.get("category") if isinstance(world_config.get("category"), dict) else {}
    category_id = category.get("id") if isinstance(category, dict) else None
    base.update(
        {
            "worldCode": world_code,
            "worldTitle": world_title,
            "languageCode": language_code,
            "unitId": f"{world_code}-U{unit_number}",
            "unitExternalKey": f"{world_code}-U{unit_number}",
            "scormActivityExternalKey": f"{world_code}-U{unit_number}-UNITSCORM",
            "moodleCategory": category_id,
            "moodleCategorySource": category.get("source", "") if isinstance(category, dict) else "",
        }
    )

    rule = stage_rule_for_unit(world_config, unit_sequence)
    explicit_stage = first_text_value(meta.get("deploymentStageCode"), meta.get("deploymentStage"))
    source_stage = first_text_value(meta.get("sourceStage"), meta.get("stage"), meta.get("cefr"))
    source_stage_source = first_text_value(meta.get("sourceStageSource")) if source_stage else ""
    if source_stage and not source_stage_source:
        source_stage_source = "unit_metadata"
    filename_stage = filename_stage_token(root, unit_path, world_config, course_map)
    if not source_stage and filename_stage:
        source_stage = filename_stage
        source_stage_source = "package_filename"
    base["sourceStage"] = source_stage
    base["sourceStageSource"] = source_stage_source
    base["explicitDeploymentStage"] = explicit_stage

    candidates: list[dict] = []
    if rule:
        candidates.append(
            {
                "source": "course_map_rule",
                "raw": rule.get("stageCode"),
                "stage": normalize_deployment_stage(rule.get("stageCode"), course_map, world_config) or str(rule.get("stageCode") or "").strip(),
                "rule": rule,
            }
        )
    if explicit_stage:
        normalized = normalize_deployment_stage(explicit_stage, course_map, world_config)
        if normalized:
            candidates.append({"source": "explicit_deployment_stage_metadata", "raw": explicit_stage, "stage": normalized})
        else:
            base["stageResolutionMessage"] = f"Explicit deployment stage is not recognized: {explicit_stage}."
    if source_stage:
        normalized = normalize_deployment_stage(source_stage, course_map, world_config)
        if normalized:
            candidates.append({"source": source_stage_source or "source_stage_metadata", "raw": source_stage, "stage": normalized})
        elif not base["stageResolutionMessage"]:
            base["stageResolutionMessage"] = f"Source stage is not recognized: {source_stage}."

    distinct = sorted({candidate["stage"] for candidate in candidates if candidate.get("stage")})
    if len(distinct) > 1:
        source_list = ", ".join(f"{candidate['source']}={candidate['raw']}→{candidate['stage']}" for candidate in candidates)
        base.update(
            {
                "preflightStatus": PREFLIGHT_STAGE_CONFLICT,
                "stageResolutionStatus": PREFLIGHT_STAGE_CONFLICT,
                "stageResolutionSource": "conflict",
                "stageResolutionMessage": f"Deployment stage conflict for {world_code}-U{unit_number}: {source_list}.",
            }
        )
        return base

    if not distinct:
        if not base["stageResolutionMessage"]:
            base["stageResolutionMessage"] = (
                f"No authoritative deployment stage resolved for {world_code}-U{unit_number}. "
                "Add an explicit deployment stage or course-map rule before real Moodle import."
            )
        base.update(
            {
                "preflightStatus": PREFLIGHT_STAGE_UNRESOLVED,
                "stageResolutionStatus": PREFLIGHT_STAGE_UNRESOLVED,
                "stageResolutionSource": "none",
            }
        )
        return base

    deployment_stage = distinct[0]
    chosen_rule = rule if rule and normalize_deployment_stage(rule.get("stageCode"), course_map, world_config) == deployment_stage else None
    course_external_key = (
        str(chosen_rule.get("courseIdnumber"))
        if chosen_rule and chosen_rule.get("courseIdnumber")
        else f"FLW_{world_code}_{external_key_segment(deployment_stage)}"
    )
    course_shortname = (
        str(chosen_rule.get("courseShortname"))
        if chosen_rule and chosen_rule.get("courseShortname")
        else f"FLW-{world_code}-{shortname_segment(deployment_stage)}"
    )
    source_names = "+".join(candidate["source"] for candidate in candidates if candidate.get("stage") == deployment_stage)
    base.update(
        {
            "deploymentStageCode": deployment_stage,
            "preflightStatus": PREFLIGHT_RESOLVED,
            "stageResolutionStatus": PREFLIGHT_RESOLVED,
            "stageResolutionSource": source_names,
            "stageResolutionMessage": f"Resolved {world_code}-U{unit_number} to {world_code}:{deployment_stage}.",
            "courseExternalKey": course_external_key,
            "courseShortname": course_shortname,
            "courseIdnumber": course_external_key,
        }
    )
    return base


def target_metadata_item_fields(target: dict) -> dict:
    keys = [
        "manifestSchemaVersion",
        "sourceRootCode",
        "worldCode",
        "worldTitle",
        "languageCode",
        "sourceStage",
        "deploymentStageCode",
        "unitId",
        "unitNumber",
        "unitSequence",
        "unitTitle",
        "courseExternalKey",
        "unitExternalKey",
        "scormActivityExternalKey",
        "preflightStatus",
        "stageResolutionStatus",
        "stageResolutionMessage",
    ]
    return {key: target.get(key, "") for key in keys}


def export_scorm_metadata_fields(export_report: dict | None) -> dict:
    report = export_report if isinstance(export_report, dict) else {}
    keys = [
        "scormStructureVersion",
        "scormManifestIdentifier",
        "scormActivityExternalKey",
        "futureCmidNumber",
        "packageSha256",
        "packageContentSha256",
        "componentMappings",
        "microActivityMappings",
        "courseImage",
        "packageIdentifierRule",
        "scoIdentifierRule",
    ]
    return {key: report.get(key, [] if key.endswith("Mappings") else "") for key in keys if key in report}


def scorm_export_identity_mismatches(target: dict, export_report: dict | None) -> list[str]:
    report = export_report if isinstance(export_report, dict) else {}
    if not report:
        return []
    world_code = str(target.get("worldCode") or "").strip().upper()
    unit_number = parse_unit_number_option(target.get("unitNumber"))
    unit_id = str(target.get("unitId") or "").strip()
    if not unit_id and world_code and unit_number:
        unit_id = f"{world_code}-U{unit_number}"
    expected = {
        "worldCode": world_code,
        "unitId": unit_id,
        "scormActivityExternalKey": f"{unit_id}-UNITSCORM" if unit_id else "",
        "scormManifestIdentifier": f"FLW_{world_code}_U{unit_number}_SCORM12" if world_code and unit_number else "",
        "futureCmidNumber": f"FLW_{world_code}_U{unit_number}_UNITSCORM" if world_code and unit_number else "",
    }
    mismatches = []
    for field, expected_value in expected.items():
        actual_value = str(report.get(field) or "").strip()
        if expected_value and actual_value and actual_value.casefold() != expected_value.casefold():
            mismatches.append(f"{field}: expected {expected_value}, exported {actual_value}")
    return mismatches


def validate_scorm_export_identity(target: dict, export_report: dict | None) -> None:
    mismatches = scorm_export_identity_mismatches(target, export_report)
    if mismatches:
        raise AppError(
            "SCORM_EXPORT_IDENTITY_MISMATCH: Exported package identity does not match its resolved FLW Unit target. "
            + "; ".join(mismatches),
            409,
        )


def add_target_metadata(item: dict, language: dict, root: Path, unit_path: Path, unit_number: str | None, meta: dict) -> dict:
    target = resolve_deployment_target(language, root, unit_path, unit_number, meta)
    validate_scorm_export_identity(target, item.get("export"))
    item.update(target_metadata_item_fields(target))
    item["targetMetadata"] = target
    export_fields = export_scorm_metadata_fields(item.get("export"))
    if export_fields:
        item.update(export_fields)
        item["targetMetadata"].update({key: value for key, value in export_fields.items() if key not in {"componentMappings", "microActivityMappings"}})
    return item


def manifest_blocking_items(manifest: dict | None) -> list[dict]:
    if not isinstance(manifest, dict):
        return [
            {
                "preflightStatus": PREFLIGHT_INVALID_CONFIG,
                "stageResolutionMessage": "Manifest is missing or invalid.",
            }
        ]
    blocking: list[dict] = []
    for item in manifest.get("items", []) if isinstance(manifest.get("items"), list) else []:
        if item.get("status") not in {"planned", "exported"}:
            continue
        status = item.get("preflightStatus") or (item.get("targetMetadata") or {}).get("preflightStatus")
        if status in BLOCKING_PREFLIGHT_STATUSES:
            blocking.append(
                {
                    "code": item.get("code", ""),
                    "label": item.get("label", ""),
                    "unit": item.get("unit", ""),
                    "worldCode": item.get("worldCode", ""),
                    "unitId": item.get("unitId", ""),
                    "preflightStatus": status,
                    "stageResolutionMessage": item.get("stageResolutionMessage")
                    or (item.get("targetMetadata") or {}).get("stageResolutionMessage", ""),
                }
            )
    return blocking


def manifest_preflight_summary(items: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        status = item.get("preflightStatus") or (item.get("targetMetadata") or {}).get("preflightStatus") or item.get("status") or "UNKNOWN"
        counts[status] = counts.get(status, 0) + 1
    blocking = manifest_blocking_items({"items": items})
    return {
        "statusCounts": counts,
        "blockingCount": len(blocking),
        "blockingStatuses": sorted({item["preflightStatus"] for item in blocking if item.get("preflightStatus")}),
        "blockingItems": blocking[:50],
    }


def enrich_manifest_preflight(manifest: dict) -> dict:
    manifest["manifestSchemaVersion"] = 2
    manifest["preflight"] = manifest_preflight_summary(manifest.get("items", []) if isinstance(manifest.get("items"), list) else [])
    manifest["blockedForRealImport"] = bool(manifest["preflight"]["blockingCount"])
    return manifest


def enforce_manifest_preflight_for_real_import(manifest_path: Path) -> None:
    manifest = load_json_file(manifest_path)
    blocking = manifest_blocking_items(manifest)
    if blocking:
        examples = "; ".join(
            f"{item.get('unitId') or (str(item.get('code', '')) + ' U' + str(item.get('unit', '')))}: {item.get('preflightStatus')}"
            for item in blocking[:8]
        )
        extra = f" First blocking items: {examples}." if examples else ""
        raise AppError(
            f"Real Moodle import is blocked by S1 deployment preflight ({len(blocking)} item(s)).{extra} "
            "Use dry run/preview or resolve World/DeploymentStage metadata first.",
            409,
        )


def find_language_content_root(start: Path, language: dict) -> Path | None:
    containers = batch_search_containers(start)
    for container in containers:
        candidates: list[Path] = []
        if language_root_name_matches(container, language):
            candidates.append(container)
        try:
            children = [child for child in container.iterdir() if child.is_dir()]
        except OSError:
            children = []
        candidates.extend(child for child in children if language_root_name_matches(child, language))
        for candidate in candidates:
            content_root = detect_content_root(candidate)
            if content_root.exists() and content_root.is_dir() and (has_unit_dirs(content_root) or has_unit_archives(content_root)):
                try:
                    return content_root.resolve()
                except OSError:
                    return content_root.absolute()
    return None


def configured_world_source_root_status(raw_root: str | None) -> list[dict]:
    try:
        start = root_from_value(raw_root or str(default_content_root()))
    except Exception:
        start = default_content_root()
    course_map, errors = course_map_load_result()
    worlds = (course_map or {}).get("worlds", {}) if isinstance(course_map, dict) else {}
    rows: list[dict] = []
    for language in FLW_LANGUAGE_ROOTS:
        source_code = normalized_source_root_code(language.get("code"))
        world = worlds.get(source_code, {}) if isinstance(worlds, dict) else {}
        found = find_language_content_root(start, language) if start.exists() and start.is_dir() else None
        rows.append(
            {
                "code": source_code,
                "label": language.get("label", ""),
                "sourceRootCode": source_code,
                "worldCode": world.get("worldCode") or language.get("worldCode", ""),
                "worldTitle": world.get("worldTitle", ""),
                "languageCode": world.get("languageCode", ""),
                "root": str(found) if found else "",
                "unitCount": len(list_units(found)) if found else 0,
                "preflightStatus": PREFLIGHT_RESOLVED if found else PREFLIGHT_SOURCE_ROOT_NOT_FOUND,
                "configStatus": PREFLIGHT_INVALID_CONFIG if errors else PREFLIGHT_RESOLVED,
                "configErrors": errors,
            }
        )
    return rows


def language_root_name_matches(path: Path, language: dict) -> bool:
    name = path.name.strip().lower()
    strong_markers = set(language_root_markers(language))
    return any(
        name == marker or name.startswith(marker + "-") or name.startswith(marker + "_")
        for marker in strong_markers
        if marker
    )


def batch_search_containers(start: Path) -> list[Path]:
    containers: list[Path] = []
    for candidate in (start, start.parent, start.parent.parent):
        if not candidate:
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        if resolved not in containers:
            containers.append(resolved)
    return containers


def language_root_result(language: dict, selected: Path, worlds: dict) -> dict:
    world = worlds.get(normalized_source_root_code(language["code"]), {}) if isinstance(worlds, dict) else {}
    return {
        "code": language["code"],
        "label": language["label"],
        "sourceRootCode": language["code"],
        "worldCode": (world or {}).get("worldCode", language.get("worldCode", "")),
        "worldTitle": (world or {}).get("worldTitle", ""),
        "languageCode": (world or {}).get("languageCode", ""),
        "root": selected,
        "unitCount": len(list_units(selected)),
    }


def direct_selected_language_root(raw_root: str | None) -> dict | None:
    try:
        start = root_from_value(raw_root or str(default_content_root()))
    except Exception:
        return None
    if not start.exists() or not start.is_dir():
        return None
    content_root = detect_content_root(start)
    if not ((has_unit_dirs(content_root) or has_unit_archives(content_root))):
        return None
    course_map, _ = course_map_load_result()
    worlds = (course_map or {}).get("worlds", {}) if isinstance(course_map, dict) else {}
    for language in FLW_LANGUAGE_ROOTS:
        if (
            language_root_name_matches(start, language)
            or language_root_name_matches(start.parent, language)
            or language_root_name_matches(content_root.parent, language)
        ):
            return language_root_result(language, content_root, worlds)
    return None


def s7b_is_seven_world_production_scope(options: dict | None) -> bool:
    options = options or {}
    values = [
        options.get("productionScope"),
        options.get("batchProductionScope"),
        options.get("flwProductionScope"),
        options.get("s7bScope"),
    ]
    normalized = {str(value or "").strip().lower().replace("-", "_") for value in values}
    return bool(
        normalized
        & {
            S7B_SEVEN_WORLD_PRODUCTION_SCOPE,
            "seven_world",
            "7_world",
            "current_production",
            "current_7_world_production",
        }
    )


def s7b_scope_language_allowed(language: dict, options: dict | None) -> bool:
    if not s7b_is_seven_world_production_scope(options):
        return True
    return normalized_source_root_code(language.get("code") or language.get("sourceRootCode")) in S7B_PRODUCTION_WORLD_CODES


def s7b_scope_expected_unit_count(language: dict, options: dict | None) -> int:
    if not s7b_is_seven_world_production_scope(options):
        return 0
    code = normalized_source_root_code(language.get("code") or language.get("sourceRootCode"))
    return int(S7B_PRODUCTION_EXPECTED_UNIT_COUNTS.get(code, 0))


def s7b_scope_unit_allowed(language: dict, unit_number: str, options: dict | None) -> bool:
    expected = s7b_scope_expected_unit_count(language, options)
    if expected <= 0:
        return True
    return item_unit_sequence(unit_number) <= expected


def normalized_batch_world_scope(options: dict | None) -> str:
    options = options or {}
    raw = str(options.get("batchWorldScope") or "").strip().lower().replace("-", "_")
    aliases = {
        "": "legacy",
        "all": "all",
        "all_worlds": "all",
        "current": "current",
        "current_world": "current",
        "selected": "current",
        "selected_world": "current",
        "specific": "specific",
        "specific_world": "specific",
    }
    scope = aliases.get(raw)
    if not scope:
        raise AppError("Batch world selection must be all, current, or specific.")
    return scope


def batch_specific_world_code(options: dict | None) -> str:
    options = options or {}
    return normalized_source_root_code(options.get("batchSpecificWorld") or options.get("batchWorldCode"))


def batch_language_roots_for_options(raw_root: str | None, options: dict) -> list[dict]:
    scope = normalized_batch_world_scope(options)
    if scope == "current" or (scope == "legacy" and not bool(options.get("batchAllUnits", True))):
        direct = direct_selected_language_root(raw_root)
        if direct:
            if not s7b_scope_language_allowed(direct, options):
                raise AppError(
                    f"The current world '{direct.get('label') or direct.get('code')}' is outside the selected production scope.",
                    400,
                )
            return [direct]
        if scope == "current":
            raise AppError(
                "The current root is not a recognizable SmartCourses world. Select a world folder such as 04-Chinese, or choose a specific world.",
                400,
            )
    discovered = discover_batch_language_roots(raw_root)
    if scope == "specific":
        target_code = batch_specific_world_code(options)
        if not target_code:
            raise AppError("Choose a specific world for this batch export.", 400)
        matches = [
            language for language in discovered
            if normalized_source_root_code(language.get("sourceRootCode") or language.get("code")) == target_code
        ]
        if not matches:
            raise AppError(f"The selected world '{target_code}' was not found under or near the current course root.", 404)
        if not s7b_scope_language_allowed(matches[0], options):
            raise AppError(
                f"The selected world '{matches[0].get('label') or target_code}' is outside the selected production scope. Choose All configured worlds to include it.",
                400,
            )
        return matches
    return [language for language in discovered if s7b_scope_language_allowed(language, options)]


def discover_batch_language_roots(raw_root: str | None) -> list[dict]:
    start = root_from_value(raw_root or str(default_content_root()))
    if not start.exists() or not start.is_dir():
        raise AppError(f"Batch root not found: {start}", 404)
    results: list[dict] = []
    seen: set[Path] = set()
    course_map, _ = course_map_load_result()
    worlds = (course_map or {}).get("worlds", {}) if isinstance(course_map, dict) else {}

    for language in FLW_LANGUAGE_ROOTS:
        selected = find_language_content_root(start, language)
        if selected and selected not in seen:
            seen.add(selected)
            results.append(language_root_result(language, selected, worlds))

    if not results:
        known = ", ".join(language["code"] for language in FLW_LANGUAGE_ROOTS)
        raise AppError(f"No SmartCourses language roots found near {start}. Expected folders like: {known}.", 404)
    return results


def parse_unit_number_option(value) -> str | None:
    match = re.search(r"(\d{1,3})", str(value or ""))
    if not match:
        return None
    return f"{int(match.group(1)):03d}"


def batch_unit_numbers(language_roots: list[dict], options: dict) -> list[str]:
    if bool(options.get("batchAllUnits", True)):
        numbers = {
            unit["number"]
            for language in language_roots
            for unit in list_units(language["root"])
        }
        return sorted(numbers)

    start = parse_unit_number_option(options.get("batchUnitStart")) or parse_unit_number_option(options.get("unit"))
    end = parse_unit_number_option(options.get("batchUnitEnd")) or start
    if not start and end:
        start = end
    if not start or not end:
        raise AppError("Batch unit range needs a start and end unit, for example 001 to 010.")
    start_number = int(start)
    end_number = int(end)
    if start_number > end_number:
        raise AppError("Batch unit range start must be less than or equal to end.")
    return [f"{number:03d}" for number in range(start_number, end_number + 1)]


def batch_language_unit_plan(language_roots: list[dict], options: dict) -> list[dict]:
    if bool(options.get("batchAllUnits", True)):
        return [
            {
                "language": language,
                "units": [
                    unit["number"]
                    for unit in list_units(language["root"])
                    if s7b_scope_unit_allowed(language, unit["number"], options)
                ],
            }
            for language in language_roots
        ]

    unit_numbers = batch_unit_numbers(language_roots, options)
    return [{"language": language, "units": unit_numbers} for language in language_roots]


def batch_unit_pairs(language_roots: list[dict], options: dict) -> list[tuple[dict, str]]:
    return [
        (plan["language"], unit_number)
        for plan in batch_language_unit_plan(language_roots, options)
        for unit_number in plan["units"]
    ]


def batch_unit_numbers_from_plan(language_plan: list[dict]) -> list[str]:
    return sorted({unit_number for plan in language_plan for unit_number in plan["units"]})


def batch_language_roots_summary(language_plan: list[dict]) -> list[dict]:
    rows = []
    for plan in language_plan:
        language = plan["language"]
        units = plan["units"]
        rows.append(
            {
                "code": language["code"],
                "label": language["label"],
                "sourceRootCode": language.get("sourceRootCode", language["code"]),
                "worldCode": language.get("worldCode", ""),
                "worldTitle": language.get("worldTitle", ""),
                "languageCode": language.get("languageCode", ""),
                "root": str(language["root"]),
                "unitCount": language["unitCount"],
                "plannedUnitCount": len(units),
                "plannedFirstUnit": units[0] if units else "",
                "plannedLastUnit": units[-1] if units else "",
            }
        )
    return rows


def s7_language_order_index(code: str | None) -> int:
    cleaned = normalized_source_root_code(code or "")
    for index, language in enumerate(FLW_LANGUAGE_ROOTS):
        if normalized_source_root_code(language.get("code")) == cleaned:
            return index
    return len(FLW_LANGUAGE_ROOTS) + 1


def s7_stage_rank(stage_code: str | None) -> int:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(stage_code or "").upper())
    if not cleaned:
        return 999
    if cleaned in S7_STAGE_ORDER:
        return S7_STAGE_ORDER[cleaned]
    match = re.match(r"^(A1|A2|B1|B2|C1|C2)(\d+)?$", cleaned)
    if match:
        return S7_STAGE_ORDER.get(match.group(1), 900) + int(match.group(2) or 0)
    return 900


def s7_item_target(item: dict) -> dict:
    target = item.get("targetMetadata")
    return target if isinstance(target, dict) else item


def s7_unit_sort_key(item: dict) -> tuple:
    target = s7_item_target(item)
    source_code = target.get("sourceRootCode") or item.get("sourceRootCode") or item.get("code")
    unit_sequence = target.get("unitSequence") or item.get("unitSequence") or item_unit_sequence(item.get("unit"))
    try:
        unit_sequence = int(unit_sequence)
    except (TypeError, ValueError):
        unit_sequence = 999999
    return (
        s7_language_order_index(str(source_code or "")),
        s7_stage_rank(str(target.get("deploymentStageCode") or item.get("deploymentStageCode") or "")),
        unit_sequence,
        str(target.get("unitId") or item.get("unitId") or item.get("unit") or ""),
        str(item.get("unitPath") or item.get("root") or ""),
    )


def s7_batch_target_contract(item: dict, import_mode: str) -> dict:
    target = s7_item_target(item)
    export = item.get("export") if isinstance(item.get("export"), dict) else {}
    return {
        "worldCode": target.get("worldCode", item.get("worldCode", "")),
        "deploymentStageCode": target.get("deploymentStageCode", item.get("deploymentStageCode", "")),
        "unitId": target.get("unitId", item.get("unitId", "")),
        "unitSequence": target.get("unitSequence", item.get("unitSequence", "")),
        "courseExternalKey": target.get("courseExternalKey", item.get("courseExternalKey", "")),
        "unitExternalKey": target.get("unitExternalKey", item.get("unitExternalKey", "")),
        "scormActivityExternalKey": target.get("scormActivityExternalKey", item.get("scormActivityExternalKey", "")),
        "sourceRootCode": target.get("sourceRootCode", item.get("sourceRootCode", item.get("code", ""))),
        "sourceUnitPath": item.get("unitPath", ""),
        "sourceArchivePath": item.get("archivePath", ""),
        "packagePath": export.get("zipPath", item.get("packagePath", "")),
        "packageSha256": export.get("packageSha256", item.get("packageSha256", "")),
        "packageContentSha256": export.get("packageContentSha256", item.get("packageContentSha256", "")),
        "courseImage": export.get("courseImage", item.get("courseImage")),
        "mode": import_mode,
    }


def s7_stage_group_plan(items: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for item in items:
        if item.get("status") not in {"planned", "exported"}:
            continue
        target = s7_item_target(item)
        world_code = str(target.get("worldCode") or item.get("worldCode") or "").strip()
        stage_code = str(target.get("deploymentStageCode") or item.get("deploymentStageCode") or "").strip()
        course_key = str(target.get("courseExternalKey") or item.get("courseExternalKey") or "").strip()
        unit_id = str(target.get("unitId") or item.get("unitId") or "").strip()
        if not world_code or not stage_code or not course_key:
            key = (world_code or "UNRESOLVED", stage_code or "UNRESOLVED")
        else:
            key = (world_code, stage_code)
        group = groups.setdefault(
            key,
            {
                "worldCode": key[0],
                "worldTitle": target.get("worldTitle", item.get("worldTitle", "")),
                "deploymentStageCode": key[1],
                "courseExternalKey": course_key,
                "unitCount": 0,
                "unitIds": [],
                "sourceRootCodes": [],
            },
        )
        group["unitCount"] += 1
        if unit_id:
            group["unitIds"].append(unit_id)
        source_code = str(target.get("sourceRootCode") or item.get("sourceRootCode") or item.get("code") or "")
        if source_code and source_code not in group["sourceRootCodes"]:
            group["sourceRootCodes"].append(source_code)
    return sorted(
        groups.values(),
        key=lambda row: (
            s7_language_order_index((row.get("sourceRootCodes") or [""])[0]),
            s7_stage_rank(row.get("deploymentStageCode")),
            row.get("worldCode", ""),
        ),
    )


def s7_catalog_validation(language_plan: list[dict], source_root_status: list[dict], production_scope: str | None = None) -> dict:
    scoped_options = {"productionScope": production_scope or ""}
    seven_world_scope = s7b_is_seven_world_production_scope(scoped_options)
    status_by_code = {
        normalized_source_root_code(row.get("sourceRootCode") or row.get("code")): row
        for row in source_root_status
        if isinstance(row, dict)
    }
    plan_by_code = {
        normalized_source_root_code(plan["language"].get("sourceRootCode") or plan["language"].get("code")): plan
        for plan in language_plan
    }
    worlds = []
    expected_total = 0
    available_total = 0
    selected_total = 0
    missing_or_invalid_total = 0
    extra_available_total = 0
    spanish_present = False
    for language in FLW_LANGUAGE_ROOTS:
        code = normalized_source_root_code(language.get("code"))
        if seven_world_scope and code not in S7B_PRODUCTION_WORLD_CODES:
            continue
        expected = int(
            (S7B_PRODUCTION_EXPECTED_UNIT_COUNTS if seven_world_scope else S7_EXPECTED_WORLD_UNIT_COUNTS).get(code, 0)
        )
        status = status_by_code.get(code, {})
        available_source = int(status.get("unitCount") or 0)
        available_valid = min(available_source, expected) if seven_world_scope and expected else available_source
        plan = plan_by_code.get(code)
        selected = len(plan["units"]) if plan else 0
        missing_or_invalid = max(expected - available_valid, 0)
        extra_available = max(available_source - expected, 0)
        if code == "07-spanish" and available_source > 0:
            spanish_present = True
        worlds.append(
            {
                "sourceRootCode": code,
                "label": language.get("label", ""),
                "worldCode": status.get("worldCode") or language.get("worldCode", ""),
                "expected": expected,
                "availableSource": available_source,
                "availableValid": available_valid,
                "selected": selected,
                "missingOrInvalid": missing_or_invalid,
                "extraAvailable": extra_available,
                "preflightStatus": status.get("preflightStatus", PREFLIGHT_SOURCE_ROOT_NOT_FOUND),
                "root": status.get("root", ""),
            }
        )
        expected_total += expected
        available_total += available_valid
        selected_total += selected
        missing_or_invalid_total += missing_or_invalid
        extra_available_total += extra_available
    return {
        "gate": "S7B" if seven_world_scope else "S7",
        "productionScope": S7B_SEVEN_WORLD_PRODUCTION_SCOPE if seven_world_scope else "all_configured_worlds",
        "description": (
            "Seven-world production readiness excludes Spanish and caps selected Units to the scoped expected counts; extra source packages are reported."
            if seven_world_scope
            else "Expected catalog counts are validation expectations only; unavailable source Units are reported and never fabricated."
        ),
        "expectedTotal": expected_total,
        "availableValidTotal": available_total,
        "selectedTotal": selected_total,
        "missingOrInvalidTotal": missing_or_invalid_total,
        "extraAvailableTotal": extra_available_total,
        "spanishSourcePresent": spanish_present,
        "spanishReadinessStatus": "OUT_OF_SCOPE" if seven_world_scope else ("PRESENT" if spanish_present else "SOURCE_ROOT_NOT_FOUND"),
        "worlds": worlds,
    }


def s7_enrich_batch_manifest(manifest: dict, language_plan: list[dict], raw_root: str | None, import_mode: str) -> dict:
    items = manifest.get("items", []) if isinstance(manifest.get("items"), list) else []
    items = sorted(items, key=s7_unit_sort_key)
    for item in items:
        if item.get("status") in {"planned", "exported"}:
            item["batchTarget"] = s7_batch_target_contract(item, import_mode)
    manifest["items"] = items
    source_status = manifest.get("sourceRootStatus") or configured_world_source_root_status(raw_root)
    manifest["sourceRootStatus"] = source_status
    manifest["s7BatchArchitecture"] = {
        "stageCourse": "FLW World + Deployment Stage -> Moodle Course",
        "unitSection": "FLW Unit -> Moodle Section",
        "unitScorm": "1 FLW Unit -> 1 current SCORM 1.2 activity/package",
        "groupingKey": "WorldCode + DeploymentStageCode",
        "normalBatchImportModes": ["overwrite", "add_new", "clear_add"],
        "clearAddAvailableInS7NormalBatch": False,
        "s8SafeRebuildMode": "clear_add",
        "s8VisibleOperationName": "Rebuild Selected FLW Scope",
        "s8ScopeModel": "WorldCode + DeploymentStageCode + UnitID + UnitSCORMActivityID",
    }
    manifest["stageGroups"] = s7_stage_group_plan(items)
    manifest["stageGroupCount"] = len(manifest["stageGroups"])
    manifest["catalogValidation"] = s7_catalog_validation(language_plan, source_status, manifest.get("productionScope"))
    plan_payload = {
        "timestamp": manifest.get("timestamp", ""),
        "importMode": import_mode,
        "allAvailableUnits": manifest.get("allAvailableUnits"),
        "items": [item.get("batchTarget", {}) for item in items if item.get("status") in {"planned", "exported"}],
        "catalogValidation": manifest["catalogValidation"],
    }
    manifest["batchPlanId"] = hashlib.sha256(
        json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, default=json_default).encode("utf-8")
    ).hexdigest()
    manifest["batchPlanCreatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
    return enrich_manifest_preflight(manifest)


def s7_job_plan_items(manifest: dict) -> list[dict]:
    rows = []
    for item in manifest.get("items", []) if isinstance(manifest.get("items"), list) else []:
        target = s7_item_target(item)
        rows.append(
            {
                "status": item.get("status", ""),
                "code": item.get("code", target.get("sourceRootCode", "")),
                "unit": item.get("unit", target.get("unitNumber", "")),
                "worldCode": target.get("worldCode", item.get("worldCode", "")),
                "deploymentStageCode": target.get("deploymentStageCode", item.get("deploymentStageCode", "")),
                "unitId": target.get("unitId", item.get("unitId", "")),
                "unitSequence": target.get("unitSequence", item.get("unitSequence", "")),
                "courseExternalKey": target.get("courseExternalKey", item.get("courseExternalKey", "")),
                "unitExternalKey": target.get("unitExternalKey", item.get("unitExternalKey", "")),
                "scormActivityExternalKey": target.get("scormActivityExternalKey", item.get("scormActivityExternalKey", "")),
                "sourceUnitPath": item.get("unitPath", ""),
                "reason": item.get("reason", ""),
                "error": item.get("error", ""),
            }
        )
    return rows


def planned_batch_manifest(raw_root: str | None, options: dict, stamp: str) -> dict:
    language_roots = batch_language_roots_for_options(raw_root, options)
    language_plan = batch_language_unit_plan(language_roots, options)
    unit_numbers = batch_unit_numbers_from_plan(language_plan)
    import_mode = normalize_flw_import_mode(options, batch=True)
    items: list[dict] = []
    for plan in language_plan:
        language = plan["language"]
        root = language["root"]
        for unit_number in plan["units"]:
            try:
                unit_path = unit_dir(root, unit_number)
                meta = index_meta(unit_path)
                structure = scorm_structure_preview(
                    unit_path,
                    {
                        **options,
                        "root": str(root),
                        "launchFile": (options.get("launchFile") or "index.html"),
                        "title": compact_title([language["label"], f"Unit {unit_number}", meta.get("title") or unit_path.name]),
                    },
                )
                item = {
                    "code": language["code"],
                    "label": language["label"],
                    "status": "planned",
                    "unit": unit_number,
                    "unitPath": str(unit_path),
                    "root": str(root),
                    "title": compact_title([language["label"], f"Unit {unit_number}", meta.get("title") or unit_path.name]),
                    "metadata": meta,
                    "scormStructureVersion": structure.get("scormStructureVersion"),
                    "scormManifestIdentifier": structure.get("scormManifestIdentifier"),
                    "scormActivityExternalKey": structure.get("scormActivityExternalKey"),
                    "futureCmidNumber": structure.get("futureCmidNumber"),
                    "componentMappings": structure.get("componentMappings", []),
                    "microActivityMappings": structure.get("microActivityMappings", []),
                }
                items.append(add_target_metadata(item, language, root, unit_path, unit_number, meta))
            except AppError as exc:
                items.append(batch_missing_item(language, root, unit_number, str(exc)))
            except Exception as exc:
                items.append(batch_failed_item(language, root, unit_number, exc))
    manifest = {
        "kind": "smartcourses_scorm_batch_preview",
        "timestamp": stamp,
        "allAvailableUnits": bool(options.get("batchAllUnits", True)),
        "batchWorldScope": normalized_batch_world_scope(options),
        "batchSpecificWorld": batch_specific_world_code(options),
        "productionScope": S7B_SEVEN_WORLD_PRODUCTION_SCOPE if s7b_is_seven_world_production_scope(options) else "all_configured_worlds",
        "units": unit_numbers,
        "languageRoots": batch_language_roots_summary(language_plan),
        "sourceRootStatus": configured_world_source_root_status(raw_root),
        "items": items,
        "plannedCount": sum(1 for item in items if item.get("status") == "planned"),
        "missingCount": sum(1 for item in items if item.get("status") == "missing"),
        "failureCount": sum(1 for item in items if item.get("status") == "failed"),
    }
    return s7_enrich_batch_manifest(manifest, language_plan, raw_root, import_mode)


def direct_flw_manifest(root: Path, unit_path: Path, export_report: dict, stamp: str) -> dict:
    language = detect_flw_language(root, unit_path)
    unit_number = export_report.get("unit") or unit_number_from_path(unit_path)
    meta = index_meta(unit_path)
    item = {
        **language,
        "status": "exported",
        "unit": unit_number,
        "unitPath": str(unit_path),
        "root": str(root),
        "title": export_report.get("title") or meta.get("title") or unit_path.name,
        "metadata": meta,
        "validation": validate_unit(unit_path),
        "export": export_report,
    }
    item = add_target_metadata(item, language, root, unit_path, unit_number, meta)
    manifest = {
        "kind": "smartcourses_scorm_direct",
        "timestamp": stamp,
        "unit": unit_number,
        "exportDir": str(Path(export_report["zipPath"]).parent),
        "items": [item],
        "successCount": 1,
        "failureCount": 0,
    }
    return enrich_manifest_preflight(manifest)


def load_json_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def text_tail(value: str, limit: int = 20000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_flw_import(
    manifest_path: Path,
    report_path: Path,
    stamp: str,
    moodle_url: str,
    moodle_php_path: Path | None = None,
    moodle_config_path: Path | None = None,
    dry_run: bool = False,
    section_prefix: str = "SmartCourses SCORM Direct",
    name_prefix: str = "SCORM Direct",
    import_mode: str = "overwrite",
    timeout_seconds: int = 900,
    allow_nonzero_with_report: bool = False,
    expected_preview_state: str | None = None,
) -> dict:
    if not dry_run:
        enforce_manifest_preflight_for_real_import(manifest_path)
    php_path = path_from_setting(str(moodle_php_path) if moodle_php_path else None, default_moodle_php_path())
    config_path = path_from_setting(str(moodle_config_path) if moodle_config_path else None, default_moodle_config_path())
    if not php_path.exists():
        raise AppError(f"Moodle PHP was not found: {php_path}", 500)
    if not config_path.exists():
        raise AppError(f"Moodle config.php was not found: {config_path}", 500)
    if not MOODLE_IMPORT_SCRIPT.exists():
        raise AppError(f"Moodle import script was not found: {MOODLE_IMPORT_SCRIPT}", 500)

    command = [
        str(php_path),
        str(MOODLE_IMPORT_SCRIPT),
        f"--manifest={manifest_path}",
        f"--config={config_path}",
        "--by-language",
        f"--sectionname={section_prefix} {stamp}",
        f"--report={report_path}",
        f"--name-prefix={name_prefix}",
        f"--moodle-url={moodle_url}",
        f"--import-mode={import_mode}",
    ]
    if dry_run:
        command.append("--dry-run")
    expected_preview_state = str(expected_preview_state or "").strip()
    if expected_preview_state:
        command.append(f"--expect-preview-state={expected_preview_state}")

    try:
        completed = subprocess.run(
            command,
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(f"FLW import timed out after {timeout_seconds // 60} minutes.", 504) from exc

    report = load_json_file(report_path) if report_path.exists() else None
    result = {
        "returnCode": completed.returncode,
        "dryRun": dry_run,
        "importMode": import_mode,
        "moodleUrl": moodle_url,
        "moodlePhpPath": str(php_path),
        "moodleConfigPath": str(config_path),
        "manifestPath": str(manifest_path),
        "reportPath": str(report_path) if report_path.exists() else "",
        "stdout": text_tail(completed.stdout or ""),
        "stderr": text_tail(completed.stderr or ""),
        "report": report,
    }
    if completed.returncode != 0:
        if allow_nonzero_with_report and report:
            return result
        detail = (completed.stderr or completed.stdout or "").strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise AppError(f"FLW import failed with exit code {completed.returncode}. {detail}", 500)
    return result


def single_import_request_contract(manifest: dict) -> dict:
    items = manifest.get("items", []) if isinstance(manifest, dict) else []
    item = items[0] if items and isinstance(items[0], dict) else {}
    target = item.get("targetMetadata") if isinstance(item.get("targetMetadata"), dict) else item
    export = item.get("export") if isinstance(item.get("export"), dict) else {}
    return {
        "mode": "overwrite",
        "worldCode": target.get("worldCode", item.get("worldCode", "")),
        "deploymentStageCode": target.get("deploymentStageCode", item.get("deploymentStageCode", "")),
        "unitId": target.get("unitId", item.get("unitId", "")),
        "courseExternalKey": target.get("courseExternalKey", item.get("courseExternalKey", "")),
        "unitExternalKey": target.get("unitExternalKey", item.get("unitExternalKey", "")),
        "scormActivityExternalKey": target.get("scormActivityExternalKey", item.get("scormActivityExternalKey", "")),
        "packagePath": export.get("zipPath", item.get("packagePath", "")),
        "packageSha256": export.get("packageSha256", item.get("packageSha256", "")),
        "packageContentSha256": export.get("packageContentSha256", item.get("packageContentSha256", "")),
        "courseImage": export.get("courseImage", item.get("courseImage")),
    }


def single_import_lock_key(manifest: dict) -> str:
    contract = single_import_request_contract(manifest)
    parts = [
        str(contract.get("worldCode") or "UNKNOWN"),
        str(contract.get("deploymentStageCode") or "UNRESOLVED"),
        str(contract.get("unitId") or contract.get("unitExternalKey") or "UNIT"),
    ]
    return ":".join(parts)


def acquire_single_import_lock(lock_key: str) -> threading.Lock:
    with SINGLE_IMPORT_LOCKS_LOCK:
        lock = SINGLE_IMPORT_LOCKS.get(lock_key)
        if lock is None:
            lock = threading.Lock()
            SINGLE_IMPORT_LOCKS[lock_key] = lock
    if not lock.acquire(blocking=False):
        raise AppError(
            f"IMPORT_ALREADY_RUNNING: another Moodle import is already running for {lock_key}. Try again after it finishes.",
            409,
        )
    return lock


def s7_batch_lock_keys(manifest: dict) -> list[str]:
    stage_keys = {
        f"STAGE:{group.get('worldCode') or 'UNKNOWN'}:{group.get('deploymentStageCode') or 'UNRESOLVED'}"
        for group in manifest.get("stageGroups", [])
        if group.get("worldCode") or group.get("deploymentStageCode")
    }
    unit_keys = set()
    for item in manifest.get("items", []) if isinstance(manifest.get("items"), list) else []:
        if item.get("status") != "exported":
            continue
        target = s7_item_target(item)
        world_code = str(target.get("worldCode") or item.get("worldCode") or "UNKNOWN")
        stage_code = str(target.get("deploymentStageCode") or item.get("deploymentStageCode") or "UNRESOLVED")
        unit_id = str(target.get("unitId") or item.get("unitId") or item.get("unit") or "UNIT")
        unit_keys.add(f"UNIT:{world_code}:{stage_code}:{unit_id}")
    return sorted(stage_keys | unit_keys)


def acquire_s7_batch_import_locks(manifest: dict) -> list[threading.Lock]:
    acquired: list[threading.Lock] = []
    for lock_key in s7_batch_lock_keys(manifest):
        try:
            acquired.append(acquire_single_import_lock(lock_key))
        except Exception:
            for lock in reversed(acquired):
                lock.release()
            raise
    return acquired


def run_flw_course_preview(manifest_path: Path, report_path: Path, moodle_target: dict, import_mode: str = "overwrite") -> dict:
    php_path = path_from_setting(str(moodle_target.get("moodlePhpPath")), default_moodle_php_path())
    config_path = path_from_setting(str(moodle_target.get("moodleConfigPath")), default_moodle_config_path())
    moodle_url = normalize_moodle_url(str(moodle_target.get("moodleUrl") or default_moodle_url()))
    if not php_path.exists():
        raise AppError(f"Moodle PHP was not found: {php_path}", 500)
    if not config_path.exists():
        raise AppError(f"Moodle config.php was not found: {config_path}", 500)
    command = [
        str(php_path),
        str(MOODLE_IMPORT_SCRIPT),
        f"--manifest={manifest_path}",
        f"--config={config_path}",
        "--preview-courses",
        f"--report={report_path}",
        f"--moodle-url={moodle_url}",
        f"--import-mode={import_mode}",
    ]
    completed = subprocess.run(command, cwd=str(APP_DIR), capture_output=True, text=True, timeout=300)
    report = load_json_file(report_path) if report_path.exists() else None
    result = {
        "returnCode": completed.returncode,
        "importMode": import_mode,
        "moodleUrl": moodle_url,
        "moodlePhpPath": str(php_path),
        "moodleConfigPath": str(config_path),
        "manifestPath": str(manifest_path),
        "reportPath": str(report_path) if report_path.exists() else "",
        "stdout": text_tail(completed.stdout or ""),
        "stderr": text_tail(completed.stderr or ""),
        "report": report,
    }
    if completed.returncode != 0 and not report:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise AppError(f"Moodle course preview failed with exit code {completed.returncode}. {detail}", 500)
    return result


def preview_batch_flw_courses(raw_root: str | None, options: dict) -> dict:
    stamp = flw_import_stamp()
    moodle_target = moodle_target_from_options(options)
    import_mode = normalize_flw_import_mode(options, batch=True)
    base_export_dir = root_from_value(options.get("exportDir") or str(APP_DIR / "batch_previews"))
    preview_dir, export_dir_warning = ensure_writable_output_dir(
        base_export_dir / f"flw_preview_{stamp}",
        APP_DIR / "verification_exports",
        "Batch preview export",
    )
    manifest = planned_batch_manifest(raw_root, options, stamp)
    manifest["exportDir"] = str(preview_dir)
    if export_dir_warning:
        manifest["exportDirWarning"] = export_dir_warning
    manifest_path = preview_dir / "batch_course_preview_manifest.json"
    report_path = preview_dir / "batch_course_preview_report.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    preview = run_flw_course_preview(manifest_path, report_path, moodle_target, import_mode)
    return {
        "mode": "course_preview",
        "importMode": import_mode,
        "allAvailableUnits": manifest.get("allAvailableUnits", bool(options.get("batchAllUnits", True))),
        "stamp": stamp,
        "exportDir": str(preview_dir),
        "exportDirWarning": export_dir_warning,
        "manifestPath": str(manifest_path),
        "languageRoots": manifest["languageRoots"],
        "sourceRootStatus": manifest.get("sourceRootStatus", []),
        "units": manifest["units"],
        "itemCount": len(manifest["items"]),
        "plannedCount": manifest["plannedCount"],
        "missingCount": manifest["missingCount"],
        "failureCount": manifest["failureCount"],
        "batchPlanId": manifest.get("batchPlanId", ""),
        "catalogValidation": manifest.get("catalogValidation", {}),
        "stageGroups": manifest.get("stageGroups", []),
        "stageGroupCount": manifest.get("stageGroupCount", 0),
        "preflight": manifest.get("preflight", {}),
        "blockedForRealImport": manifest.get("blockedForRealImport", False),
        "preview": preview,
    }


def export_scorm_to_flw(root: Path, unit_path: Path, options: dict) -> dict:
    export_report = export_scorm(unit_path, options)
    export_zip = Path(export_report["zipPath"])
    stamp = flw_import_stamp()
    moodle_target = moodle_target_from_options(options)
    moodle_url = moodle_target["moodleUrl"]
    import_mode = normalize_flw_import_mode(options, batch=False)
    manifest = direct_flw_manifest(root, unit_path, export_report, stamp)
    contract = single_import_request_contract(manifest)
    contract["mode"] = import_mode
    manifest_path = export_zip.with_suffix(".flw_manifest.json")
    report_path = export_zip.with_suffix(".flw_import_report.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    dry_run = bool(options.get("flwDryRun"))
    lock = None
    if not dry_run:
        lock = acquire_single_import_lock(single_import_lock_key(manifest))
    try:
        import_result = run_flw_import(
            manifest_path=manifest_path,
            report_path=report_path,
            stamp=stamp,
            moodle_url=moodle_url,
            moodle_php_path=moodle_target["moodlePhpPath"],
            moodle_config_path=moodle_target["moodleConfigPath"],
            dry_run=dry_run,
            import_mode=import_mode,
            allow_nonzero_with_report=True,
            expected_preview_state=options.get("previewStateHash") or options.get("expectedPreviewStateHash"),
        )
    finally:
        if lock:
            lock.release()
    return {
        "export": export_report,
        "flw": {
            "stamp": stamp,
            "singleImportRequest": contract,
            "language": manifest["items"][0]["label"],
            "code": manifest["items"][0]["code"],
            "targetMetadata": manifest["items"][0].get("targetMetadata", {}),
            "preflight": manifest.get("preflight", {}),
            "blockedForRealImport": manifest.get("blockedForRealImport", False),
            "importMode": import_mode,
            "manifestPath": str(manifest_path),
            **import_result,
        },
    }


def batch_manifest_item(language: dict, root: Path, unit_path: Path, export_report: dict) -> dict:
    unit_number = export_report.get("unit") or unit_number_from_path(unit_path)
    meta = index_meta(unit_path)
    item = {
        "code": language["code"],
        "label": language["label"],
        "status": "exported",
        "unit": unit_number,
        "unitPath": str(unit_path),
        "root": str(root),
        "title": export_report.get("title") or meta.get("title") or unit_path.name,
        "metadata": meta,
        "validation": validate_unit(unit_path),
        "export": export_report,
    }
    return add_target_metadata(item, language, root, unit_path, unit_number, meta)


def batch_missing_item(language: dict, root: Path, unit_number: str, reason: str) -> dict:
    return {
        "code": language["code"],
        "label": language["label"],
        "status": "missing",
        "unit": unit_number,
        "root": str(root),
        "preflightStatus": PREFLIGHT_SOURCE_ROOT_NOT_FOUND if "root" in reason.lower() else "MISSING_UNIT",
        "reason": reason,
    }


def batch_failed_item(language: dict, root: Path, unit_number: str, exc: Exception) -> dict:
    return {
        "code": language["code"],
        "label": language["label"],
        "status": "failed",
        "unit": unit_number,
        "root": str(root),
        "error": str(exc),
        "class": exc.__class__.__name__,
        "traceback": traceback.format_exc(),
    }


def export_scorm_batch_to_flw(raw_root: str | None, options: dict) -> dict:
    language_roots = batch_language_roots_for_options(raw_root, options)
    language_plan = batch_language_unit_plan(language_roots, options)
    unit_numbers = batch_unit_numbers_from_plan(language_plan)
    pairs = [(plan["language"], unit_number) for plan in language_plan for unit_number in plan["units"]]
    if not pairs:
        raise AppError("No units matched the batch import selection.")

    stamp = flw_import_stamp()
    moodle_target = moodle_target_from_options(options)
    moodle_url = moodle_target["moodleUrl"]
    import_mode = normalize_flw_import_mode(options, batch=True)
    base_export_dir = root_from_value(options.get("exportDir") or str(APP_DIR / "batch_exports"))
    batch_dir, export_dir_warning = ensure_writable_output_dir(
        base_export_dir / f"flw_batch_{stamp}",
        APP_DIR / "batch_exports",
        "Batch SCORM export",
    )

    items: list[dict] = []
    exported_count = 0
    for language, unit_number in pairs:
        root = language["root"]
        try:
            unit_path = unit_dir(root, unit_number)
        except AppError as exc:
            items.append(batch_missing_item(language, root, unit_number, str(exc)))
            continue
        except Exception as exc:
            items.append(batch_failed_item(language, root, unit_number, exc))
            continue

        try:
            meta = index_meta(unit_path)
            title = compact_title([language["label"], f"Unit {unit_number}", meta.get("title") or unit_path.name])
            identifier = safe_scorm_identifier(f"FLW_SCORM_BATCH_{language['code']}_U{unit_number}_{stamp}")
            report = export_scorm(
                unit_path,
                {
                    "title": title,
                    "identifier": identifier,
                    "root": str(root),
                    "exportDir": str(batch_dir),
                    "launchFile": (options.get("launchFile") or "index.html"),
                    "includeSourceData": bool(options.get("includeSourceData")),
                    "includeTools": bool(options.get("includeTools")),
                    "includeUnitSco": bool(options.get("includeUnitSco")),
                    "keepTopNavBar": bool(options.get("keepTopNavBar")),
                    "autocomplete": bool(options.get("autocomplete", True)),
                },
            )
            items.append(batch_manifest_item(language, root, unit_path, report))
            exported_count += 1
        except Exception as exc:
            items.append(batch_failed_item(language, root, unit_number, exc))

    if exported_count == 0:
        manifest_path = batch_dir / "batch_manifest.json"
        manifest = {
            "kind": "smartcourses_scorm_batch",
            "timestamp": stamp,
            "manifestSchemaVersion": 2,
            "importMode": import_mode,
            "allAvailableUnits": bool(options.get("batchAllUnits", True)),
            "batchWorldScope": normalized_batch_world_scope(options),
            "batchSpecificWorld": batch_specific_world_code(options),
            "productionScope": S7B_SEVEN_WORLD_PRODUCTION_SCOPE if s7b_is_seven_world_production_scope(options) else "all_configured_worlds",
            "units": unit_numbers,
            "exportDir": str(batch_dir),
            "exportDirWarning": export_dir_warning,
            "items": items,
            "successCount": 0,
            "failureCount": len(items),
        }
        manifest = s7_enrich_batch_manifest(manifest, language_plan, raw_root, import_mode)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        raise AppError(f"No SCORM packages were exported. Batch manifest: {manifest_path}", 500)

    manifest = {
        "kind": "smartcourses_scorm_batch",
        "timestamp": stamp,
        "manifestSchemaVersion": 2,
        "importMode": import_mode,
        "allAvailableUnits": bool(options.get("batchAllUnits", True)),
        "batchWorldScope": normalized_batch_world_scope(options),
        "batchSpecificWorld": batch_specific_world_code(options),
        "productionScope": S7B_SEVEN_WORLD_PRODUCTION_SCOPE if s7b_is_seven_world_production_scope(options) else "all_configured_worlds",
        "units": unit_numbers,
        "exportDir": str(batch_dir),
        "exportDirWarning": export_dir_warning,
        "languageRoots": batch_language_roots_summary(language_plan),
        "sourceRootStatus": configured_world_source_root_status(raw_root),
        "items": items,
        "successCount": exported_count,
            "failureCount": sum(1 for item in items if item.get("status") not in {"exported", "missing"}),
            "missingCount": sum(1 for item in items if item.get("status") == "missing"),
        }
    manifest = s7_enrich_batch_manifest(manifest, language_plan, raw_root, import_mode)
    manifest_path = batch_dir / "batch_manifest.json"
    report_path = batch_dir / "batch_flw_import_report.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    dry_run = bool(options.get("flwDryRun", True))
    expected_rebuild_preview = s8_expected_rebuild_preview_hash(options)
    if s8_is_safe_rebuild_mode(import_mode) and not dry_run and not expected_rebuild_preview:
        raise AppError(
            "PREVIEW_REQUIRED: Run Rebuild Selected FLW Scope with Dry run only first, then execute the real rebuild from that preview.",
            409,
        )
    locks: list[threading.Lock] = []
    if not dry_run:
        locks = acquire_s7_batch_import_locks(manifest)
    try:
        import_result = run_flw_import(
            manifest_path=manifest_path,
            report_path=report_path,
            stamp=stamp,
            moodle_url=moodle_url,
            moodle_php_path=moodle_target["moodlePhpPath"],
            moodle_config_path=moodle_target["moodleConfigPath"],
            dry_run=dry_run,
            section_prefix="SmartCourses SCORM Batch",
            name_prefix="SCORM Batch",
            import_mode=import_mode,
            timeout_seconds=7200,
            allow_nonzero_with_report=True,
            expected_preview_state=expected_rebuild_preview,
        )
    finally:
        for lock in reversed(locks):
            lock.release()
    return {
        "mode": "batch",
        "stamp": stamp,
        "importMode": import_mode,
        "allAvailableUnits": bool(options.get("batchAllUnits", True)),
        "batchWorldScope": normalized_batch_world_scope(options),
        "batchSpecificWorld": batch_specific_world_code(options),
        "moodleUrl": moodle_url,
        "exportDir": str(batch_dir),
        "exportDirWarning": export_dir_warning,
        "manifestPath": str(manifest_path),
        "languageRoots": manifest["languageRoots"],
        "sourceRootStatus": manifest.get("sourceRootStatus", []),
        "units": unit_numbers,
        "itemCount": len(items),
        "exportedCount": exported_count,
        "missingCount": manifest["missingCount"],
        "exportFailedCount": manifest["failureCount"],
        "dryRun": dry_run,
        "batchPlanId": manifest.get("batchPlanId", ""),
        "catalogValidation": manifest.get("catalogValidation", {}),
        "stageGroups": manifest.get("stageGroups", []),
        "stageGroupCount": manifest.get("stageGroupCount", 0),
        "preflight": manifest.get("preflight", {}),
        "blockedForRealImport": manifest.get("blockedForRealImport", False),
        "flw": {
            "manifestPath": str(manifest_path),
            **import_result,
        },
    }


def batch_job_dir(job_id: str) -> Path:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", job_id).strip("._-")
    if not cleaned:
        raise AppError("Missing batch job id")
    return BATCH_JOBS_DIR / cleaned


def batch_job_path(job_id: str) -> Path:
    return batch_job_dir(job_id) / "job.json"


def public_batch_job_snapshot_unlocked(job: dict) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in list(job.items())
        if key not in BATCH_JOB_PRIVATE_KEYS
    }


def public_batch_job(job: dict) -> dict:
    with BATCH_JOBS_LOCK:
        return public_batch_job_snapshot_unlocked(job)


def save_batch_job(job: dict) -> None:
    snapshot = public_batch_job(job)
    path = batch_job_path(snapshot["jobId"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")


def remember_batch_job(job: dict) -> None:
    with BATCH_JOBS_LOCK:
        existing = BATCH_JOBS.get(job["jobId"], {})
        stored = public_batch_job_snapshot_unlocked(job)
        for key in BATCH_JOB_PRIVATE_KEYS:
            if existing.get(key):
                stored[key] = existing[key]
            elif job.get(key):
                stored[key] = job[key]
        BATCH_JOBS[job["jobId"]] = stored
    save_batch_job(stored)


def load_batch_job(job_id: str) -> dict:
    with BATCH_JOBS_LOCK:
        job = BATCH_JOBS.get(job_id)
        if job:
            return job
    path = batch_job_path(job_id)
    if not path.exists():
        raise AppError(f"Batch job was not found: {job_id}", 404)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AppError(f"Batch job file is invalid: {job_id}", 500)
    with BATCH_JOBS_LOCK:
        BATCH_JOBS[job_id] = data
    return data


def update_batch_job(job_id: str, **patch) -> dict:
    load_batch_job(job_id)
    with BATCH_JOBS_LOCK:
        job = BATCH_JOBS.get(job_id)
        if not job:
            raise AppError(f"Batch job was not found: {job_id}", 404)
        private_values = {key: job[key] for key in BATCH_JOB_PRIVATE_KEYS if key in job}
        stored = public_batch_job_snapshot_unlocked(job)
        stored.update(copy.deepcopy(patch))
        stored["updatedAt"] = dt.datetime.now().isoformat(timespec="seconds")
        stored.update(private_values)
        BATCH_JOBS[job_id] = stored
        result = dict(stored)
    save_batch_job(stored)
    return result


def exported_item_is_reusable(item: dict) -> bool:
    if item.get("status") != "exported":
        return False
    if int(item.get("manifestSchemaVersion") or 0) < 2 or not item.get("targetMetadata"):
        return False
    target = item.get("targetMetadata") if isinstance(item.get("targetMetadata"), dict) else item
    if scorm_export_identity_mismatches(target, item.get("export")):
        return False
    zip_path = item.get("export", {}).get("zipPath")
    return bool(zip_path and Path(zip_path).exists())


def process_is_running(process_id: int | str | None) -> bool:
    try:
        pid = int(process_id or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except (OSError, PermissionError):
        return False
    return True


def last_nonempty_log_line(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        if line.strip():
            return line.strip()
    return ""


def reconcile_stale_batch_jobs() -> list[dict]:
    recovered: list[dict] = []
    if not BATCH_JOBS_DIR.exists():
        return recovered
    for directory in sorted(path for path in BATCH_JOBS_DIR.iterdir() if path.is_dir()):
        job_path = directory / "job.json"
        if not job_path.exists():
            continue
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(job.get("status") or "").strip().lower()
        if not status or status in BATCH_TERMINAL_STATUSES:
            continue
        previous_pid = int(job.get("processId") or 0)
        if previous_pid and process_is_running(previous_pid):
            continue
        items = job.get("items") if isinstance(job.get("items"), list) else []
        reusable_count = sum(1 for item in items if exported_item_is_reusable(item))
        expected_count = int(job.get("itemCount") or len(items) or 0)
        manifest_path = Path(str(job.get("manifestPath") or "")) if job.get("manifestPath") else None
        stdout_path = manifest_path.with_name("moodle_import_stdout.log") if manifest_path else directory / "moodle_import_stdout.log"
        last_output = last_nonempty_log_line(stdout_path)
        job.update(
            {
                "status": "interrupted",
                "phase": "interrupted",
                "updatedAt": dt.datetime.now().isoformat(timespec="seconds"),
                "interruptedAt": dt.datetime.now().isoformat(timespec="seconds"),
                "interruptionReason": "EDITOR_BACKEND_PROCESS_ENDED",
                "error": "The Course Editor backend ended before the Moodle importer returned a final report.",
                "current": "Moodle import was interrupted. Resume will re-check Moodle and reuse existing SCORM packages.",
                "lastProcessId": previous_pid,
                "processId": 0,
                "lastImporterOutput": last_output,
                "canResume": True,
                "resumeReusableExportCount": reusable_count,
                "resumeRequiresExportCount": max(0, expected_count - reusable_count),
                "resumeWillReuseAllExports": bool(expected_count and reusable_count == expected_count),
            }
        )
        job_path.write_text(json.dumps(job, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
        with BATCH_JOBS_LOCK:
            BATCH_JOBS[job["jobId"]] = job
        recovered.append(
            {
                "jobId": job.get("jobId", directory.name),
                "previousStatus": status,
                "previousProcessId": previous_pid,
                "reusableExportCount": reusable_count,
                "expectedCount": expected_count,
            }
        )
    return recovered


def comparable_path_text(value) -> str:
    return str(value or "").strip().replace("\\", "/").rstrip("/").casefold()


def completed_dry_run_options_match(job: dict, options: dict) -> bool:
    old_options = job.get("options") or {}
    if comparable_path_text(job.get("root") or old_options.get("root")) != comparable_path_text(options.get("root")):
        return False
    bool_fields = {
        "batchAllUnits": True,
        "includeSourceData": False,
        "includeTools": False,
        "includeUnitSco": False,
        "keepTopNavBar": False,
        "autocomplete": True,
    }
    for field, default in bool_fields.items():
        if bool(old_options.get(field, default)) != bool(options.get(field, default)):
            return False
    text_fields = (
        "batchUnitStart",
        "batchUnitEnd",
        "batchFlwImportMode",
        "batchProductionScope",
        "batchWorldScope",
        "batchSpecificWorld",
        "launchFile",
    )
    for field in text_fields:
        if str(old_options.get(field) or "").strip() != str(options.get(field) or "").strip():
            return False
    return True


def completed_dry_run_exports_can_be_promoted(job: dict, options: dict) -> bool:
    return (
        job.get("status") == "complete"
        and bool((job.get("options") or {}).get("flwDryRun", True))
        and not bool(options.get("flwDryRun", True))
        and completed_dry_run_options_match(job, options)
        and any(exported_item_is_reusable(item) for item in job.get("items", []))
    )


def promotable_completed_dry_run_summary(job: dict) -> dict:
    return {
        "jobId": job.get("jobId", ""),
        "status": job.get("status", ""),
        "phase": job.get("phase", ""),
        "root": job.get("root", ""),
        "exportDir": job.get("exportDir", ""),
        "exportedCount": int(job.get("exportedCount") or 0),
        "itemCount": int(job.get("itemCount") or 0),
        "importMode": job.get("importMode", ""),
        "createdAt": job.get("createdAt", ""),
        "updatedAt": job.get("updatedAt", ""),
    }


def find_promotable_completed_dry_run_job(raw_root: str | None, options: dict) -> dict | None:
    candidate_options = {**options, "root": str(options.get("root") or raw_root or ""), "flwDryRun": False}
    if not BATCH_JOBS_DIR.exists():
        return None
    for directory in sorted((path for path in BATCH_JOBS_DIR.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
        path = directory / "job.json"
        if not path.exists():
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if completed_dry_run_exports_can_be_promoted(job, candidate_options):
            return promotable_completed_dry_run_summary(job)
    return None


def run_flw_import_for_job(
    job_id: str,
    manifest_path: Path,
    report_path: Path,
    stamp: str,
    moodle_target: dict,
    dry_run: bool,
    import_mode: str,
    expected_preview_state: str | None = None,
) -> dict:
    if not dry_run:
        enforce_manifest_preflight_for_real_import(manifest_path)
    php_path = path_from_setting(str(moodle_target.get("moodlePhpPath")), default_moodle_php_path())
    config_path = path_from_setting(str(moodle_target.get("moodleConfigPath")), default_moodle_config_path())
    moodle_url = normalize_moodle_url(str(moodle_target.get("moodleUrl") or default_moodle_url()))
    if not php_path.exists():
        raise AppError(f"Moodle PHP was not found: {php_path}", 500)
    if not config_path.exists():
        raise AppError(f"Moodle config.php was not found: {config_path}", 500)
    command = [
        str(php_path),
        str(MOODLE_IMPORT_SCRIPT),
        f"--manifest={manifest_path}",
        f"--config={config_path}",
        "--by-language",
        f"--sectionname=SmartCourses SCORM Batch {stamp}",
        f"--report={report_path}",
        "--name-prefix=SCORM Batch",
        f"--moodle-url={moodle_url}",
        f"--import-mode={import_mode}",
    ]
    if dry_run:
        command.append("--dry-run")
    expected_preview_state = str(expected_preview_state or "").strip()
    if expected_preview_state:
        command.append(f"--expect-preview-state={expected_preview_state}")

    stdout_path = manifest_path.with_name("moodle_import_stdout.log")
    stderr_path = manifest_path.with_name("moodle_import_stderr.log")
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr_file:
        process = subprocess.Popen(command, cwd=str(APP_DIR), stdout=stdout_file, stderr=stderr_file, text=True)
        update_batch_job(
            job_id,
            processId=process.pid,
            importStartedAt=dt.datetime.now().isoformat(timespec="seconds"),
            stdoutLogPath=str(stdout_path),
            stderrLogPath=str(stderr_path),
        )
        with BATCH_JOBS_LOCK:
            if job_id in BATCH_JOBS:
                BATCH_JOBS[job_id]["process"] = process
        cancel_requested_during_import = False
        last_importer_output = ""
        while True:
            return_code = process.poll()
            job = load_batch_job(job_id)
            current_importer_output = last_nonempty_log_line(stdout_path)
            if current_importer_output and current_importer_output != last_importer_output:
                last_importer_output = current_importer_output
                update_batch_job(
                    job_id,
                    current=f"Moodle import: {current_importer_output}",
                    lastImporterOutput=current_importer_output,
                    importLogUpdatedAt=dt.datetime.now().isoformat(timespec="seconds"),
                )
            if job.get("cancelRequested"):
                if not cancel_requested_during_import:
                    cancel_requested_during_import = True
                    update_batch_job(
                        job_id,
                        phase="cancelling",
                        cancelPolicy="Moodle mutation already started; not terminating PHP process mid-import.",
                    )
            if return_code is not None:
                break
            time.sleep(0.5)

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    report = load_json_file(report_path) if report_path.exists() else None
    return {
        "returnCode": return_code,
        "cancelRequestedDuringImport": cancel_requested_during_import,
        "dryRun": dry_run,
        "importMode": import_mode,
        "expectedPreviewStateHash": expected_preview_state,
        "moodleUrl": moodle_url,
        "moodlePhpPath": str(php_path),
        "moodleConfigPath": str(config_path),
        "manifestPath": str(manifest_path),
        "reportPath": str(report_path) if report_path.exists() else "",
        "stdoutLogPath": str(stdout_path),
        "stderrLogPath": str(stderr_path),
        "stdout": text_tail(stdout or ""),
        "stderr": text_tail(stderr or ""),
        "report": report,
    }


def run_batch_job(job_id: str) -> None:
    try:
        job = update_batch_job(job_id, status="running", phase="planning", error="")
        options = job["options"]
        raw_root = job.get("root")
        stamp = job.get("stamp") or flw_import_stamp()
        moodle_target = moodle_target_from_options(options)
        import_mode = normalize_flw_import_mode(options, batch=True)
        base_export_dir = root_from_value(options.get("exportDir") or str(APP_DIR / "batch_exports"))
        preferred_batch_dir = Path(job.get("exportDir") or (base_export_dir / f"flw_batch_job_{job_id}"))
        batch_dir, export_dir_warning = ensure_writable_output_dir(
            preferred_batch_dir,
            APP_DIR / "batch_exports",
            "Batch SCORM export",
        )

        language_roots = batch_language_roots_for_options(raw_root, options)
        language_plan = batch_language_unit_plan(language_roots, options)
        unit_numbers = batch_unit_numbers_from_plan(language_plan)
        preflight_manifest = planned_batch_manifest(raw_root, options, stamp)
        language_by_code = {plan["language"]["code"]: plan["language"] for plan in language_plan}
        pairs = []
        for planned in preflight_manifest.get("items", []):
            code = planned.get("code")
            unit_number = planned.get("unit")
            if code in language_by_code and unit_number:
                pairs.append((language_by_code[code], unit_number))
        if not pairs:
            pairs = [(plan["language"], unit_number) for plan in language_plan for unit_number in plan["units"]]
        old_items = {
            (item.get("code"), item.get("unit")): item
            for item in job.get("items", [])
            if item.get("code") and item.get("unit")
        }
        reuse_completed_dry_run_exports = bool(job.get("reuseCompletedDryRunExports") or options.get("reuseCompletedDryRunExports"))
        reuse_interrupted_exports = bool(job.get("reuseInterruptedExports"))
        reuse_prior_exports = reuse_completed_dry_run_exports or reuse_interrupted_exports
        if reuse_prior_exports:
            missing_reusable = [
                f"{language['label']} U{unit_number}"
                for language, unit_number in pairs
                if not exported_item_is_reusable(old_items.get((language["code"], unit_number), {}))
            ]
            if missing_reusable:
                sample = ", ".join(missing_reusable[:10])
                more = f" and {len(missing_reusable) - 10} more" if len(missing_reusable) > 10 else ""
                raise AppError(
                    "Cannot start import-only batch: previously exported ZIPs are missing or stale for "
                    f"{len(missing_reusable)} unit(s): {sample}{more}. Run Batch Deploy with Dry run only again.",
                    409,
                )
        items: list[dict] = []
        processed = 0
        exported_count = 0
        update_batch_job(
            job_id,
            stamp=stamp,
            exportDir=str(batch_dir),
            exportDirWarning=export_dir_warning,
            languageRoots=batch_language_roots_summary(language_plan),
            sourceRootStatus=configured_world_source_root_status(raw_root),
            units=unit_numbers,
            allAvailableUnits=bool(options.get("batchAllUnits", True)),
            itemCount=len(pairs),
            importMode=import_mode,
            s8RebuildMode=s8_is_safe_rebuild_mode(import_mode),
            visibleOperationName="Rebuild Selected FLW Scope" if s8_is_safe_rebuild_mode(import_mode) else "",
            batchPlanId=preflight_manifest.get("batchPlanId", ""),
            batchPlanCreatedAt=preflight_manifest.get("batchPlanCreatedAt", ""),
            plannedItems=s7_job_plan_items(preflight_manifest),
            stageGroups=preflight_manifest.get("stageGroups", []),
            stageGroupCount=preflight_manifest.get("stageGroupCount", 0),
            catalogValidation=preflight_manifest.get("catalogValidation", {}),
            preflight=preflight_manifest.get("preflight", {}),
            blockedForRealImport=preflight_manifest.get("blockedForRealImport", False),
            processedCount=0,
            exportedCount=0,
            missingCount=0,
            exportFailedCount=0,
            phase="reusing_exports" if reuse_prior_exports else "exporting",
            current=(
                "Reusing interrupted-job SCORM packages; preparing Moodle import."
                if reuse_interrupted_exports
                else "Reusing completed dry-run SCORM packages; preparing Moodle import."
                if reuse_completed_dry_run_exports
                else ""
            ),
        )

        if reuse_prior_exports:
            for language, unit_number in pairs:
                item = copy.deepcopy(old_items[(language["code"], unit_number)])
                item["resumeState"] = (
                    "REUSED_INTERRUPTED_JOB_EXPORT"
                    if reuse_interrupted_exports
                    else "REUSED_COMPLETED_DRY_RUN_EXPORT"
                )
                item["batchTarget"] = s7_batch_target_contract(item, import_mode)
                items.append(item)
            processed = len(items)
            exported_count = sum(1 for row in items if row.get("status") == "exported")
            update_batch_job(
                job_id,
                current=(
                    "Interrupted-job SCORM packages reused; restarting Moodle import idempotently."
                    if reuse_interrupted_exports
                    else "Completed dry-run SCORM packages reused; starting Moodle import."
                ),
                processedCount=processed,
                exportedCount=exported_count,
                missingCount=sum(1 for row in items if row.get("status") == "missing"),
                exportFailedCount=sum(1 for row in items if row.get("status") == "failed"),
                items=items,
                phase="importing",
            )
        for language, unit_number in ([] if reuse_prior_exports else pairs):
            current_label = f"{language['label']} U{unit_number}"
            if load_batch_job(job_id).get("cancelRequested"):
                update_batch_job(job_id, status="canceled", phase="canceled", current=current_label, items=items)
                return

            previous = old_items.get((language["code"], unit_number))
            if previous and exported_item_is_reusable(previous):
                item = copy.deepcopy(previous)
                item["resumeState"] = "REUSED_EXPORTED_PACKAGE"
                item["batchTarget"] = s7_batch_target_contract(item, import_mode)
            else:
                root = language["root"]
                try:
                    unit_path = unit_dir(root, unit_number)
                except AppError as exc:
                    item = batch_missing_item(language, root, unit_number, str(exc))
                except Exception as exc:
                    item = batch_failed_item(language, root, unit_number, exc)
                else:
                    try:
                        meta = index_meta(unit_path)
                        title = compact_title([language["label"], f"Unit {unit_number}", meta.get("title") or unit_path.name])
                        identifier = safe_scorm_identifier(f"FLW_SCORM_BATCH_{language['code']}_U{unit_number}_{stamp}")
                        report = export_scorm(
                            unit_path,
                            {
                                "title": title,
                                "identifier": identifier,
                                "root": str(root),
                                "exportDir": str(batch_dir),
                                "launchFile": (options.get("launchFile") or "index.html"),
                                "includeSourceData": bool(options.get("includeSourceData")),
                                "includeTools": bool(options.get("includeTools")),
                                "includeUnitSco": bool(options.get("includeUnitSco")),
                                "keepTopNavBar": bool(options.get("keepTopNavBar")),
                                "autocomplete": bool(options.get("autocomplete", True)),
                            },
                        )
                        item = batch_manifest_item(language, root, unit_path, report)
                    except Exception as exc:
                        item = batch_failed_item(language, root, unit_number, exc)
            items.append(item)
            processed += 1
            exported_count = sum(1 for row in items if row.get("status") == "exported")
            update_batch_job(
                job_id,
                current=current_label,
                processedCount=processed,
                exportedCount=exported_count,
                missingCount=sum(1 for row in items if row.get("status") == "missing"),
                exportFailedCount=sum(1 for row in items if row.get("status") == "failed"),
                items=items,
            )

        if exported_count == 0:
            update_batch_job(job_id, status="failed", phase="failed", error="No SCORM packages were exported.", items=items)
            return

        manifest = {
            "kind": "smartcourses_scorm_batch_job",
            "timestamp": stamp,
            "manifestSchemaVersion": 2,
            "importMode": import_mode,
            "allAvailableUnits": bool(options.get("batchAllUnits", True)),
            "productionScope": S7B_SEVEN_WORLD_PRODUCTION_SCOPE if s7b_is_seven_world_production_scope(options) else "all_configured_worlds",
            "units": unit_numbers,
            "exportDir": str(batch_dir),
            "exportDirWarning": export_dir_warning,
            "languageRoots": load_batch_job(job_id).get("languageRoots", []),
            "sourceRootStatus": load_batch_job(job_id).get("sourceRootStatus", []),
            "items": items,
            "successCount": exported_count,
            "failureCount": sum(1 for item in items if item.get("status") == "failed"),
            "missingCount": sum(1 for item in items if item.get("status") == "missing"),
        }
        manifest = s7_enrich_batch_manifest(manifest, language_plan, raw_root, import_mode)
        manifest_path = batch_dir / "batch_manifest.json"
        report_path = batch_dir / "batch_flw_import_report.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if load_batch_job(job_id).get("cancelRequested"):
            update_batch_job(
                job_id,
                status="canceled",
                phase="canceled",
                current="Cancellation honored before Moodle mutation started.",
                manifestPath=str(manifest_path),
                flwReportPath=str(report_path),
                items=items,
            )
            return
        update_batch_job(
            job_id,
            phase="importing",
            manifestPath=str(manifest_path),
            flwReportPath=str(report_path),
            batchPlanId=manifest.get("batchPlanId", ""),
            stageGroups=manifest.get("stageGroups", []),
            stageGroupCount=manifest.get("stageGroupCount", 0),
            catalogValidation=manifest.get("catalogValidation", {}),
            preflight=manifest.get("preflight", {}),
            blockedForRealImport=manifest.get("blockedForRealImport", False),
        )

        dry_run = bool(options.get("flwDryRun", True))
        expected_rebuild_preview = s8_expected_rebuild_preview_hash(options)
        if s8_is_safe_rebuild_mode(import_mode) and not dry_run and not expected_rebuild_preview:
            raise AppError(
                "PREVIEW_REQUIRED: Run Rebuild Selected FLW Scope with Dry run only first, then execute the real rebuild from that preview.",
                409,
            )
        locks: list[threading.Lock] = []
        if not dry_run:
            locks = acquire_s7_batch_import_locks(manifest)
        try:
            import_result = run_flw_import_for_job(
                job_id=job_id,
                manifest_path=manifest_path,
                report_path=report_path,
                stamp=stamp,
                moodle_target=moodle_target,
                dry_run=dry_run,
                import_mode=import_mode,
                expected_preview_state=expected_rebuild_preview,
            )
        finally:
            for lock in reversed(locks):
                lock.release()
        if import_result.get("canceled"):
            update_batch_job(job_id, status="canceled", phase="canceled", flw=import_result)
            return
        summary = (import_result.get("report") or {}).get("summary") or {}
        failed = int(summary.get("failed") or 0) + sum(1 for item in items if item.get("status") == "failed")
        status = "completed_with_issues" if failed else "complete"
        update_batch_job(
            job_id,
            status=status,
            phase="complete",
            cancelResult=(
                "Cancel was requested after Moodle mutation started; import was allowed to finish safely."
                if import_result.get("cancelRequestedDuringImport")
                else ""
            ),
            flw=import_result,
        )
    except Exception as exc:
        update_batch_job(job_id, status="failed", phase="failed", error=str(exc), traceback=traceback.format_exc())


def start_batch_job(raw_root: str | None, options: dict, resume_job_id: str | None = None) -> dict:
    import_mode = normalize_flw_import_mode(options, batch=True)
    if resume_job_id:
        job = load_batch_job(resume_job_id)
        previous_status = str(job.get("status") or "").strip().lower()
        promote_completed_dry_run = completed_dry_run_exports_can_be_promoted(job, options)
        if job.get("status") == "complete" and not promote_completed_dry_run:
            raise AppError(f"Batch job already completed successfully; there is nothing to resume: {resume_job_id}", 409)
        if job.get("status") not in BATCH_TERMINAL_STATUSES:
            thread = job.get("thread")
            if thread and hasattr(thread, "is_alive") and thread.is_alive():
                raise AppError(f"Batch job is already active: {resume_job_id}")
        old_options = copy.deepcopy(job.get("options") or {})
        resume_interrupted = previous_status == "interrupted"
        job["cancelRequested"] = False
        job["status"] = "queued"
        job["phase"] = "queued"
        job["error"] = ""
        if resume_interrupted:
            import_mode = normalize_flw_import_mode(old_options, batch=True)
            job["options"] = old_options
        else:
            job["options"] = {**old_options, **options}
        job["importMode"] = import_mode
        job["reuseCompletedDryRunExports"] = promote_completed_dry_run
        reusable_count = sum(1 for item in job.get("items", []) if exported_item_is_reusable(item))
        expected_count = int(job.get("itemCount") or len(job.get("items", [])) or 0)
        job["reuseInterruptedExports"] = bool(
            resume_interrupted and expected_count and reusable_count == expected_count
        )
        job["resumedFromStatus"] = previous_status
        job["resumeReusableExportCount"] = reusable_count
        job["canResume"] = False
        job_id = resume_job_id
    else:
        job_id = f"{now_stamp()}_{uuid.uuid4().hex[:8]}"
        job = {
            "jobId": job_id,
            "status": "queued",
            "phase": "queued",
            "createdAt": dt.datetime.now().isoformat(timespec="seconds"),
            "updatedAt": dt.datetime.now().isoformat(timespec="seconds"),
            "root": str(raw_root or ""),
            "options": options,
            "importMode": import_mode,
            "cancelRequested": False,
            "reuseCompletedDryRunExports": False,
            "reuseInterruptedExports": False,
            "processedCount": 0,
            "itemCount": 0,
            "items": [],
        }
    remember_batch_job(job)
    thread = threading.Thread(target=run_batch_job, args=(job_id,), daemon=False)
    with BATCH_JOBS_LOCK:
        BATCH_JOBS[job_id]["thread"] = thread
    thread.start()
    return public_batch_job(load_batch_job(job_id))


def cancel_batch_job(job_id: str) -> dict:
    job = update_batch_job(job_id, cancelRequested=True)
    process = job.get("process")
    if process and hasattr(process, "terminate") and job.get("phase") not in {"importing", "cancelling"}:
        try:
            process.terminate()
        except OSError:
            pass
    elif process and job.get("phase") in {"importing", "cancelling"}:
        update_batch_job(
            job_id,
            phase="cancelling",
            cancelPolicy="Moodle mutation is in progress; the backend will not terminate it mid-import.",
        )
    return public_batch_job(load_batch_job(job_id))


def export_scorm(unit_path: Path, options: dict) -> dict:
    meta = index_meta(unit_path)
    title = (options.get("title") or meta.get("title") or unit_path.name).strip()
    unit_number = unit_number_from_path(unit_path)
    unit_identity = scorm_identity_context(unit_path, options)
    requested_identifier = str(options.get("identifier") or "").strip()
    identifier = unit_identity["scormManifestIdentifier"]
    launch_file = (options.get("launchFile") or "index.html").replace("\\", "/").lstrip("/")
    include_source_data = bool(options.get("includeSourceData"))
    include_tools = bool(options.get("includeTools"))
    keep_top_nav_bar = bool(options.get("keepTopNavBar"))
    export_dir = root_from_value(options.get("exportDir") or str(unit_path.parent / "scorm_exports"))
    export_dir, export_dir_warning = ensure_writable_output_dir(
        export_dir,
        APP_DIR / "scorm_exports",
        "SCORM export",
    )
    if not (unit_path / launch_file).exists():
        raise AppError(f"Launch file not found: {launch_file}")

    with tempfile.TemporaryDirectory(prefix=f"flw_scorm_{unit_number}_") as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir(parents=True, exist_ok=True)
        copy_for_export(unit_path, stage, include_source_data, include_tools)
        course_image = first_unit_course_image(stage, launch_file)
        scorm_dir = stage / "assets" / "scorm"
        scorm_dir.mkdir(parents=True, exist_ok=True)
        (scorm_dir / "scorm_api.js").write_text(SCORM_JS, encoding="utf-8")

        scorm_config = {
            "statusOnLaunch": options.get("statusOnLaunch") or "incomplete",
            "completeStatus": options.get("completeStatus") or "completed",
            "scoreOnComplete": int(options.get("scoreOnComplete") or 100),
            "completeAfterMs": int(options.get("completeAfterMs") or 1500),
            "autocomplete": bool(options.get("autocomplete", True)),
        }
        injected = inject_scorm_script(stage / launch_file, scorm_config)
        top_nav_style_injected = inject_top_nav_hide_style(stage / launch_file, keep_top_nav_bar)
        lessons = unit_lessons(unit_path)
        source_html = read_text(stage / launch_file)
        structured_unit_data = bool(find_json_object_span(source_html, "window.UNIT_DATA="))
        if structured_unit_data:
            unit_data = extract_json_object(source_html, "window.UNIT_DATA=")
            fixed_sections = unit_fixed_sections(unit_data)
            opening_section_scos = [
                create_fixed_section_launch(stage, title, section, source_html, unit_data, unit_identity, keep_top_nav_bar)
                for section in fixed_sections
                if section["section"] == "words"
            ]
            lesson_scos = create_lesson_launches(
                stage,
                launch_file,
                title,
                lessons,
                source_html=source_html,
                unit_data=unit_data,
                unit_identity=unit_identity,
                keep_top_nav_bar=keep_top_nav_bar,
            )
            closing_section_scos = [
                create_fixed_section_launch(stage, title, section, source_html, unit_data, unit_identity, keep_top_nav_bar)
                for section in fixed_sections
                if section["section"] != "words"
            ]
            content_scos = opening_section_scos + lesson_scos + closing_section_scos
        else:
            lesson_scos = []
            unit_data = {}
            content_scos = create_generic_section_launches(stage, title, source_html, unit_identity=unit_identity, keep_top_nav_bar=keep_top_nav_bar)
        lesson_focus_injected = False
        include_unit_sco = bool(options.get("includeUnitSco")) or not content_scos
        flw_navigator_enabled = bool(options.get("flwNavigator", True))
        flw_navigator_injected_count = 0
        if flw_navigator_enabled and content_scos:
            for sco in content_scos:
                nav_config = flw_navigator_config(unit_identity, title, content_scos, sco)
                if inject_flw_navigator_file(stage / sco["launchFile"], scorm_config, nav_config):
                    flw_navigator_injected_count += 1
        elif include_unit_sco:
            unit_sco = unit_sco_identity(unit_identity, title)
            unit_sco["launchFile"] = launch_file
            unit_nav_config = flw_navigator_config(unit_identity, title, [unit_sco], unit_sco)
            if inject_flw_navigator_file(stage / launch_file, scorm_config, unit_nav_config):
                flw_navigator_injected_count += 1

        files = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
        shared_files = [path for path in files if not path.startswith("scos/") and path != launch_file]
        for sco in content_scos:
            sco["files"] = sorted(set(shared_files + [sco["launchFile"]]))
        manifest = manifest_xml(identifier, title, launch_file, files, content_scos, include_unit_sco, unit_identity)
        (stage / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
        component_mappings = component_mappings_from_scos(content_scos, unit_identity)
        micro_activity_mappings = micro_activity_mappings_from_unit_data(unit_data, lessons if structured_unit_data else [], content_scos, unit_identity)
        package_content_sha256 = stage_content_sha256(stage)

        file_name = f"{unit_identity['worldCode']}-U{unit_number}-{slug(title)}-SCORM12-{now_stamp()}.zip"
        zip_path = unique_export_path(export_dir / file_name)
        result = zip_stage(stage, zip_path)
        package_sha256 = file_sha256(zip_path)

    detected_lesson_scos = [sco for sco in content_scos if sco.get("kind") == "lesson"]
    report = {
        "manifestSchemaVersion": 2,
        "scormStructureVersion": SCORM_STRUCTURE_VERSION,
        "unit": unit_number,
        "title": title,
        "identifier": identifier,
        "requestedIdentifier": requested_identifier,
        "identifierPolicy": "S2 stable FLW package identity; requested Identifier UI value is not used for Moodle-targeted manifest identity.",
        "worldCode": unit_identity["worldCode"],
        "deploymentStageCode": unit_identity.get("deploymentStageCode", ""),
        "unitId": unit_identity["unitId"],
        "unitExternalKey": unit_identity["unitExternalKey"],
        "courseExternalKey": unit_identity.get("courseExternalKey", ""),
        "scormActivityExternalKey": unit_identity["scormActivityExternalKey"],
        "futureCmidNumber": unit_identity["futureCmidNumber"],
        "scormManifestIdentifier": identifier,
        "packageIdentifierRule": unit_identity["packageIdentifierRule"],
        "scoIdentifierRule": unit_identity["scoIdentifierRule"],
        "packageSha256": package_sha256,
        "packageContentSha256": package_content_sha256,
        "componentMappings": component_mappings,
        "microActivityMappings": micro_activity_mappings,
        "courseImage": course_image,
        "launchFile": launch_file,
        "includeSourceData": include_source_data,
        "includeTools": include_tools,
        "keepTopNavBar": keep_top_nav_bar,
        "topNavBarStyleInjected": top_nav_style_injected,
        "flwNavigatorEnabled": flw_navigator_enabled,
        "flwNavigatorVersion": FLW_NAVIGATOR_VERSION,
        "flwNavigatorInjectedCount": flw_navigator_injected_count,
        "flwNavigatorPrimary": bool(flw_navigator_enabled and flw_navigator_injected_count),
        "resumeStorage": ["cmi.core.lesson_location", "cmi.suspend_data"],
        "moodleScoLaunchMechanism": "/mod/scorm/player.php?scoid=<moodle scorm_scoes.id>",
        "unitScoIncluded": include_unit_sco,
        "scormScriptInjected": injected,
        "lessonFocusInjected": lesson_focus_injected,
        "lessonPagesFiltered": bool(content_scos),
        "sectionPagesFiltered": bool(content_scos),
        "sectionScoCount": len(content_scos),
        "lessonScoCount": len(detected_lesson_scos),
        "genericSectionScoCount": len([sco for sco in content_scos if sco.get("kind") == "section"]),
        "nonLessonScoCount": len(content_scos) - len(detected_lesson_scos),
        "sectionLaunchFiles": [sco["launchFile"] for sco in content_scos],
        "lessonLaunchFiles": [sco["launchFile"] for sco in detected_lesson_scos],
        "exportDirWarning": export_dir_warning,
        **result,
    }
    report_path = Path(result["zipPath"]).with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report


class Handler(BaseHTTPRequestHandler):
    server_version = "FLWScormGui/0.1"

    def log_message(self, fmt, *args):
        LOGGER.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), fmt % args)

    def send_json(self, payload, status: int = 200):
        data = json.dumps(payload, default=json_default, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            raise AppError("File not found", 404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data: bytes, content_type: str = "application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def handle_error(self, exc: Exception):
        if isinstance(exc, AppError):
            LOGGER.warning("AppError while handling %s: %s", self.path, exc)
            self.send_json({"ok": False, "error": str(exc)}, exc.status)
        else:
            LOGGER.error("Unhandled error while handling %s\n%s", self.path, traceback.format_exc())
            self.send_json({"ok": False, "error": repr(exc), "logPath": str(LOG_FILE)}, 500)

    def do_GET(self):
        try:
            self.route_get()
        except Exception as exc:
            self.handle_error(exc)

    def do_POST(self):
        try:
            self.route_post()
        except Exception as exc:
            self.handle_error(exc)

    def route_get(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/":
            self.send_file(STATIC_DIR / "index.html")
            return
        if path.startswith("/static/"):
            self.send_file(safe_join(STATIC_DIR, path.removeprefix("/static/")))
            return
        if path.startswith("/preview/"):
            parts = path.removeprefix("/preview/").split("/", 1)
            if len(parts) != 2:
                raise AppError("Preview path must include unit and file")
            root = preview_root_for_request(parts[0], qs.get("root", [None])[0])
            selected_unit = unit_dir(root, parts[0])
            self.send_file(safe_join(selected_unit, parts[1]))
            return
        if path.startswith("/edit-preview/"):
            parts = path.removeprefix("/edit-preview/").split("/", 1)
            if len(parts) != 2:
                raise AppError("Edit preview path must include unit and file")
            root = preview_root_for_request(parts[0], qs.get("root", [None])[0])
            selected_unit = unit_dir(root, parts[0])
            file_path = safe_join(selected_unit, parts[1])
            if file_path.suffix.lower() in {".html", ".htm"}:
                self.send_bytes(edit_preview_html(file_path), "text/html; charset=utf-8")
            else:
                self.send_file(file_path)
            return
        if path == "/api/config":
            content_root = default_content_root()
            export_dir = default_export_dir()
            self.send_json(
                {
                    "ok": True,
                    "defaultRoot": str(content_root),
                    "defaultExportDir": str(export_dir),
                    "defaultMoodleUrl": default_moodle_url(),
                    "defaultMoodlePhpPath": str(default_moodle_php_path()),
                    "defaultMoodleConfigPath": str(default_moodle_config_path()),
                    "settingsPath": str(settings_path()),
                    "appDir": str(APP_DIR),
                    "courseMapPath": str(FLW_COURSE_MAP_PATH),
                    "flwWorlds": configured_worlds_public(),
                    "batchPlannerVersion": "s1_world_stage_metadata_v1",
                }
            )
            return
        if path == "/api/batch-job":
            job_id = qs.get("jobId", [""])[0]
            self.send_json({"ok": True, "job": public_batch_job(load_batch_job(job_id))})
            return
        if path == "/api/units":
            root = ensure_root(qs.get("root", [None])[0])
            self.send_json({"ok": True, "root": str(root), "units": list_units(root)})
            return
        if path == "/api/unit":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            unit_number = unit_number_from_path(selected)
            archive = selected_unit_archive(root, selected)
            self.send_json(
                {
                    "ok": True,
                    "unit": unit_number,
                    "path": str(selected),
                    "source": "zip" if archive else "folder",
                    "archivePath": str(archive) if archive else "",
                    "canSaveZip": bool(archive),
                    "meta": index_meta(selected),
                    "validation": validate_unit(selected),
                    "files": list_unit_files(selected),
                }
            )
            return
        if path == "/api/file":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            file_path = safe_join(selected, qs.get("path", [""])[0])
            if not editable_file(file_path):
                raise AppError("File is not editable as text")
            self.send_json(
                {
                    "ok": True,
                    "path": file_path.relative_to(selected).as_posix(),
                    "content": read_text(file_path),
                    "size": file_path.stat().st_size,
                    "modified": dt.datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds"),
                }
            )
            return
        if path == "/api/csv":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            file_path = safe_join(selected, qs.get("path", [""])[0])
            if file_path.suffix.lower() != ".csv":
                raise AppError("Selected file is not CSV")
            self.send_json({"ok": True, "path": file_path.relative_to(selected).as_posix(), **read_csv_file(file_path)})
            return
        if path == "/api/unit-data":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            data = read_unit_data(selected)
            self.send_json(
                {
                    "ok": True,
                    "unit": unit_number_from_path(selected),
                    "path": "index.html",
                    "summary": unit_data_summary(data),
                    "data": data,
                }
            )
            return
        if path == "/api/visual-edits":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            edits = read_visual_edits(selected)
            self.send_json({"ok": True, "unit": unit_number_from_path(selected), "edits": edits, "count": len(edits)})
            return
        if path == "/api/backups":
            root = ensure_root(qs.get("root", [None])[0])
            selected = unit_dir(root, qs.get("unit", [""])[0])
            self.send_json({"ok": True, "unit": unit_number_from_path(selected), "backups": list_unit_backups(selected)})
            return
        raise AppError("Route not found", 404)

    def route_post(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if path == "/api/select-directory":
            self.send_json(
                {
                    "ok": True,
                    "path": select_directory(
                        body.get("initialDir"),
                        body.get("title") or "Select folder",
                    ),
                }
            )
            return

        if path == "/api/settings":
            settings = update_saved_paths(
                body.get("root"),
                body.get("exportDir"),
                body.get("moodleUrl"),
                body.get("moodlePhpPath"),
                body.get("moodleConfigPath"),
            )
            self.send_json({"ok": True, "settings": settings, "settingsPath": str(settings_path())})
            return

        if path == "/api/batch-export-scorm-to-flw":
            result = start_batch_job(body.get("root"), body)
            update_saved_paths(body.get("root"), body.get("exportDir"), body.get("moodleUrl"), body.get("moodlePhpPath"), body.get("moodleConfigPath"))
            self.send_json({"ok": True, "job": result})
            return
        if path == "/api/promotable-batch-dry-run":
            job = find_promotable_completed_dry_run_job(body.get("root"), body)
            self.send_json({"ok": True, "job": job, "found": bool(job)})
            return
        if path == "/api/resume-batch-job":
            result = start_batch_job(body.get("root"), body, body.get("jobId"))
            self.send_json({"ok": True, "job": result})
            return
        if path == "/api/cancel-batch-job":
            self.send_json({"ok": True, "job": cancel_batch_job(body.get("jobId", ""))})
            return
        if path == "/api/batch-preview-flw-courses":
            result = preview_batch_flw_courses(body.get("root"), body)
            update_saved_paths(body.get("root"), body.get("exportDir"), body.get("moodleUrl"), body.get("moodlePhpPath"), body.get("moodleConfigPath"))
            self.send_json({"ok": True, **result})
            return

        root = ensure_root(body.get("root"))

        if path == "/api/file":
            selected = unit_dir(root, body.get("unit", ""))
            file_path = safe_join(selected, body.get("path", ""))
            if file_path.suffix.lower() not in TEXT_EXTENSIONS:
                raise AppError("File type is not editable as text")
            backup = backup_file(selected, file_path)
            write_text(file_path, body.get("content", ""))
            self.send_json({"ok": True, "backup": backup, "path": file_path.relative_to(selected).as_posix()})
            return
        if path == "/api/csv":
            selected = unit_dir(root, body.get("unit", ""))
            file_path = safe_join(selected, body.get("path", ""))
            if file_path.suffix.lower() != ".csv":
                raise AppError("Selected file is not CSV")
            headers = body.get("headers") or []
            rows = body.get("rows") or []
            if not headers:
                raise AppError("CSV save needs headers")
            backup = backup_file(selected, file_path)
            write_csv_file(file_path, headers, rows)
            self.send_json({"ok": True, "backup": backup, "path": file_path.relative_to(selected).as_posix()})
            return
        if path == "/api/unit-data":
            selected = unit_dir(root, body.get("unit", ""))
            data = body.get("data")
            backup = write_unit_data(selected, data)
            self.send_json(
                {
                    "ok": True,
                    "backup": backup,
                    "summary": unit_data_summary(data),
                    "validation": validate_unit(selected),
                }
            )
            return
        if path == "/api/visual-edits":
            selected = unit_dir(root, body.get("unit", ""))
            edits, backup = merge_visual_edits(selected, body.get("edits") or [], body.get("mode") or "merge")
            self.send_json(
                {
                    "ok": True,
                    "backup": backup,
                    "count": len(edits),
                    "edits": edits,
                    "validation": validate_unit(selected),
                }
            )
            return
        if path == "/api/replace-reference":
            selected = unit_dir(root, body.get("unit", ""))
            result = replace_index_reference(selected, body.get("oldRef", ""), body.get("newRef", ""))
            self.send_json({"ok": True, "replace": result, "validation": validate_unit(selected), "files": list_unit_files(selected)})
            return
        if path == "/api/import-asset":
            selected = unit_dir(root, body.get("unit", ""))
            result = import_unit_asset(selected, body.get("filename", ""), body.get("contentBase64", ""), body.get("kind", ""))
            self.send_json({"ok": True, "asset": result, "validation": validate_unit(selected), "files": list_unit_files(selected)})
            return
        if path == "/api/restore-backup":
            selected = unit_dir(root, body.get("unit", ""))
            result = restore_unit_backup(selected, body.get("stamp", ""), body.get("path", ""))
            self.send_json(
                {
                    "ok": True,
                    "restore": result,
                    "validation": validate_unit(selected),
                    "files": list_unit_files(selected),
                    "backups": list_unit_backups(selected),
                }
            )
            return
        if path == "/api/validate":
            selected = unit_dir(root, body.get("unit", ""))
            self.send_json({"ok": True, "validation": validate_unit(selected)})
            return
        if path == "/api/scorm-preview":
            selected = unit_dir(root, body.get("unit", ""))
            self.send_json({"ok": True, "structure": scorm_structure_preview(selected, body)})
            return
        if path == "/api/repack-unit-zip":
            selected = unit_dir(root, body.get("unit", ""))
            self.send_json({"ok": True, "zip": repack_unit_archive(root, selected)})
            return
        if path == "/api/copy-unit":
            selected = unit_dir(root, body.get("unit", ""))
            result = copy_unit_package(root, selected, body.get("targetUnit"), body.get("title"), body.get("outputType") or "auto")
            PREVIEW_ROOTS[result["unit"]] = root
            self.send_json({"ok": True, "copy": result, "units": list_units(root)})
            return
        if path == "/api/export-scorm":
            selected = unit_dir(root, body.get("unit", ""))
            result = export_scorm(selected, body)
            update_saved_paths(root, body.get("exportDir") or str(Path(result["zipPath"]).parent), body.get("moodleUrl"), body.get("moodlePhpPath"), body.get("moodleConfigPath"))
            self.send_json({"ok": True, "export": result})
            return
        if path == "/api/export-scorm-to-flw":
            selected = unit_dir(root, body.get("unit", ""))
            result = export_scorm_to_flw(root, selected, body)
            update_saved_paths(root, body.get("exportDir") or str(Path(result["export"]["zipPath"]).parent), body.get("moodleUrl"), body.get("moodlePhpPath"), body.get("moodleConfigPath"))
            self.send_json({"ok": True, **result})
            return
        raise AppError("Route not found", 404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local GUI for Adventure unit package inspection and SCORM 1.2 export.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    interrupted_jobs = reconcile_stale_batch_jobs()
    for recovered in interrupted_jobs:
        message = (
            f"Recovered interrupted batch job {recovered['jobId']}: "
            f"{recovered['reusableExportCount']}/{recovered['expectedCount']} exported package(s) reusable."
        )
        LOGGER.warning(message)
        print(message)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"FLW SCORM GUI listening at http://{args.host}:{args.port}")
    print(f"Default root: {default_content_root()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
