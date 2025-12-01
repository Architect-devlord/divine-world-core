# ai_core/config_loader.py
"""
Unified configuration loader for Divine World Project.
Loads config.yml, merges environment variable overrides (DW_*),
and caches the final dictionary. Used by all AI subsystems.
"""

import os
import yaml
import logging
from typing import Any, Dict

log = logging.getLogger("config_loader")

_DEFAULT_LOCATIONS = [
    "config.yml",
    os.path.join(os.getcwd(), "config.yml"),
    os.path.join(os.getcwd(), "py_backend", "config.yml"),
]

_cached: Dict[str, Any] = {}


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Apply DW_* environment variable overrides."""
    env_map = {
        "DW_DEVICE": ("runtime", "device_preference"),
        "DW_PRECISION": ("runtime", "precision"),
        "DW_LM": ("language_model", "model_name_or_path"),
        "DW_WM": ("world_model", "model_name"),
        "DW_LOG_LEVEL": ("runtime", "log_level"),
        "DW_LOG_DIR": ("paths", "logs_dir"),
        "DW_SAFE_MODE": ("runtime", "safe_mode"),
    }
    for env_key, path in env_map.items():
        if env_key in os.environ:
            section, key = path
            if section in cfg:
                val = os.environ[env_key]
                if val.lower() in ("true", "false"):
                    val = val.lower() == "true"
                cfg[section][key] = val
                log.info(f"Env override: {env_key} -> {section}.{key} = {val}")
    return cfg


def load_config(path: str = None, force_reload: bool = False) -> Dict[str, Any]:
    """Load YAML config and merge environment overrides."""
    global _cached
    if _cached and not force_reload:
        return _cached

    cfg = None
    for p in ([path] if path else _DEFAULT_LOCATIONS):
        if p and os.path.exists(p):
            try:
                cfg = _load_yaml(p)
                break
            except Exception as e:
                log.error(f"Error loading {p}: {e}")
    if cfg is None:
        raise FileNotFoundError("config.yml not found in any default path")

    cfg = _apply_env_overrides(cfg)
    _cached = cfg
    log.info(f"Configuration loaded successfully from {p}")
    return cfg


def get_section(section: str, default: Dict[str, Any] = None) -> Dict[str, Any]:
    cfg = load_config()
    return cfg.get(section, default or {})


def get_device() -> str:
    """Return preferred torch device."""
    cfg = load_config()
    pref = cfg.get("runtime", {}).get("device_preference", "auto").lower()
    if pref == "cuda":
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    if pref == "cpu":
        return "cpu"
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_precision() -> str:
    return load_config().get("runtime", {}).get("precision", "float32")


def summary() -> None:
    cfg = load_config()
    print("\n========== Divine World Configuration ==========")
    print(f"Device Preference : {get_device()}")
    print(f"Precision          : {get_precision()}")
    print(f"Log Level          : {cfg.get('runtime', {}).get('log_level')}")
    for section in ("world_model", "language_model", "training"):
        print(f"\n[{section}]")
        for k, v in cfg.get(section, {}).items():
            print(f"  {k}: {v}")
    print("================================================\n")
