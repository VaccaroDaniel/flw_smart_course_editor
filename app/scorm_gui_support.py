"""Small shared support helpers for the SCORM editor.

Keeping operational helpers here lets server.py stay focused on editor and
export behavior while avoiding a risky large-scale route/export split.
"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logger(app_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir = app_dir / "logs"
    log_file = log_dir / "editor.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("flw_scorm_gui")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
    return logger, log_file


def fmt_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
