# ai_core/agent_spawner.py - FIXED VERSION with None handling
"""
Centralized agent spawning system - FIXED VERSION
Handles all spawning logic for NPCs and God-tier entities.
Each spawned agent is completely independent and standalone.
Should support operation without Minecraft client (chat/learning mode only).
"""
import subprocess
import socket
import time
import json
import threading
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from ai_core.agent import NPCAgent
from ai_core.personality import GenderType, assign_npc_gender

log = logging.getLogger("agent_spawner")
log.setLevel(logging.INFO)


class MinecraftClientProcess:
    """Represents a dedicated Minecraft client process for an agent"""
    
    def __init__(self, agent_id: str, process: subprocess.Popen,
                 backend_port: int, server_addr: str):
        self.agent_id = agent_id
        self.process = process
        self.backend_port = backend_port
        self.backend_url = f"http://127.0.0.1:{backend_port}"
        self.server_addr = server_addr
        self.started_at = time.time()
        self.is_alive = True
        
    def kill(self):
        """Terminate the client process"""
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.is_alive = False


class AgentClientManager:
    """
    Manages dedicated Minecraft clients for each AI agent.
    Each agent gets its own Java process and backend connection.
    Can operate without client jar for chat/learning-only mode.
    """
    
    def __init__(self, client_jar_path: Optional[str] = "DWClientBot.jar", 
                 base_backend_port: int = 11400):
        # CRITICAL FIX: Handle None client_jar_path
        if client_jar_path is None:
            self.client_jar = None
            self.minecraft_mode = False
            log.info("AgentClientManager initialized in CHAT-ONLY mode (no Minecraft)")
        else:
            self.client_jar = Path(client_jar_path)
            self.minecraft_mode = self.client_jar.exists()
            
            if not self.minecraft_mode:
                log.warning(f"Client jar not found: {client_jar_path} (chat-only mode)")
            else:
                log.info(f"AgentClientManager initialized with Minecraft support: {client_jar_path}")
            
        self.base_port = base_backend_port
        self.clients: dict[str, MinecraftClientProcess] = {}
        self.lock = threading.Lock()
        
    def allocate_port(self, agent_id: str) -> int:
        """Allocate unique port for agent backend"""
        port_offset = hash(agent_id) % 10000
        port = self.base_port + port_offset
        
        # Ensure port is free
        while not self._is_port_free(port):
            port += 1
            
        return port
    
    def _is_port_free(self, port: int) -> bool:
        """Check if port is available"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return True
            except OSError:
                return False
    
    def spawn_client(self, agent_id: str, server_addr: str = "127.0.0.1:25565",
                     memory_mb: int = 2048) -> Optional[MinecraftClientProcess]:
        """
        Spawn dedicated Minecraft client for an agent.
        Returns MinecraftClientProcess object or None if not in Minecraft mode.
        """
        with self.lock:
            # If no Minecraft mode, return None immediately
            if not self.minecraft_mode:
                log.debug(f"Skipping client spawn for {agent_id} (chat-only mode)")
                return None
            
            if agent_id in self.clients:
                raise ValueError(f"Agent {agent_id} already has a client")
            
            backend_port = self.allocate_port(agent_id)
            backend_url = f"http://127.0.0.1:{backend_port}"
            
            # Java command
            java_cmd = [
                "java",
                f"-Xmx{memory_mb}M",
                f"-Xms{memory_mb}M",
                f"-Ddw.agentId={agent_id}",
                f"-Ddw.server={server_addr}",
                f"-Ddw.backend={backend_url}",
                "-jar",
                str(self.client_jar)
            ]
            
            log.info(f"Launching client for {agent_id}")
            log.info(f"  Backend: {backend_url}")
            log.info(f"  Server: {server_addr}")
            log.info(f"  Memory: {memory_mb}MB")
            
            # Start process
            process = subprocess.Popen(
                java_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Create client process object
            client_process = MinecraftClientProcess(
                agent_id=agent_id,
                process=process,
                backend_port=backend_port,
                server_addr=server_addr
            )
            
            self.clients[agent_id] = client_process
            
            # Start log reader thread
            threading.Thread(
                target=self._read_client_logs,
                args=(agent_id, process),
                daemon=True
            ).start()
            
            return client_process
    
    def _read_client_logs(self, agent_id: str, process: subprocess.Popen):
        """Read and log client output"""
        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                log.debug(f"[Client:{agent_id}] {line.strip()}")
    
    def kill_client(self, agent_id: str):
        """Terminate client for an agent"""
        with self.lock:
            if agent_id not in self.clients:
                return
            
            client = self.clients[agent_id]
            log.info(f"Killing client for {agent_id}")
            
            client.kill()
            del self.clients[agent_id]
    
    def get_client(self, agent_id: str) -> Optional[MinecraftClientProcess]:
        """Get client process for agent"""
        return self.clients.get(agent_id)
    
    def list_clients(self) -> List[str]:
        """List all active agent clients"""
        with self.lock:
            return list(self.clients.keys())
    
    def cleanup_all(self):
        """Kill all agent clients"""
        for agent_id in list(self.clients.keys()):
            self.kill_client(agent_id)


class AgentSpawner:
    """
    Main spawner that creates and manages all AI agents.
    Handles both NPCs and God-tier entities.
    Supports chat-only mode without Minecraft.
    """
    
    # God entity configurations
    GOD_CONFIGS = {
        'wither': {
            'memory_mb': 3072,
            'persona_traits': {
                'boldness': 0.9,
                'agreeableness': -0.8,
                'neuroticism': 0.7,
                'curiosity': 0.3
            },
            'description': 'Aggressive boss entity with destructive tendencies'
        },
        'warden': {
            'memory_mb': 3072,
            'persona_traits': {
                'boldness': 0.9,
                'curiosity': 0.3,
                'neuroticism': 0.1,
                'agreeableness': -0.7
            },
            'description': 'Blind but powerful deep dark guardian'
        },
        'dragon': {
            'memory_mb': 4096,
            'persona_traits': {
                'boldness': 1.0,
                'sociability': -0.9,
                'openness': 0.5,
                'neuroticism': -0.3
            },
            'description': 'Ender Dragon - ultimate boss entity'
        },
        'oracle': {
            'memory_mb': 2048,
            'persona_traits': {
                'curiosity': 0.9,
                'sociability': 0.7,
                'openness': 0.9,
                'conscientiousness': 0.6
            },
            'description': 'Wise entity that provides guidance'
        },
        'creaking': {
            'memory_mb': 2048,
            'persona_traits': {
                'curiosity': 0.8,
                'boldness': 0.4,
                'neuroticism': 0.6,
                'sociability': -0.2
            },
            'description': 'Mysterious pale garden entity'
        }
    }
    
    def __init__(self, client_jar_path: Optional[str] = "DWClientBot.jar"):
        # CRITICAL FIX: Pass None properly to AgentClientManager
        self.client_manager = AgentClientManager(client_jar_path)
        self.agents: dict[str, NPCAgent] = {}
        self.lock = threading.Lock()
        
        mode = "CHAT-ONLY" if not self.client_manager.minecraft_mode else "MINECRAFT"
        log.info(f"AgentSpawner initialized in {mode} mode")
    
    def spawn_npc(self, agent_id: str, server_addr: str = "127.0.0.1:25565",
                  persona_traits: Optional[dict[str, float]] = None,
                  memory_mb: int = 2048,
                  gender: Optional[GenderType] = None) -> NPCAgent:
        """
        Spawn a regular NPC agent with custom personality.
        
        Args:
            agent_id: Unique identifier for the agent
            server_addr: Minecraft server address (ignored in chat-only mode)
            persona_traits: Custom personality traits (optional)
            memory_mb: JVM memory allocation (ignored in chat-only mode)
            gender: Gender assignment (optional, auto-assigned if None)
            
        Returns:
            NPCAgent instance
        """
        with self.lock:
            if agent_id in self.agents:
                raise ValueError(f"Agent {agent_id} already exists")
            
            # Default persona if not provided
            if persona_traits is None:
                persona_traits = {
                    'openness': np.random.uniform(-0.5, 0.5),
                    'conscientiousness': np.random.uniform(-0.3, 0.7),
                    'extraversion': np.random.uniform(-0.5, 0.5),
                    'agreeableness': np.random.uniform(0.0, 0.8),
                    'neuroticism': np.random.uniform(-0.3, 0.3),
                    'boldness': np.random.uniform(0.0, 0.6),
                    'curiosity': np.random.uniform(0.3, 0.8),
                    'sociability': np.random.uniform(0.0, 0.7)
                }
            
            # Auto-assign gender if not provided
            if gender is None:
                gender = assign_npc_gender()
            
            # Spawn client process (will be None in chat-only mode)
            client_process = self.client_manager.spawn_client(
                agent_id=agent_id,
                server_addr=server_addr,
                memory_mb=memory_mb
            )
            
            # Create NPCAgent
            agent = NPCAgent(
                agent_id=agent_id,
                gender=gender,
                persona_traits=persona_traits,
                client_process=client_process
            )
            
            # Set agent type
            agent.agent_type = 'npc'
            
            # CRITICAL FIX: Save brain immediately after creation
            self._save_agent_brain(agent)
            
            self.agents[agent_id] = agent
            
            log.info(f"Spawned NPC: {agent_id} (gender: {gender})")
            return agent
    
    def spawn_god(self, god_type: str, server_addr: str = "127.0.0.1:25565",
                  custom_traits: Optional[dict[str, float]] = None) -> NPCAgent:
        """
        Spawn a god-tier entity with predefined characteristics.
        
        Args:
            god_type: Type of god ('wither', 'dragon', 'oracle', etc.)
            server_addr: Minecraft server address (ignored in chat-only mode)
            custom_traits: Override default traits (optional)
            
        Returns:
            NPCAgent instance
        """
        if god_type not in self.GOD_CONFIGS:
            available = ', '.join(self.GOD_CONFIGS.keys())
            raise ValueError(f"Unknown god type: {god_type}. Available: {available}")
        
        config = self.GOD_CONFIGS[god_type]
        
        # Generate unique agent ID
        agent_id = f"god_{god_type}_{int(time.time() * 1000)}"
        
        with self.lock:
            # Use custom traits or default config
            persona_traits = custom_traits or config['persona_traits']
            
            # Gods are always 'dual' gender
            from ai_core.personality import assign_god_gender
            gender = assign_god_gender()
            
            # Spawn client process (will be None in chat-only mode)
            client_process = self.client_manager.spawn_client(
                agent_id=agent_id,
                server_addr=server_addr,
                memory_mb=config['memory_mb']
            )
            
            # Create NPCAgent
            agent = NPCAgent(
                agent_id=agent_id,
                gender=gender,
                persona_traits=persona_traits,
                client_process=client_process
            )
            
            # Set god type
            agent.agent_type = f'god_{god_type}'
            
            # CRITICAL FIX: Save brain immediately after creation
            self._save_agent_brain(agent)
            
            self.agents[agent_id] = agent
            
            log.info(f"Spawned God: {god_type} ({agent_id})")
            log.info(f"  Description: {config['description']}")
            return agent
    
    def _save_agent_brain(self, agent: NPCAgent):
        """
        Save agent brain immediately after creation.
        This ensures brain.pcap exists for packaging.
        """
        brain_dir = Path("data/brains") / agent.agent_id
        brain_dir.mkdir(parents=True, exist_ok=True)
        
        brain_path = brain_dir / "brain.pcap"
        
        try:
            agent.save(str(brain_path))
            log.info(f"  Brain saved: {brain_path}")
        except Exception as e:
            log.error(f"  Failed to save brain: {e}")
    
    def despawn_agent(self, agent_id: str):
        """Remove agent and kill its client process"""
        with self.lock:
            if agent_id not in self.agents:
                log.warning(f"Agent {agent_id} not found")
                return
            
            agent = self.agents[agent_id]
            
            # Save final state before despawning
            try:
                self._save_agent_brain(agent)
            except Exception as e:
                log.error(f"Failed to save final brain state: {e}")
            
            self.client_manager.kill_client(agent_id)
            del self.agents[agent_id]
            
            log.info(f"Despawned agent: {agent_id}")
    
    def get_agent(self, agent_id: str) -> Optional[NPCAgent]:
        """Get agent by ID"""
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[str]:
        """List all active agents"""
        with self.lock:
            return list(self.agents.keys())
    
    def get_agents_by_type(self, agent_type: str) -> List[NPCAgent]:
        """Get all agents of a specific type"""
        return [a for a in self.agents.values() if a.agent_type.startswith(agent_type)]
    
    def get_all_agents_info(self) -> dict[str, dict[str, Any]]:
        """Get information about all agents"""
        return {
            agent_id: agent.get_info()
            for agent_id, agent in self.agents.items()
        }
    
    def cleanup_all(self):
        """Shutdown all agents and clients"""
        log.info("Cleaning up all agents...")
        
        # Save all agents before cleanup
        for agent_id in list(self.agents.keys()):
            try:
                agent = self.agents[agent_id]
                self._save_agent_brain(agent)
            except Exception as e:
                log.error(f"Failed to save {agent_id}: {e}")
        
        # Despawn all
        for agent_id in list(self.agents.keys()):
            self.despawn_agent(agent_id)
        
        self.client_manager.cleanup_all()
        log.info("Cleanup complete")