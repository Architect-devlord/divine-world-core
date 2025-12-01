# ai_core/logger_setup.py
"""
Centralized logger setup that respects config.yml runtime.log_level and format.
Call logger_setup.initialize_logging() at backend startup.
"""

import logging
import os
from ai_core.config_loader import get_section

def initialize_logging(log_dir: str = None):
    cfg = get_section("runtime", {})
    log_level = cfg.get("log_level", "INFO").upper()
    log_fmt = cfg.get("log_format", "[%(asctime)s][%(levelname)s] %(name)s: %(message)s")

    log_dir = log_dir or get_section("paths", {}).get("logs_dir", "data/logs")
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, "divine_world.log")

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_fmt,
        handlers=[
            logging.FileHandler(file_path, mode="a", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    logging.getLogger("config_loader").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.ERROR)

    logging.info("Logging initialized at %s level. Log file: %s", log_level, file_path)
