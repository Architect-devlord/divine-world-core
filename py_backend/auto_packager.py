# py_backend/auto_packager.py - FIXED VERSION
"""
Enhanced Auto-Packager with:
- Longer brain file wait time (30s)
- Better file stability detection
- Multi-agent frontend support (unique ports per agent)
- Proper synchronization
"""

import os
import json
import logging
import threading
from pathlib import Path
from typing import Optional
from queue import Queue, Empty
import time

from ai_core.agent_spawner import AgentSpawner, EnhancedAgentSpawner
from ai_core.agent import NPCAgent
from packager import AgentPackager

log = logging.getLogger("auto_packager")
log.setLevel(logging.INFO)


class AutoPackagingSystem:
    """
    Enhanced auto-packaging with proper synchronization.
    """
    
    def __init__(self, output_dir: str = "npc_applications"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.packager = AgentPackager(output_dir=str(self.output_dir))
        self.packaging_queue = Queue()
        self.packaged_agents: dict[str, dict[str, str]] = {}
        
        # Background worker thread
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._packaging_worker,
            daemon=True
        )
        self._worker_thread.start()
        
        log.info(f"AutoPackaging system initialized (output: {self.output_dir})")
    
    def queue_agent_for_packaging(self, agent: NPCAgent,
                                   brain_capsule_path: str,
                                   metadata: Optional[dict[str, any]] = None):
        """Queue an agent for packaging"""
        package_request = {
            'agent': agent,
            'brain_path': brain_capsule_path,
            'metadata': metadata or {}
        }
        
        self.packaging_queue.put(package_request)
        log.info(f"✅ Queued {agent.agent_id} for packaging")
    
    def package_agent_sync(self, agent: NPCAgent, brain_capsule_path: str, metadata: Optional[dict[str, any]] = None):
        """Package agent synchronously"""
        log.info(f"📦 Sync packaging {agent.agent_id}...")
        
        brain_file = Path(brain_capsule_path)
        max_wait = 30
        elapsed = 0
        
        log.info(f"⏳ Waiting for brain file: {brain_capsule_path}")
        
        while not brain_file.exists() and elapsed < max_wait:
            time.sleep(0.5)
            elapsed += 0.5
        
        if not brain_file.exists():
            log.error(f"Brain file not found: {brain_capsule_path}")
            return
        
        # Stability check
        log.info(f"✅ Brain file found, verifying stability...")
        
        prev_size = -1
        current_size = brain_file.stat().st_size
        stable_checks = 0
        
        while stable_checks < 3 and elapsed < max_wait:
            time.sleep(0.5)
            elapsed += 0.5
            new_size = brain_file.stat().st_size
            if new_size == current_size:
                stable_checks += 1
            else:
                current_size = new_size
                stable_checks = 0
        
        log.info(f"✅ Brain file stable: {brain_capsule_path} ({current_size:,} bytes)")
        
        # Package
        try:
            result = self.packager.package_agent(
                agent_id=agent.agent_id,
                brain_capsule_path=brain_capsule_path,
                gender=agent.gender,
                agent_type=agent.agent_type,
                backend_port=self._allocate_port(agent.agent_id)
            )
            self.packaged_agents[agent.agent_id] = result
            self._save_package_registry()
            log.info(f"✅ Sync packaged {agent.agent_id}: {result['exe_path']}")
        except Exception as e:
            log.error(f"❌ Sync packaging failed for {agent.agent_id}: {e}")
    
    def _packaging_worker(self):
        """Enhanced background worker with better synchronization"""
        log.info("📦 Packaging worker started")
        
        while not self._stop_event.is_set():
            try:
                # Wait for packaging request
                request = self.packaging_queue.get(timeout=1.0)
                
                agent = request['agent']
                brain_path = request['brain_path']
                metadata = request['metadata']
                
                log.info(f"📦 Packaging {agent.agent_id}...")
                
                # ENHANCED: Wait for brain file with better detection
                brain_file = Path(brain_path)
                max_wait = 30  # INCREASED from 10 to 30 seconds
                wait_interval = 0.5
                elapsed = 0
                
                log.info(f"⏳ Waiting for brain file: {brain_path}")
                
                while not brain_file.exists() and elapsed < max_wait:
                    log.debug(f"   Waiting... ({elapsed:.1f}s / {max_wait}s)")
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                
                if not brain_file.exists():
                    log.error(f"❌ Brain file timeout after {max_wait}s: {brain_path}")
                    log.error(f"   Expected location: {brain_file.absolute()}")
                    
                    # List what's actually in the directory
                    brain_dir = brain_file.parent
                    if brain_dir.exists():
                        files = list(brain_dir.iterdir())
                        log.error(f"   Directory contents ({len(files)} files):")
                        for f in files[:10]:
                            log.error(f"     - {f.name} ({f.stat().st_size} bytes)")
                    
                    continue
                
                # ENHANCED: Wait for file size to stabilize (ensure write is complete)
                log.info(f"✅ Brain file found, verifying stability...")
                
                prev_size = -1
                current_size = brain_file.stat().st_size
                stable_checks = 0
                
                while stable_checks < 3 and elapsed < max_wait:
                    if prev_size == current_size:
                        stable_checks += 1
                    else:
                        stable_checks = 0
                    
                    prev_size = current_size
                    time.sleep(0.3)
                    elapsed += 0.3
                    
                    if brain_file.exists():
                        current_size = brain_file.stat().st_size
                
                log.info(f"✅ Brain file stable: {brain_path} ({current_size:,} bytes)")
                
                try:
                    # Generate unique backend port for this agent
                    backend_port = self._allocate_port(agent.agent_id)
                    
                    # Generate .exe
                    result = self.packager.package_agent(
                        agent_id=agent.agent_id,
                        brain_capsule_path=brain_path,
                        gender=agent.personality.gender,
                        agent_type=agent.agent_type,
                        icon_path=None,
                        include_frontend=True,
                        include_mod=True,
                        include_client_jar=True,
                        backend_port=backend_port  # NEW: Pass unique port
                    )
                    
                    # Store metadata
                    result['metadata'] = metadata
                    result['agent_type'] = agent.agent_type
                    result['personality'] = agent.personality.to_dict()
                    result['backend_port'] = backend_port
                    result['frontend_port'] = backend_port + 1
                    
                    # Save package info
                    self.packaged_agents[agent.agent_id] = result
                    self._save_package_registry()
                    
                    log.info(f"✅ Successfully packaged {agent.agent_id}")
                    log.info(f"   Executable: {result['exe_path']}")
                    log.info(f"   Package: {result['package_path']}")
                    log.info(f"   Backend Port: {backend_port}")
                    log.info(f"   Frontend Port: {backend_port + 1}")
                    
                except Exception as e:
                    log.error(f"❌ Failed to package {agent.agent_id}: {e}")
                    import traceback
                    log.error(traceback.format_exc())
                
            except Empty:
                continue
            except Exception as e:
                log.error(f"Worker error: {e}")
                import traceback
                log.error(traceback.format_exc())
        
        log.info("Packaging worker stopped")
    
    def _allocate_port(self, agent_id: str, base_port: int = 11400) -> int:
        """
        Allocate unique port for agent.
        Uses hash to ensure consistency across runs.
        """
        # Use hash of agent_id to get consistent offset
        port_offset = abs(hash(agent_id)) % 9000  # Avoid system ports
        port = base_port + port_offset
        
        # Ensure not already in use by another packaged agent
        used_ports = {
            info['backend_port'] 
            for info in self.packaged_agents.values() 
            if 'backend_port' in info
        }
        
        while port in used_ports:
            port += 1
        
        return port
    
    def _save_package_registry(self):
        """Save registry of packaged agents"""
        registry_path = self.output_dir / "package_registry.json"
        
        with open(registry_path, 'w') as f:
            json.dump(self.packaged_agents, f, indent=2)
    
    def get_package_info(self, agent_id: str) -> Optional[dict[str, any]]:
        """Get package information for an agent"""
        return self.packaged_agents.get(agent_id)
    
    def list_packaged_agents(self) -> list:
        """List all packaged agents"""
        return list(self.packaged_agents.keys())
    
    def cleanup_build_artifacts(self):
        """Clean up temporary build files"""
        self.packager.cleanup_build_artifacts()
    
    def shutdown(self):
        """Shutdown the packaging system"""
        log.info("Shutting down auto-packaging system...")
        self._stop_event.set()
        self._worker_thread.join(timeout=5.0)
        log.info("Auto-packaging system stopped")


class EnhancedAgentSpawner(AgentSpawner):
    """
    Enhanced spawner with:
    - Multi-agent port allocation
    - Auto-packaging system
    - UltimMC automation for Minecraft setup
    
    Handles complete lifecycle of agent spawn → setup → package
    """
    
    def __init__(self, client_jar_path: Optional[str] = "DWClientBot.jar",
                 auto_package: bool = True,
                 package_output_dir: str = "npc_applications",
                 use_ultimmc: bool = None):
        """
        Initialize enhanced spawner.
        
        Args:
            client_jar_path: Path to DWClientBot.jar
            auto_package: Enable auto-packaging
            package_output_dir: Output directory for packages
            use_ultimmc: Use UltimMC for automation (auto-detect if None)
        """
        super().__init__(client_jar_path)
        
        self.auto_package = auto_package
        self.packager = None
        self.use_ultimmc = use_ultimmc
        
        if auto_package:
            self.packager = AutoPackagingSystem(output_dir=package_output_dir)
            log.info("Auto-packaging enabled")
        
        # Setup UltimMC if requested or available
        if use_ultimmc is None:
            # Auto-detect: try to use UltimMC if available
            from py_backend.config import Config
            self.use_ultimmc = Config.USE_ULTIMMC
        
        if self.use_ultimmc:
            try:
                from ai_core.agent_spawner import EnhancedAgentSpawner as UltimMCSpawner
                # Create a wrapper that combines both
                self._ultimmc_spawner = UltimMCSpawner(client_jar_path=client_jar_path)
                log.info("✅ UltimMC automation available")
            except Exception as e:
                log.warning(f"UltimMC not available: {e}")
                self.use_ultimmc = False
                self._ultimmc_spawner = None
    
    def spawn_npc(self, agent_id: str, server_addr: str = "127.0.0.1:25565",
                  persona_traits: Optional[dict[str, float]] = None,
                  memory_mb: int = 2048,
                  gender: Optional[str] = None) -> NPCAgent:
        """Spawn NPC with UltimMC automation if available"""
        
        # Try UltimMC path first
        if self.use_ultimmc and self._ultimmc_spawner:
            try:
                log.info(f"Spawning {agent_id} with UltimMC automation...")
                agent = self._ultimmc_spawner.spawn_npc(
                    agent_id=agent_id,
                    server_addr=server_addr,
                    persona_traits=persona_traits,
                    memory_mb=memory_mb,
                    gender=gender
                )
            except Exception as e:
                log.warning(f"UltimMC spawn failed, falling back: {e}")
                agent = super().spawn_npc(agent_id, server_addr, persona_traits, memory_mb, gender)
        else:
            # Regular spawn
            agent = super().spawn_npc(agent_id, server_addr, persona_traits, memory_mb, gender)
        
        # Queue for packaging
        from py_backend.config import Config
        brain_path = Path(Config.BRAINS_DIR) / agent.agent_id / "brain.pcap"
        
        if not brain_path.exists():
            log.error(f"Brain not found after spawn: {brain_path}")
            raise RuntimeError(f"Brain file missing: {brain_path}")
        
        if self.auto_package and self.packager:
            import time
            metadata = {
                'spawned_at': agent.client_process.started_at if agent.client_process else time.time(),
                'server': server_addr,
                'memory_mb': memory_mb,
                'spawn_type': 'command',
                'ultimmc_used': self.use_ultimmc and self._ultimmc_spawner is not None,
            }
            
            self.packager.package_agent_sync(
                agent=agent,
                brain_capsule_path=str(brain_path),
                metadata=metadata
            )
        
        return agent
    
    def spawn_god(self, god_type: str, server_addr: str = "127.0.0.1:25565",
                  custom_traits: Optional[dict[str, float]] = None) -> NPCAgent:
        """Spawn god entity with UltimMC automation if available"""
        
        # Try UltimMC path first
        if self.use_ultimmc and self._ultimmc_spawner:
            try:
                log.info(f"Spawning god {god_type} with UltimMC automation...")
                agent = self._ultimmc_spawner.spawn_god(god_type, server_addr, custom_traits)
            except Exception as e:
                log.warning(f"UltimMC god spawn failed, falling back: {e}")
                agent = super().spawn_god(god_type, server_addr, custom_traits)
        else:
            agent = super().spawn_god(god_type, server_addr, custom_traits)
        
        from py_backend.config import Config
        brain_path = Path(Config.BRAINS_DIR) / agent.agent_id / "brain.pcap"
        
        if not brain_path.exists():
            log.error(f"Brain not found after spawn: {brain_path}")
            raise RuntimeError(f"Brain file missing: {brain_path}")
        
        if self.auto_package and self.packager:
            import time
            metadata = {
                'spawned_at': agent.client_process.started_at if agent.client_process else time.time(),
                'server': server_addr,
                'god_type': god_type,
                'spawn_type': 'command',
                'ultimmc_used': self.use_ultimmc and self._ultimmc_spawner is not None,
            }
            
            self.packager.package_agent_sync(
                agent=agent,
                brain_capsule_path=str(brain_path),
                metadata=metadata
            )
        
        return agent
    
    def cleanup_all(self):
        """Enhanced cleanup"""
        super().cleanup_all()
        
        if self.packager:
            self.packager.shutdown()