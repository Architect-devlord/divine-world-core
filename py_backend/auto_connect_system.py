# py_backend/auto_connect_system.py
"""
Auto-Connect System
===================
Scans the NPC applications folder for packaged agents that have
auto_connect=True in their config.json, launches them via the spawner,
and waits for all of them to report as connected through the
/api/player_event endpoint before signalling readiness.

Changes from original:
  - server_addr read from agents.json 'server' block (not hardcoded Config.DEFAULT_SERVER)
  - Each agent checks Minecraft availability before launching MC client
  - Agents without Minecraft fall back to frontend-only mode automatically
  - Agents that fail MC launch also fall back to frontend-only mode
  - Logs clear per-agent diagnostic: "X: Minecraft not found — frontend-only mode"
  - integrate_with_backend() reads server info from agents.json at call time
"""

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from py_backend.config import Config

log = logging.getLogger("auto_connect")


class AutoConnectSystem:
    """
    Discovers, launches, and tracks connection of auto-connect agents.

    Lifecycle:
      1. scan_agents_folder()          — populate required_agents list
      2. launch_all_agents(spawner)    — start each agent process
      3. wait_for_all_connections()    — block until all send player_event
      4. mark_connected(agent_id)      — called by player_event handler
    """

    def __init__(self, agents_folder: str,
                 server_addr: str = "127.0.0.1:25565"):
        self.agents_folder   = Path(agents_folder)
        self.server_addr     = server_addr
        self.required_agents: List[Dict]             = []
        self.connected_agents: Set[str]              = set()
        self.connection_callbacks: Dict[str, asyncio.Event] = {}

        log.info("AutoConnect System initialised")
        log.info(f"  Agents Folder : {self.agents_folder}")
        log.info(f"  Server        : {self.server_addr}")

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def scan_agents_folder(self) -> List[Dict]:
        self.required_agents = []
        self.connection_callbacks.clear()

        if not self.agents_folder.exists():
            log.warning(f"Agents folder missing: {self.agents_folder}")
            return []

        for agent_dir in self.agents_folder.glob("DW_*"):
            config_path = agent_dir / "config.json"
            if not config_path.exists():
                continue
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                if not config.get("auto_connect", False):
                    continue
                agent_info = {
                    "agent_id":   config["agent_id"],
                    "agent_type": config.get("agent_type", "npc"),
                    "god_type":   config.get("god_type"),
                    "path":       str(agent_dir),
                    "config":     config,
                }
                self.required_agents.append(agent_info)
                self.connection_callbacks[agent_info["agent_id"]] = asyncio.Event()
                log.info(
                    f"  Auto-connect agent: {agent_info['agent_id']} "
                    f"(type={agent_info['agent_type']})"
                )
            except Exception as e:
                log.error(f"Failed to read config {config_path}: {e}")

        log.info(f"✅ {len(self.required_agents)} auto-connect agent(s) found")
        return self.required_agents

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    async def launch_all_agents(self, spawner) -> bool:
        if not self.required_agents:
            log.info("No auto-connect agents to launch")
            return True
        log.info(f"🚀 Launching {len(self.required_agents)} agent(s)…")
        results = await asyncio.gather(
            *[self._launch_agent(spawner, a) for a in self.required_agents],
            return_exceptions=True,
        )
        ok   = sum(1 for r in results if r is True)
        fail = len(results) - ok
        if fail:
            log.warning(f"⚠️  {fail}/{len(results)} agent(s) failed to launch")
        log.info(f"✅ {ok}/{len(results)} agent(s) launched")
        return fail == 0

    async def _launch_agent(self, spawner, agent_info: Dict) -> bool:
        """
        Launch one agent.
          - Checks if Minecraft is available on this machine.
          - If MC available: launches in minecraft mode.
          - If MC missing or launch fails: starts in frontend-only mode.
        """
        agent_id   = agent_info["agent_id"]
        agent_type = agent_info["agent_type"]

        # ── Check Minecraft availability ─────────────────────────────────
        try:
            from py_backend.utils.mc_uuid import AgentNameManager
            mc_path = AgentNameManager.get_minecraft_path()
        except Exception:
            mc_path = None

        if mc_path is None:
            log.warning(
                f"[{agent_id}] Minecraft not found on this machine "
                f"— starting in frontend-only mode"
            )
            return await self._launch_frontend_only(agent_id, agent_info)

        # ── Minecraft launch ──────────────────────────────────────────────
        try:
            log.info(f"  Launching {agent_id} (type={agent_type}, MC={mc_path})…")

            if agent_type == "npc":
                from ai_core.agent import NPCAgent
                agent = NPCAgent(agent_id=agent_id, autonomous=True, mode="minecraft")
            elif agent_type.startswith("god_"):
                god_type = (
                    agent_info.get("god_type") or agent_type.replace("god_", "")
                )
                agent = spawn_god_agent(spawner, god_type=god_type, agent_id=agent_id)
            else:
                log.error(f"Unknown agent type: {agent_type}")
                return False

            if agent:
                log.info(f"  ✅ {agent_id} launched (minecraft mode)")
                return True

            log.error(f"  ❌ {agent_id}: agent creation returned None — falling back")
            return await self._launch_frontend_only(agent_id, agent_info)

        except Exception as e:
            log.error(
                f"  ❌ {agent_id}: Minecraft launch failed: {e} "
                f"— falling back to frontend-only mode"
            )
            return await self._launch_frontend_only(agent_id, agent_info)

    async def _launch_frontend_only(self, agent_id: str, agent_info: Dict) -> bool:
        """Start chat_launcher (frontend-only mode) for agents without Minecraft."""
        try:
            config     = agent_info.get("config", {})
            brain_path = config.get("brain_path", "")

            # Resolve brain path: try config value, then default location
            from pathlib import Path as _P
            _bp = _P(brain_path) if brain_path else _P()
            if not _bp.exists():
                _bp = Config.get_agent_brain_path(agent_id)

            brain_str = str(_bp) if _bp.exists() else ""

            def _run():
                try:
                    from py_backend.chat_launcher import start_chat_interface
                    start_chat_interface(agent_id, brain_str, config)
                except Exception as _e:
                    log.error(f"[{agent_id}] Frontend-only mode crashed: {_e}")

            t = threading.Thread(target=_run, daemon=True, name=f"frontend-{agent_id}")
            t.start()
            log.info(
                f"[{agent_id}] Frontend-only mode started "
                f"(brain: {brain_str or 'fresh state'})"
            )
            return True
        except Exception as e:
            log.error(f"[{agent_id}] Frontend-only mode failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Wait
    # ------------------------------------------------------------------

    async def wait_for_all_connections(self, timeout: int = 60) -> bool:
        if not self.required_agents:
            return True
        log.info(
            f"⏳ Waiting for {len(self.required_agents)} agent(s) "
            f"(timeout={timeout}s)…"
        )
        start = time.time()
        wait_tasks   = [
            asyncio.ensure_future(self.connection_callbacks[a["agent_id"]].wait())
            for a in self.required_agents
        ]
        timeout_task = asyncio.ensure_future(asyncio.sleep(timeout))
        done, pending = await asyncio.wait(
            [*wait_tasks, timeout_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if timeout_task in done:
            missing = [
                a["agent_id"] for a in self.required_agents
                if a["agent_id"] not in self.connected_agents
            ]
            log.warning(f"⚠️  Connection timeout — missing: {missing}")
            return False
        elapsed = time.time() - start
        log.info(f"✅ All {len(self.required_agents)} agent(s) connected in {elapsed:.1f}s")
        return True

    # ------------------------------------------------------------------
    # Feedback from player_event endpoint
    # ------------------------------------------------------------------

    def mark_connected(self, agent_id: str):
        ids = {a["agent_id"] for a in self.required_agents}
        if agent_id not in ids:
            return
        self.connected_agents.add(agent_id)
        if agent_id in self.connection_callbacks:
            self.connection_callbacks[agent_id].set()
        log.info(
            f"✅ {agent_id} connected "
            f"({len(self.connected_agents)}/{len(self.required_agents)})"
        )

    def is_all_connected(self) -> bool:
        return len(self.connected_agents) >= len(self.required_agents)

    def get_status(self) -> Dict:
        return {
            "total_agents": len(self.required_agents),
            "connected":    len(self.connected_agents),
            "pending":      len(self.required_agents) - len(self.connected_agents),
            "server":       self.server_addr,
            "agents": [
                {
                    "agent_id":  a["agent_id"],
                    "connected": a["agent_id"] in self.connected_agents,
                }
                for a in self.required_agents
            ],
        }


# ---------------------------------------------------------------------------
# FastAPI integration
# ---------------------------------------------------------------------------

def integrate_with_backend(app, agent_manager):
    """
    Add /api/autoconnect/* endpoints to the running FastAPI app.

    Reads server address from agents.json 'server' block so that agents
    on different machines all connect to the same configured server.
    """
    from fastapi import HTTPException

    # ── Read server info from agents.json ───────────────────────────────
    try:
        from py_backend.utils.mc_uuid import AgentNameManager
        srv  = AgentNameManager.get_server_info()
        server_addr = f"{srv['host']}:{srv['port']}"
        log.info(f"[AutoConnect] Server from agents.json: {server_addr}")
    except Exception as _e:
        server_addr = Config.DEFAULT_SERVER
        log.warning(f"[AutoConnect] Could not read server info: {_e} — using {server_addr}")

    auto_connect = AutoConnectSystem(
        agents_folder=str(Config.NPC_APPLICATIONS_DIR),
        server_addr=server_addr,
    )
    app.state.auto_connect = auto_connect

    @app.post("/api/autoconnect/scan")
    async def scan_agents():
        agents = auto_connect.scan_agents_folder()
        return {"status": "success", "agents_found": len(agents), "agents": agents}

    @app.post("/api/autoconnect/launch")
    async def launch_agents():
        success = await auto_connect.launch_all_agents(agent_manager.spawner)
        return {
            "status":  "success" if success else "partial",
            "message": f"Launched {len(auto_connect.required_agents)} agent(s)",
        }

    @app.post("/api/autoconnect/wait")
    async def wait_connections(timeout: int = 60):
        success = await auto_connect.wait_for_all_connections(timeout)
        return {
            "status":        "success" if success else "timeout",
            "all_connected": auto_connect.is_all_connected(),
            **auto_connect.get_status(),
        }

    @app.get("/api/autoconnect/status")
    async def get_connection_status():
        return {"status": "success", **auto_connect.get_status()}

    log.info("✅ Auto-connect endpoints registered (/api/autoconnect/*)")


# ---------------------------------------------------------------------------
# God-agent helper
# ---------------------------------------------------------------------------

def spawn_god_agent(spawner, god_type: str, agent_id: str, **kwargs):
    from ai_core.agent import NPCAgent
    agent = NPCAgent(
        agent_id=agent_id, autonomous=True, mode="minecraft",
        god_type=god_type, **kwargs,
    )
    return agent