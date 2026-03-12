# py_backend/utils/agents_json_manager.py
"""
Agents JSON Manager — thin compatibility wrapper.
==================================================
The canonical implementation lives in mc_uuid.AgentNameManager which is
the single source of truth for agents.json reads and writes.

This module re-exports AgentsJsonManager (mapped to AgentNameManager) so
that any future code or Java-facing tooling that imports
``from utils.agents_json_manager import AgentsJsonManager`` continues to
work without a separate implementation diverging from mc_uuid.py.

Do NOT add standalone logic here — add it to AgentNameManager in mc_uuid.py.
"""

from py_backend.utils.mc_uuid import AgentNameManager as AgentsJsonManager, get_minecraft_uuid

__all__ = ["AgentsJsonManager", "get_minecraft_uuid"]


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors the old get_manager() pattern)
# ---------------------------------------------------------------------------

_manager: AgentsJsonManager | None = None


def get_manager() -> AgentsJsonManager:
    """Return (or lazily create) the global AgentNameManager instance."""
    global _manager
    if _manager is None:
        _manager = AgentsJsonManager()
    return _manager