# ai_core/config_manager.py
"""
Higher-level API built on config_loader.
Provides typed access, live reload, and environment merging.
"""

import time
import threading
from typing import Any, Dict
from ai_core.config_loader import load_config, get_device, get_precision

class ConfigManager:
    """Singleton-like manager with thread-safe reload and cached state."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._cfg = load_config()
        self._last_load = time.time()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = ConfigManager()
            return cls._instance

    def reload(self, force=False):
        if force or (time.time() - self._last_load > 60):
            self._cfg = load_config(force_reload=True)
            self._last_load = time.time()

    def get(self, section: str, key: str = None, default: Any = None) -> Any:
        if key is None:
            return self._cfg.get(section, default)
        return self._cfg.get(section, {}).get(key, default)

    def device(self) -> str:
        return get_device()

    def precision(self) -> str:
        return get_precision()

    def runtime(self) -> Dict[str, Any]:
        return self._cfg.get("runtime", {})

    def world_model(self) -> Dict[str, Any]:
        return self._cfg.get("world_model", {})

    def language_model(self) -> Dict[str, Any]:
        return self._cfg.get("language_model", {})

    def training(self) -> Dict[str, Any]:
        return self._cfg.get("training", {})

    def paths(self) -> Dict[str, Any]:
        return self._cfg.get("paths", {})

# Global accessor
config_manager = ConfigManager.get()
