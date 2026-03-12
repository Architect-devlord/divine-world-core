# ai_core/logger_setup.py
"""
Centralized logging setup for Divine World.

Call initialize_logging() once at backend startup (before anything else
writes a log message).  It is safe to call multiple times — subsequent
calls are ignored unless force=True is passed.

Why not basicConfig()
---------------------
logging.basicConfig() is a no-op if the root logger already has handlers
(which happens as soon as any imported module does `logging.getLogger()`
and emits a record before we've configured things).  We instead install
handlers explicitly so the file + stream handlers always get added.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

try:
    from ai_core.config_loader import get_section as _get_section
except ImportError:
    def _get_section(section: str, default=None):
        return default or {}

_initialized = False


def initialize_logging(log_dir: Optional[str] = None, force: bool = False) -> None:
    """
    Configure the root logger with a rotating file handler + stream handler.

    Parameters
    ----------
    log_dir : str, optional
        Directory for the log file.  Falls back to config [paths] logs_dir,
        then "data/logs".
    force : bool
        If True, re-configure even if initialize_logging() was already called.
        Useful in tests.
    """
    global _initialized
    if _initialized and not force:
        return
    _initialized = True

    # ── Read config ────────────────────────────────────────────────────────
    runtime_cfg  = _get_section("runtime", {})
    paths_cfg    = _get_section("paths",   {})

    raw_level = runtime_cfg.get("log_level", "INFO").upper()
    log_level = getattr(logging, raw_level, logging.INFO)
    log_fmt   = runtime_cfg.get(
        "log_format",
        "[%(asctime)s][%(levelname)s] %(name)s: %(message)s",
    )
    date_fmt  = runtime_cfg.get("log_date_format", "%Y-%m-%d %H:%M:%S")

    # ── Resolve log directory ──────────────────────────────────────────────
    log_dir = log_dir or paths_cfg.get("logs_dir", "data/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "divine_world.log")

    # ── Build formatter ────────────────────────────────────────────────────
    formatter = logging.Formatter(log_fmt, datefmt=date_fmt)

    # ── File handler (rotating, 10 MB × 5 backups) ────────────────────────
    file_handler = RotatingFileHandler(
        log_file,
        mode="a",
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # ── Stream handler (stdout — Uvicorn already writes to stderr) ─────────
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)

    # ── Configure root logger ──────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any pre-existing handlers of the same type so we don't double-log
    # after a force=True re-initialisation or when uvicorn installs its own.
    existing_types = (RotatingFileHandler, logging.FileHandler, logging.StreamHandler)
    for h in list(root.handlers):
        if isinstance(h, existing_types):
            try:
                h.close()
            except Exception:
                pass
            root.removeHandler(h)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # ── Silence chatty third-party loggers ────────────────────────────────
    for noisy in ("config_loader", "uvicorn.access", "httpx", "httpcore",
                  "websockets.server", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info(
        "Logging initialised — level=%s file=%s", raw_level, log_file
    )