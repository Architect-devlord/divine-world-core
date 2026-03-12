# py_backend/auto_packager.py
"""
Auto-Packager with synchronised brain file handling.
=====================================================
Provides:
  AutoPackagingSystem — background + sync packaging of agent .exe files
  EnhancedAgentSpawner — extends AgentSpawner with auto-packaging and
                         optional UltimMC automation

Design notes
------------
EnhancedAgentSpawner is defined HERE, not in agent_spawner.py.
breeding_system.py imports from auto_packager to get the spawner,
not from agent_spawner, so the class is never circular.

Port allocation uses a deterministic hash of agent_id so ports are
consistent across restarts for the same agent.
"""

import os
import json
import logging
import threading
from pathlib import Path
from typing import Optional, List
from queue import Queue, Empty
import time

from ai_core.agent import NPCAgent
from ai_core.agent_spawner import AgentSpawner       # base class only
from packager import AgentPackager
from py_backend.config import Config

log = logging.getLogger("auto_packager")
log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# AutoPackagingSystem
# ---------------------------------------------------------------------------

class AutoPackagingSystem:
    """
    Manages agent packaging — converts an agent + brain capsule into a
    self-contained .exe package.

    Two entry points:
      queue_agent_for_packaging()  — async, background thread
      package_agent_sync()         — blocking, waits for brain file to stabilise
    """

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = str(Config.NPC_APPLICATIONS_DIR)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.packager         = AgentPackager(output_dir=str(self.output_dir))
        self.packaging_queue  = Queue()
        self.packaged_agents: dict = {}

        self._stop_event    = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._packaging_worker, daemon=True
        )
        self._worker_thread.start()
        log.info(f"AutoPackaging initialised (output: {self.output_dir})")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def queue_agent_for_packaging(
        self,
        agent: NPCAgent,
        brain_capsule_path: str,
        metadata: Optional[dict] = None,
    ):
        """Enqueue for async background packaging."""
        self.packaging_queue.put({
            'agent':      agent,
            'brain_path': brain_capsule_path,
            'metadata':   metadata or {},
        })
        log.info(f"Queued {agent.agent_id} for packaging")

    def package_agent_sync(
        self,
        agent: NPCAgent,
        brain_capsule_path: str,
        metadata: Optional[dict] = None,
    ):
        """Package synchronously — blocks until done."""
        log.info(f"Sync packaging {agent.agent_id}…")
        brain_file = Path(brain_capsule_path)
        brain_file  = self._wait_for_stable_brain(brain_file)
        if brain_file is None:
            return
        self._run_packager(agent, str(brain_file), metadata or {})

    # ------------------------------------------------------------------
    # Brain file helpers
    # ------------------------------------------------------------------

    def _wait_for_stable_brain(
        self,
        brain_file: Path,
        max_wait: float = Config.MAX_BRAIN_SAVE_WAIT_SECONDS,
        check_interval: float = Config.BRAIN_STABILITY_WAIT_SECONDS,
        stable_needed: int = Config.MAX_BRAIN_STABILITY_CHECKS,
    ) -> Optional[Path]:
        """
        Wait for brain file to appear and stop growing.
        Returns the Path when stable, or None on timeout.
        """
        elapsed = 0.0
        while not brain_file.exists() and elapsed < max_wait:
            time.sleep(check_interval)
            elapsed += check_interval

        if not brain_file.exists():
            log.error(f"Brain file not found after {max_wait}s: {brain_file}")
            return None

        # Size stability check
        prev_size     = -1
        stable_count  = 0
        while stable_count < stable_needed and elapsed < max_wait:
            current_size = brain_file.stat().st_size
            if current_size == prev_size:
                stable_count += 1
            else:
                stable_count = 0
                prev_size    = current_size
            time.sleep(check_interval)
            elapsed += check_interval

        log.info(f"Brain stable: {brain_file} ({brain_file.stat().st_size:,} bytes)")
        return brain_file

    # ------------------------------------------------------------------
    # Core packaging
    # ------------------------------------------------------------------

    def _run_packager(self, agent: NPCAgent, brain_path: str, metadata: dict):
        """Call AgentPackager and register result."""
        try:
            port   = self._allocate_port(agent.agent_id)
            result = self.packager.package_agent(
                agent_id           = agent.agent_id,
                brain_capsule_path = brain_path,
                agent_name         = getattr(agent, 'custom_name', None),
                gender             = agent.personality.gender if hasattr(agent, 'personality') else 'neutral',
                agent_type         = getattr(agent, 'agent_type', 'npc'),
                include_frontend   = True,
                include_mod        = True,
                include_client_jar = True,
                backend_port       = port,
            )
            result['metadata']     = metadata
            result['backend_port'] = port
            result['frontend_port']= port + 1

            self.packaged_agents[agent.agent_id] = result
            self._save_package_registry()
            log.info(f"✅ Packaged {agent.agent_id} → {result['exe_path']} (port {port})")
        except Exception as e:
            log.error(f"Packaging failed for {agent.agent_id}: {e}", exc_info=True)

    def _packaging_worker(self):
        """Background packaging thread."""
        log.info("Packaging worker started")
        while not self._stop_event.is_set():
            try:
                req = self.packaging_queue.get(timeout=1.0)
                agent      = req['agent']
                brain_path = req['brain_path']
                metadata   = req['metadata']

                brain_file = self._wait_for_stable_brain(Path(brain_path), max_wait=3000)
                if brain_file is None:
                    continue
                self._run_packager(agent, str(brain_file), metadata)

            except Empty:
                continue
            except Exception as e:
                log.error(f"Worker error: {e}", exc_info=True)
        log.info("Packaging worker stopped")

    # ------------------------------------------------------------------
    # Port allocation
    # ------------------------------------------------------------------

    def _allocate_port(self, agent_id: str, base_port: int = Config.BASE_BACKEND_PORT) -> int:
        """
        Deterministic port from agent_id hash so the same agent always
        gets the same port across restarts.
        """
        offset = abs(hash(agent_id)) % 9000
        port   = base_port + offset
        used   = {
            info['backend_port']
            for info in self.packaged_agents.values()
            if 'backend_port' in info
        }
        while port in used:
            port += 1
        return port

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def _save_package_registry(self):
        registry = self.output_dir / "package_registry.json"
        with open(registry, 'w') as f:
            json.dump(self.packaged_agents, f, indent=2)

    def get_package_info(self, agent_id: str) -> Optional[dict]:
        return self.packaged_agents.get(agent_id)

    def list_packaged_agents(self) -> List[str]:
        return list(self.packaged_agents.keys())

    def cleanup_build_artifacts(self):
        self.packager.cleanup_build_artifacts()

    def shutdown(self):
        log.info("Shutting down AutoPackaging…")
        self._stop_event.set()
        self._worker_thread.join(timeout=5.0)
        log.info("AutoPackaging stopped")


# ---------------------------------------------------------------------------
# EnhancedAgentSpawner
# ---------------------------------------------------------------------------

class EnhancedAgentSpawner(AgentSpawner):
    """
    AgentSpawner extended with:
      - Auto-packaging (produces .exe after each spawn)
      - Optional UltimMC automation for Minecraft client setup
      - BreedingSystem attachment to every spawned agent

    This is the spawner used everywhere in py_backend.
    breeding_system.py receives an instance of this class.
    """

    def __init__(
        self,
        client_jar_path:   Optional[str] = None,
        auto_package:      bool = True,
        package_output_dir:Optional[str] = None,
        use_ultimmc:       Optional[bool] = None,
    ):
        if client_jar_path is None and Config.CLIENT_JAR:
            client_jar_path = str(Config.CLIENT_JAR)

        super().__init__(client_jar_path)

        self.auto_package   = auto_package
        self.packager: Optional[AutoPackagingSystem] = None

        if auto_package:
            self.packager = AutoPackagingSystem(
                output_dir=package_output_dir or str(Config.NPC_APPLICATIONS_DIR)
            )

        # UltimMC — auto-detect if not specified
        if use_ultimmc is None:
            use_ultimmc = Config.USE_ULTIMMC
        self.use_ultimmc = use_ultimmc

        self._ultimmc_spawner = None
        if self.use_ultimmc:
            try:
                # UltimMC spawner is a separate implementation in agent_spawner
                from ai_core.agent_spawner import UltimMCAgentSpawner
                self._ultimmc_spawner = UltimMCAgentSpawner(client_jar_path=client_jar_path)
                log.info("✅ UltimMC automation available")
            except (ImportError, Exception) as e:
                log.warning(f"UltimMC not available: {e}")
                self.use_ultimmc = False

        # Will be set externally by the breeding system after init
        self._breeding_system = None

    # ------------------------------------------------------------------
    # Spawn helpers
    # ------------------------------------------------------------------

    def _post_spawn(self, agent: NPCAgent, server_addr: str, extra_meta: dict):
        """
        Common post-spawn steps:
          1. Verify brain file exists
          2. Attach breeding system (if registered)
          3. Queue for packaging
        """
        brain_path = Config.get_agent_brain_path(agent.agent_id)

        if not brain_path.exists():
            log.warning(
                f"Brain not found at {brain_path} — "
                f"agent may not have saved yet"
            )

        # Attach breeding system so the agent can serialise pregnancy state
        if self._breeding_system is not None:
            self._breeding_system.attach_to_agent(agent)

        if self.auto_package and self.packager and brain_path.exists():
            meta = {
                'server':     server_addr,
                'spawn_time': time.time(),
                **extra_meta,
            }
            self.packager.queue_agent_for_packaging(agent, str(brain_path), meta)

        return agent

    def spawn_npc(
        self,
        agent_id:      str,
        server_addr:   str = Config.DEFAULT_SERVER,
        persona_traits:Optional[dict] = None,
        memory_mb:     int = Config.CLIENT_MEMORY_MB,
        gender:        Optional[str] = None,
    ) -> NPCAgent:
        """Spawn NPC, attach breeding, queue packaging."""
        if self.use_ultimmc and self._ultimmc_spawner:
            try:
                agent = self._ultimmc_spawner.spawn_npc(
                    agent_id, server_addr, persona_traits, memory_mb, gender
                )
            except Exception as e:
                log.warning(f"UltimMC spawn failed, using base spawner: {e}")
                agent = super().spawn_npc(agent_id, server_addr, persona_traits, memory_mb, gender)
        else:
            agent = super().spawn_npc(agent_id, server_addr, persona_traits, memory_mb, gender)

        return self._post_spawn(agent, server_addr, {'spawn_type': 'npc'})

    def spawn_god(
        self,
        god_type:     str,
        server_addr:  str = Config.DEFAULT_SERVER,
        custom_traits:Optional[dict] = None,
    ) -> NPCAgent:
        """Spawn god agent, attach breeding, queue packaging."""
        if self.use_ultimmc and self._ultimmc_spawner:
            try:
                agent = self._ultimmc_spawner.spawn_god(god_type, server_addr, custom_traits)
            except Exception as e:
                log.warning(f"UltimMC god spawn failed, using base spawner: {e}")
                agent = super().spawn_god(god_type, server_addr, custom_traits)
        else:
            agent = super().spawn_god(god_type, server_addr, custom_traits)

        return self._post_spawn(agent, server_addr, {'spawn_type': 'god', 'god_type': god_type})

    # ------------------------------------------------------------------
    # Manual packaging trigger (called from main.py)
    # ------------------------------------------------------------------

    def package_agent(
        self,
        agent_id:   str,
        brain_path: str,
        agent_type: str,
        custom_name:str,
        gender:     str = "neutral",
    ) -> Optional[Path]:
        """Manually trigger packaging for an already-spawned agent."""
        if not self.packager:
            return None
        try:
            # If no gender was passed by the caller, try to read it from the
            # brain capsule directly so we never stamp "neutral" into the
            # brain.pcap.json sidecar when the agent actually has a real gender.
            resolved_gender = gender
            if resolved_gender == "neutral":
                try:
                    from ai_core.brain_capsule import BrainCapsule
                    caps = BrainCapsule.load(brain_path)
                    if caps.gender and caps.gender != "neutral":
                        resolved_gender = caps.gender
                        log.info(f"Gender from brain capsule: {resolved_gender}")
                    elif caps.personality and caps.personality.get("gender"):
                        resolved_gender = caps.personality["gender"]
                        log.info(f"Gender from personality: {resolved_gender}")
                except Exception as eg:
                    log.debug(f"Could not read gender from brain: {eg}")

            port   = self.packager._allocate_port(agent_id)
            result = self.packager.packager.package_agent(
                agent_id           = agent_id,
                brain_capsule_path = brain_path,
                agent_name         = custom_name,
                agent_type         = agent_type,
                gender             = resolved_gender,
                backend_port       = port,
            )
            self.packager.packaged_agents[agent_id] = result
            self.packager._save_package_registry()
            return Path(result['package_path'])
        except Exception as e:
            log.error(f"Manual packaging failed for {agent_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_all(self):
        super().cleanup_all()
        if self.packager:
            self.packager.shutdown()