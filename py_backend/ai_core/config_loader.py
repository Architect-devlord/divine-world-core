# ai_core/config_loader.py
"""
Thin adapter that satisfies world_model.py's
    from ai_core.config_loader import get_section, get_device
import without requiring any changes to world_model.py.

All real configuration lives in config.py (Config class).
This module exposes the two helpers world_model.py needs and
routes everything else through a lightweight YAML/env-var layer
so callers can optionally drop a `config.yaml` next to the
package without breaking anything.
"""

import os
import logging
import torch
from typing import Any, Dict

log = logging.getLogger("config_loader")

# ---------------------------------------------------------------------------
# Optional YAML support
# ---------------------------------------------------------------------------
_yaml_config: Dict[str, Any] = {}

def _load_yaml() -> None:
    """
    Attempt to load config.yaml from the repo root (one level above ai_core/).
    Silently skips if the file doesn't exist or PyYAML isn't installed.
    """
    global _yaml_config
    try:
        import yaml
        from pathlib import Path
        candidates = [
            Path(__file__).parent.parent / "config.yaml",   # py_backend/config.yaml
            Path(__file__).parent / "config.yaml",           # ai_core/config.yaml
        ]
        for path in candidates:
            if path.exists():
                with open(path, "r") as fh:
                    _yaml_config = yaml.safe_load(fh) or {}
                log.info(f"config_loader: loaded {path}")
                return
    except ImportError:
        pass  # PyYAML not installed — fine, we fall back to defaults
    except Exception as e:
        log.warning(f"config_loader: could not load YAML config: {e}")


_load_yaml()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_section(section: str, default: Any = None) -> Any:
    """
    Return a config section dict.

    Priority:
      1. YAML file  (key == section name)
      2. `default`  (caller-supplied fallback, typically {})

    Example usage in world_model.py:
        cfg = get_section("world_model", {})
        d_model = cfg.get("d_model", 512)
    """
    return _yaml_config.get(section, default if default is not None else {})


def get_device() -> str:
    """
    Resolve the preferred torch device.

    Priority:
      1. DW_DEVICE env var  (e.g. "cuda", "cpu", "mps")
      2. YAML global key    "device"
      3. Auto-detect CUDA / MPS / CPU
    """
    env = os.getenv("DW_DEVICE", "").strip().lower()
    if env:
        return env

    yaml_device = _yaml_config.get("device", "").strip().lower()
    if yaml_device:
        return yaml_device

    if torch.cuda.is_available():
        return "cuda"
    # MPS (Apple Silicon) — only available in recent torch builds
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"