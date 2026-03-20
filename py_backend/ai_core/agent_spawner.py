# ai_core/agent_spawner.py
"""
Centralised agent spawning system.
====================================
Provides two classes:

  AgentSpawner          — base spawner: creates NPCAgent instances, manages
                          Minecraft client processes, saves brains on spawn.
                          Works in CHAT-ONLY mode when no client jar is found.

  UltimMCAgentSpawner   — extends AgentSpawner with full UltimMC automation:
                          account creation, Forge instance setup, mod install,
                          and automatic client launch.  Used by
                          auto_packager.EnhancedAgentSpawner as its UltimMC
                          delegate — never used directly by breeding_system.

Import note
-----------
auto_packager.py does:
    from ai_core.agent_spawner import AgentSpawner          # base class
    from ai_core.agent_spawner import UltimMCAgentSpawner   # optional delegate

Keep that import contract stable.
"""

import subprocess
import socket
import time
import threading
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ai_core.agent import NPCAgent
from ai_core.personality import GenderType, assign_npc_gender, assign_god_gender
from py_backend.config import Config
from py_backend.utils.mc_uuid import get_minecraft_uuid

log = logging.getLogger("agent_spawner")
log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Minecraft client process handle
# ---------------------------------------------------------------------------

class MinecraftClientProcess:
    """Handle for a running per-agent Minecraft JVM process."""

    def __init__(self, agent_id: str, process: subprocess.Popen,
                 backend_port: int, server_addr: str):
        self.agent_id     = agent_id
        self.process      = process
        self.backend_port = backend_port
        self.backend_url  = f"http://127.0.0.1:{backend_port}"
        self.server_addr  = server_addr
        self.started_at   = time.time()
        self.is_alive     = True

    def kill(self):
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.is_alive = False


# ---------------------------------------------------------------------------
# Per-agent Minecraft client manager
# ---------------------------------------------------------------------------

class AgentClientManager:
    """
    Manages dedicated Minecraft JVM client processes.
    When no client jar is found, operates in CHAT-ONLY mode
    (spawn_client returns None; all other spawning still works).
    """

    def __init__(self, client_jar_path: Optional[str] = None,
                 base_backend_port: int = Config.BASE_BACKEND_PORT):
        if client_jar_path is None:
            self.client_jar      = None
            self.minecraft_mode  = False
            log.info("AgentClientManager: CHAT-ONLY mode (no client jar)")
        else:
            self.client_jar     = Path(client_jar_path)
            self.minecraft_mode = self.client_jar.exists()
            if not self.minecraft_mode:
                log.warning(f"Client jar not found: {client_jar_path} — CHAT-ONLY mode")

        self.base_port = base_backend_port
        self.clients: Dict[str, MinecraftClientProcess] = {}
        self._lock    = threading.Lock()

    # ------------------------------------------------------------------
    # Port allocation
    # ------------------------------------------------------------------

    def allocate_port(self, agent_id: str) -> int:
        """Deterministic port from agent_id hash, guaranteed free."""
        port = self.base_port + (abs(hash(agent_id)) % 9000)
        used = {c.backend_port for c in self.clients.values()}
        while port in used or not self._port_free(port):
            port += 1
        return port

    @staticmethod
    def _port_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def spawn_client(self, agent_id: str, server_addr: str = Config.DEFAULT_SERVER,
                     memory_mb: int = Config.CLIENT_MEMORY_MB,
                     custom_name: Optional[str] = None,
                     extra_jvm_args: Optional[List[str]] = None) -> Optional[MinecraftClientProcess]:
        """
        Launch a dedicated Minecraft JVM process for an agent.
        Returns None (silently) in CHAT-ONLY mode.
        """
        if not self.minecraft_mode:
            return None

        with self._lock:
            if agent_id in self.clients:
                raise ValueError(f"Agent {agent_id} already has a client")

            port        = self.allocate_port(agent_id)
            backend_url = f"http://127.0.0.1:{port}"

            jvm_args = [
                f"-Xmx{memory_mb}M",
                f"-Xms{memory_mb}M",
                f"-Ddw.agentId={agent_id}",
                f"-Ddw.displayName={custom_name or agent_id}",
                f"-Ddw.server={server_addr}",
                f"-Ddw.backend={backend_url}",
            ]
            if extra_jvm_args:
                jvm_args.extend(extra_jvm_args)

            cmd = ["java"] + jvm_args + ["-jar", str(self.client_jar)]
            log.info(f"Launching client for {agent_id} (port {port}, server {server_addr})")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            client = MinecraftClientProcess(agent_id, process, port, server_addr)
            self.clients[agent_id] = client

            threading.Thread(
                target=self._tail_logs, args=(agent_id, process), daemon=True,
            ).start()

            return client

    def _tail_logs(self, agent_id: str, process: subprocess.Popen):
        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                log.debug(f"[client:{agent_id}] {line.rstrip()}")

    def kill_client(self, agent_id: str):
        with self._lock:
            client = self.clients.pop(agent_id, None)
            if client:
                log.info(f"Killing client for {agent_id}")
                client.kill()

    def get_client(self, agent_id: str) -> Optional[MinecraftClientProcess]:
        return self.clients.get(agent_id)

    def list_clients(self) -> List[str]:
        with self._lock:
            return list(self.clients.keys())

    def cleanup_all(self):
        for aid in list(self.clients.keys()):
            self.kill_client(aid)


# ---------------------------------------------------------------------------
# Base spawner
# ---------------------------------------------------------------------------

class AgentSpawner:
    """
    Creates and manages NPCAgent instances.
    Spawned agents are immediately saved to disk so the packaging
    pipeline can find brain.pcap without a race.
    """

    # Predefined personality templates for god entities.
    # Keys must match choices in agent.py's --god-type argparse arg.
    GOD_CONFIGS: Dict[str, Dict[str, Any]] = {
        'ender_dragon': {
            'memory_mb': 4096,
            'persona_traits': {
                'boldness':       1.0,
                'sociability':   -0.9,
                'openness':       0.5,
                'neuroticism':   -0.3,
            },
            'description': 'Ender Dragon — ultimate boss entity',
        },
        'wither': {
            'memory_mb': 3072,
            'persona_traits': {
                'boldness':       0.9,
                'agreeableness': -0.8,
                'neuroticism':    0.7,
                'curiosity':      0.3,
            },
            'description': 'Aggressive boss with destructive tendencies',
        },
        'warden': {
            'memory_mb': 3072,
            'persona_traits': {
                'boldness':       0.9,
                'curiosity':      0.3,
                'neuroticism':    0.1,
                'agreeableness': -0.7,
            },
            'description': 'Blind but powerful deep-dark guardian',
        },
        'oracle': {
            'memory_mb': 2048,
            'persona_traits': {
                'curiosity':          0.9,
                'sociability':        0.7,
                'openness':           0.9,
                'conscientiousness':  0.6,
            },
            'description': 'Wise entity that provides guidance',
        },
        'elder_guardian': {
            'memory_mb': 2048,
            'persona_traits': {
                'boldness':       0.7,
                'agreeableness': -0.5,
                'conscientiousness': 0.4,
                'neuroticism':    0.3,
            },
            'description': 'Ancient ocean guardian with a stern disposition',
        },
        'creaking': {
            'memory_mb': 2048,
            'persona_traits': {
                'curiosity':    0.8,
                'boldness':     0.4,
                'neuroticism':  0.6,
                'sociability': -0.2,
            },
            'description': 'Mysterious pale-garden entity',
        },
    }

    def __init__(self, client_jar_path: Optional[str] = None):
        if client_jar_path is None and Config.CLIENT_JAR:
            client_jar_path = str(Config.CLIENT_JAR)

        self.client_manager = AgentClientManager(client_jar_path)
        self.agents: Dict[str, NPCAgent] = {}
        self._lock = threading.Lock()

        mode = "MINECRAFT" if self.client_manager.minecraft_mode else "CHAT-ONLY"
        log.info(f"AgentSpawner initialised in {mode} mode")

    # ------------------------------------------------------------------
    # Spawn helpers
    # ------------------------------------------------------------------

    def _save_brain(self, agent: NPCAgent):
        """Persist brain immediately — ensures brain.pcap exists for packaging."""
        brain_path = Config.get_agent_brain_path(agent.agent_id)
        brain_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            agent.save(str(brain_path))
            log.debug(f"  Brain saved: {brain_path}")
        except Exception as e:
            log.error(f"  Brain save failed for {agent.agent_id}: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_npc(self, agent_id: str,
                  server_addr:   str = Config.DEFAULT_SERVER,
                  persona_traits:Optional[Dict[str, float]] = None,
                  memory_mb:     int = Config.CLIENT_MEMORY_MB,
                  gender:        Optional[GenderType] = None) -> NPCAgent:
        """Spawn an NPC agent. Works in both CHAT-ONLY and MINECRAFT modes."""
        with self._lock:
            if agent_id in self.agents:
                raise ValueError(f"Agent {agent_id} already exists")

            if persona_traits is None:
                persona_traits = {
                    'openness':          float(np.random.uniform(-0.5,  0.5)),
                    'conscientiousness': float(np.random.uniform(-0.3,  0.7)),
                    'extraversion':      float(np.random.uniform(-0.5,  0.5)),
                    'agreeableness':     float(np.random.uniform( 0.0,  0.8)),
                    'neuroticism':       float(np.random.uniform(-0.3,  0.3)),
                    'boldness':          float(np.random.uniform( 0.0,  0.6)),
                    'curiosity':         float(np.random.uniform( 0.3,  0.8)),
                    'sociability':       float(np.random.uniform( 0.0,  0.7)),
                }

            if gender is None:
                gender = assign_npc_gender()

            client = self.client_manager.spawn_client(
                agent_id=agent_id, server_addr=server_addr, memory_mb=memory_mb,
            )

            agent = NPCAgent(
                agent_id=agent_id, gender=gender,
                persona_traits=persona_traits, client_process=client,
            )
            agent.agent_type = 'npc'

            self._save_brain(agent)
            self.agents[agent_id] = agent
            log.info(f"Spawned NPC: {agent_id} (gender={gender})")
            return agent

    def spawn_god(self, god_type: str,
                  server_addr:  str = Config.DEFAULT_SERVER,
                  custom_traits:Optional[Dict[str, float]] = None) -> NPCAgent:
        """Spawn a god-tier entity."""
        if god_type not in self.GOD_CONFIGS:
            raise ValueError(
                f"Unknown god type: {god_type!r}. "
                f"Available: {', '.join(self.GOD_CONFIGS)}"
            )

        cfg      = self.GOD_CONFIGS[god_type]
        agent_id = f"god_{god_type}_{int(time.time() * 1000)}"

        with self._lock:
            traits = custom_traits or cfg['persona_traits']
            gender = assign_god_gender()

            client = self.client_manager.spawn_client(
                agent_id=agent_id, server_addr=server_addr,
                memory_mb=cfg['memory_mb'],
            )

            agent = NPCAgent(
                agent_id=agent_id, gender=gender,
                persona_traits=traits, client_process=client,
                god_type=god_type,
            )
            agent.agent_type = f'god_{god_type}'

            self._save_brain(agent)
            self.agents[agent_id] = agent
            log.info(f"Spawned God: {god_type} → {agent_id}")
            return agent

    def get_agent(self, agent_id: str) -> Optional[NPCAgent]:
        return self.agents.get(agent_id)

    def list_agents(self) -> List[str]:
        with self._lock:
            return list(self.agents.keys())

    def get_agents_by_type(self, agent_type: str) -> List[NPCAgent]:
        return [a for a in self.agents.values() if a.agent_type.startswith(agent_type)]

    def get_all_agents_info(self) -> Dict[str, Dict[str, Any]]:
        return {aid: a.get_info() for aid, a in self.agents.items()}

    def despawn_agent(self, agent_id: str):
        with self._lock:
            agent = self.agents.pop(agent_id, None)
            if agent is None:
                log.warning(f"despawn: {agent_id} not found")
                return
            self._save_brain(agent)
            self.client_manager.kill_client(agent_id)
            log.info(f"Despawned: {agent_id}")

    def cleanup_all(self):
        log.info("AgentSpawner: cleaning up all agents…")
        for aid in list(self.agents.keys()):
            try:
                self._save_brain(self.agents[aid])
            except Exception as e:
                log.error(f"Save failed for {aid}: {e}")
        for aid in list(self.agents.keys()):
            self.despawn_agent(aid)
        self.client_manager.cleanup_all()
        log.info("AgentSpawner: cleanup complete")


# ---------------------------------------------------------------------------
# UltimMC-backed spawner (used as delegate inside auto_packager)
# ---------------------------------------------------------------------------

class UltimMCAgentSpawner(AgentSpawner):
    """
    Extends AgentSpawner with full UltimMC automation.

    When UltimMC is available, spawn_npc / spawn_god:
      1. Creates an offline Minecraft account with a proper UUID
      2. Creates a Forge 1.20.1 instance
      3. Installs DivineWorld + DWClientBot mods
      4. Launches via UltimMC with agent system properties
         (-Ddw.agentId, -Ddw.backend, -Ddw.server)
      5. Supports headless mode via xvfb-run

    Falls back to the base AgentSpawner behaviour if UltimMC is absent.

    This class is imported by auto_packager.EnhancedAgentSpawner as its
    UltimMC delegate.  It is NOT EnhancedAgentSpawner itself — that lives
    in auto_packager.py and adds packaging on top.
    """

    def __init__(self, client_jar_path: Optional[str] = None,
                 headless: bool = False):
        super().__init__(client_jar_path)

        self.headless = headless

        # Import here so the module is optional at test time
        from py_backend.minecraft_launcher import UltimMCLauncher, MultiAgentLauncher
        self._launcher_cls       = UltimMCLauncher
        self._multi_launcher_cls = MultiAgentLauncher

        self._ultimmc = UltimMCLauncher(
            client_jar_path=client_jar_path,
            mod_jar_path=str(Config.MOD_JAR) if Config.MOD_JAR else None,
        )
        self._multi = MultiAgentLauncher()

        if self._ultimmc.source_ultimmc_path:
            log.info("✅ UltimMCAgentSpawner: UltimMC automation active")
        else:
            log.warning("⚠️  UltimMCAgentSpawner: UltimMC not found — base spawner used")

    @property
    def ultimmc_available(self) -> bool:
        return bool(self._ultimmc.source_ultimmc_path)

    def spawn_npc(self, agent_id: str,
                  server_addr:   str = Config.DEFAULT_SERVER,
                  persona_traits:Optional[Dict[str, float]] = None,
                  memory_mb:     int = Config.CLIENT_MEMORY_MB,
                  gender:        Optional[GenderType] = None) -> NPCAgent:

        if not self.ultimmc_available:
            return super().spawn_npc(agent_id, server_addr, persona_traits, memory_mb, gender)

        with self._lock:
            if agent_id in self.agents:
                raise ValueError(f"Agent {agent_id} already exists")

            if persona_traits is None:
                persona_traits = {
                    'openness':          float(np.random.uniform(-0.5,  0.5)),
                    'conscientiousness': float(np.random.uniform(-0.3,  0.7)),
                    'extraversion':      float(np.random.uniform(-0.5,  0.5)),
                    'agreeableness':     float(np.random.uniform( 0.0,  0.8)),
                    'neuroticism':       float(np.random.uniform(-0.3,  0.3)),
                    'boldness':          float(np.random.uniform( 0.0,  0.6)),
                    'curiosity':         float(np.random.uniform( 0.3,  0.8)),
                    'sociability':       float(np.random.uniform( 0.0,  0.7)),
                }
            if gender is None:
                gender = assign_npc_gender()

            # Resolve display name from agents.json — no DW_ prefix
            from py_backend.utils.mc_uuid import AgentNameManager as _ANM
            minecraft_name = _ANM().resolve_display_name(agent_id)
            agent_uuid     = get_minecraft_uuid(minecraft_name)

            # Setup UltimMC instance for this agent
            ok = self._multi.setup_agent(
                agent_id=agent_id, server_addr=server_addr,
                custom_uuid=agent_uuid, agent_type='npc',
                custom_name=minecraft_name,
                source_launcher=self._ultimmc,
            )
            if not ok:
                log.warning(f"UltimMC setup failed for {agent_id} — falling back")
                return super().spawn_npc(
                    agent_id, server_addr, persona_traits, memory_mb, gender
                )

            # Allocate backend port and launch
            port        = self.client_manager.allocate_port(agent_id)
            backend_url = f"http://127.0.0.1:{port}"

            process = self._multi.launch_agent(
                agent_id=agent_id, server_addr=server_addr,
                backend_url=backend_url, memory_mb=memory_mb,
                headless=self.headless, agent_type='npc',
            )

            client = None
            if process:
                client = MinecraftClientProcess(agent_id, process, port, server_addr)
                self.client_manager.clients[agent_id] = client
                threading.Thread(
                    target=self.client_manager._tail_logs,
                    args=(agent_id, process), daemon=True,
                ).start()
            else:
                log.warning(f"UltimMC launch failed for {agent_id} — chat-only")

            agent = NPCAgent(
                agent_id=agent_id, gender=gender,
                persona_traits=persona_traits, client_process=client,
            )
            agent.agent_type = 'npc'
            self._save_brain(agent)
            self.agents[agent_id] = agent
            log.info(f"✅ Spawned NPC via UltimMC: {agent_id}")
            return agent

    def spawn_god(self, god_type: str,
                  server_addr:  str = Config.DEFAULT_SERVER,
                  custom_traits:Optional[Dict[str, float]] = None) -> NPCAgent:

        if not self.ultimmc_available:
            return super().spawn_god(god_type, server_addr, custom_traits)

        if god_type not in self.GOD_CONFIGS:
            raise ValueError(f"Unknown god type: {god_type!r}")

        cfg      = self.GOD_CONFIGS[god_type]
        agent_id = f"god_{god_type}_{int(time.time() * 1000)}"

        with self._lock:
            traits = custom_traits or cfg['persona_traits']
            gender = assign_god_gender()

            # Resolve display name from agents.json — no DW_ prefix
            from py_backend.utils.mc_uuid import AgentNameManager as _ANM
            minecraft_name = _ANM().resolve_display_name(agent_id)
            agent_uuid     = get_minecraft_uuid(minecraft_name)

            ok = self._multi.setup_agent(
                agent_id=agent_id, server_addr=server_addr,
                custom_uuid=agent_uuid, agent_type=f'god_{god_type}',
                source_launcher=self._ultimmc,
            )
            if not ok:
                log.warning(f"UltimMC setup failed for god {agent_id} — falling back")
                return super().spawn_god(god_type, server_addr, custom_traits)

            port        = self.client_manager.allocate_port(agent_id)
            backend_url = f"http://127.0.0.1:{port}"

            process = self._multi.launch_agent(
                agent_id=agent_id, server_addr=server_addr,
                backend_url=backend_url, memory_mb=cfg['memory_mb'],
                headless=self.headless, agent_type=f'god_{god_type}',
            )

            client = None
            if process:
                client = MinecraftClientProcess(agent_id, process, port, server_addr)
                self.client_manager.clients[agent_id] = client
                threading.Thread(
                    target=self.client_manager._tail_logs,
                    args=(agent_id, process), daemon=True,
                ).start()
            else:
                log.warning(f"UltimMC launch failed for god {agent_id} — chat-only")

            agent = NPCAgent(
                agent_id=agent_id, gender=gender,
                persona_traits=traits, client_process=client,
                god_type=god_type,
            )
            agent.agent_type = f'god_{god_type}'
            self._save_brain(agent)
            self.agents[agent_id] = agent
            log.info(f"✅ Spawned God via UltimMC: {god_type} → {agent_id}")
            return agent
