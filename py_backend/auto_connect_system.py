# py_backend/auto_connect_system.py
"""
Auto-Connect System
===================
Scans the NPC applications folder for packaged agents that have
auto_connect=True in their config.json, launches them via the spawner,
and waits for all of them to report as connected through the
/api/player_event endpoint before signalling readiness.

Integration points
------------------
  integrate_with_backend(app, agent_manager)
    → adds /api/autoconnect/* endpoints to the FastAPI app
    → registers a mark_connected hook so player_event calls feed back here

  spawn_god_agent(spawner, god_type, agent_id, **kwargs)
    → thin helper used by _launch_agent for god-type packaged agents
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from py_backend.config import Config

log = logging.getLogger("auto_connect")


# ---------------------------------------------------------------------------
# AutoConnectSystem
# ---------------------------------------------------------------------------

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
        self.agents_folder  = Path(agents_folder)
        self.server_addr    = server_addr
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
        """
        Scan agents_folder for packaged agent directories that have
        auto_connect=True in their config.json.
        """
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
        """Launch every discovered auto-connect agent concurrently."""
        if not self.required_agents:
            log.info("No auto-connect agents to launch")
            return True

        log.info(f"🚀 Launching {len(self.required_agents)} agent(s)…")
        results = await asyncio.gather(
            *[self._launch_agent(spawner, a) for a in self.required_agents],
            return_exceptions=True,
        )

        ok    = sum(1 for r in results if r is True)
        fail  = len(results) - ok
        if fail:
            log.warning(f"⚠️  {fail}/{len(results)} agent(s) failed to launch")
        log.info(f"✅ {ok}/{len(results)} agent(s) launched")
        return fail == 0

    async def _launch_agent(self, spawner, agent_info: Dict) -> bool:
        agent_id   = agent_info["agent_id"]
        agent_type = agent_info["agent_type"]
        try:
            log.info(f"  Launching {agent_id} (type={agent_type})…")

            if agent_type == "npc":
                from ai_core.agent import NPCAgent
                agent = NPCAgent(agent_id=agent_id, autonomous=True, mode="minecraft")

            elif agent_type.startswith("god_"):
                god_type = (
                    agent_info.get("god_type")
                    or agent_type.replace("god_", "")
                )
                agent = spawn_god_agent(spawner, god_type=god_type, agent_id=agent_id)

            else:
                log.error(f"Unknown agent type: {agent_type}")
                return False

            if agent:
                log.info(f"  ✅ {agent_id} launched")
                return True

            log.error(f"  ❌ {agent_id}: agent creation returned None")
            return False

        except Exception as e:
            log.error(f"  ❌ Exception launching {agent_id}: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Wait
    # ------------------------------------------------------------------

    async def wait_for_all_connections(self, timeout: int = 60) -> bool:
        """
        Wait up to *timeout* seconds for every required agent to call
        mark_connected().  Returns True if all connected, False on timeout.
        """
        if not self.required_agents:
            return True

        log.info(
            f"⏳ Waiting for {len(self.required_agents)} agent(s) "
            f"(timeout={timeout}s)…"
        )
        start = time.time()

        # One asyncio.Event per agent; gather all waits + a timeout task
        wait_tasks    = [
            asyncio.ensure_future(
                self.connection_callbacks[a["agent_id"]].wait()
            )
            for a in self.required_agents
        ]
        timeout_task  = asyncio.ensure_future(asyncio.sleep(timeout))

        done, pending = await asyncio.wait(
            [*wait_tasks, timeout_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel everything still running
        for t in pending:
            t.cancel()

        if timeout_task in done:
            missing = [
                a["agent_id"]
                for a in self.required_agents
                if a["agent_id"] not in self.connected_agents
            ]
            log.warning(f"⚠️  Connection timeout — missing: {missing}")
            return False

        elapsed = time.time() - start
        log.info(
            f"✅ All {len(self.required_agents)} agent(s) connected "
            f"in {elapsed:.1f}s"
        )
        return True

    # ------------------------------------------------------------------
    # Feedback from player_event endpoint
    # ------------------------------------------------------------------

    def mark_connected(self, agent_id: str):
        """
        Called by the /api/player_event handler when an agent with
        event='connected' is received.  Fires the corresponding Event so
        wait_for_all_connections() can unblock.
        """
        ids = {a["agent_id"] for a in self.required_agents}
        if agent_id not in ids:
            return   # not an auto-connect agent, ignore
        self.connected_agents.add(agent_id)
        if agent_id in self.connection_callbacks:
            self.connection_callbacks[agent_id].set()
        log.info(
            f"✅ {agent_id} connected "
            f"({len(self.connected_agents)}/{len(self.required_agents)})"
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_all_connected(self) -> bool:
        return len(self.connected_agents) >= len(self.required_agents)

    def get_status(self) -> Dict:
        return {
            "total_agents": len(self.required_agents),
            "connected":    len(self.connected_agents),
            "pending":      len(self.required_agents) - len(self.connected_agents),
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
    Add /api/autoconnect/* endpoints to the running FastAPI app and
    expose the auto_connect instance via app.state so that the
    player_event handler can call mark_connected().

    Call this ONCE at startup, after creating the FastAPI app.
    """
    from fastapi import HTTPException

    auto_connect = AutoConnectSystem(
        agents_folder=str(Config.NPC_APPLICATIONS_DIR),
        server_addr=Config.DEFAULT_SERVER,
    )
    app.state.auto_connect = auto_connect

    # ------------------------------------------------------------------

    @app.post("/api/autoconnect/scan")
    async def scan_agents():
        agents = auto_connect.scan_agents_folder()
        return {
            "status":       "success",
            "agents_found": len(agents),
            "agents":       agents,
        }

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
            "status":       "success" if success else "timeout",
            "all_connected": auto_connect.is_all_connected(),
            **auto_connect.get_status(),
        }

    @app.get("/api/autoconnect/status")
    async def get_connection_status():
        return {"status": "success", **auto_connect.get_status()}

    log.info("✅ Auto-connect endpoints registered (/api/autoconnect/*)")
    log.info(
        "   player_event handler must call "
        "app.state.auto_connect.mark_connected(agent_id) on 'connected' events"
    )


# ---------------------------------------------------------------------------
# God-agent helper
# ---------------------------------------------------------------------------

def spawn_god_agent(spawner, god_type: str, agent_id: str, **kwargs):
    """
    Instantiate a god-type NPCAgent directly (used by auto-connect when
    a packaged god agent is found in the applications folder).

    The *spawner* argument is accepted for API compatibility but not used —
    NPCAgent's __init__ handles god_type internally via god_controls.
    """
    from ai_core.agent import NPCAgent

    agent = NPCAgent(
        agent_id=agent_id,
        autonomous=True,
        mode="minecraft",
        god_type=god_type,
        **kwargs,
    )
    return agent