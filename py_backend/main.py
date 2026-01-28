# py_backend/main.py
"""
Divine World Management Server
====================================================
Fixed to match actual Java mod API calls from:
- DWEventHandler.java
- BreedingEventHandler.java
- PythonBackendClient.java
- GodCommand.java
- DivineCommands.java
"""

import asyncio
from curses import raw
import sys
import os
import subprocess
import signal
import psutil
import json
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Optional, Any, List

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import uvicorn
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from auto_packager import EnhancedAgentSpawner
from auto_connect_system import integrate_with_backend

# Initialize logging
from ai_core.logger_setup import initialize_logging
initialize_logging()

log = logging.getLogger("management_server")

# Initialize config
Config.ensure_dirs()
if not Config.validate():
    logging.critical("Configuration validation failed!")
    sys.exit(1)
class MinecraftServerIntegration:
    """Handles Minecraft server folder integration and agent registration."""
        
    def __init__(self):
        self.server_folder: Optional[Path] = None
        self.usercache_path: Optional[Path] = None
        self.usernamecache_path: Optional[Path] = None
    #can  you add taking input for the server folder path

    def get_server_folder(self) -> Path:
        
        
        try:
            from config import Config
            self.folder = Path(Config.SERVER_FOLDER)
            return self.folder
        except Exception:
            self.folder = Path(
                input("Enter ABSOLUTE path of the Minecraft server folder: ").strip()
            )
            if not self.folder.is_absolute() or not self.folder.is_dir():
                raise RuntimeError("Invalid Minecraft server folder")

        return self.folder

    def set_server_folder(self, folder: Path):
        """Set the Minecraft server folder and locate cache files."""
        self.server_folder = folder
        self.usercache_path = folder / "usercache.json"
        self.usernamecache_path = folder / "usernamecache.json"
        log.info(f"Server folder set to: {folder}")
    
    def list_registered_agents(self) -> List[Dict[str, Any]]:
        """List all agents registered in usercache and usernamecache."""
        agents = []
        
        if self.usercache_path and self.usercache_path.exists():
            with open(self.usercache_path, 'r', encoding='utf-8') as f:
                usercache_data = json.load(f)
                for entry in usercache_data:
                    agents.append({
                        'agent_id': entry.get('name'),
                        'uuid': entry.get('uuid'),
                        'type': 'npc'  # Default type; could be enhanced
                    })
        
        return agents
    
server_integration = MinecraftServerIntegration()


try:
    folder_path = server_integration.get_server_folder()
    server_integration.set_server_folder(folder_path)
except Exception as e:
    logging.critical(f"❌ Failed to initialize Minecraft server folder: {e}")
    sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI startup and shutdown."""
    global startup_time
    
    # Startup
    startup_time = asyncio.get_event_loop().time()
    
    log.info("=" * 70)
    log.info("  🎮 Divine World Management Server")
    log.info("=" * 70)
    log.info("  Version: 3.0.0 (Endpoints Corrected + Server Integration)")
    log.info("  Role: Agent Management for Minecraft Mod")
    log.info("  Mod: Divine World 1.20.1")
    log.info("  Agent Runtime: Separate processes (agent.py)")
    log.info("=" * 70)
    log.info("  CORRECTED ENDPOINTS:")
    log.info("    ✅ /api/player_event (DWEventHandler)")
    log.info("    ✅ /api/breeding/event (BreedingEventHandler)")
    log.info("    ✅ /api/genesis/spawn (DivineCommands)")
    log.info("    ✅ /api/divine_reset (DivineCommands)")
    log.info("    ✅ /api/agents/clear_memories (DivineCommands)")
    log.info("    ✅ /api/gods/spawn (DivineCommands)")
    log.info("    ✅ /api/gods/ability (DivineCommands)")
    log.info("    ✅ /api/gods/transform (DivineCommands)")
    log.info("=" * 70)
    log.info("  SERVER INTEGRATION:")
    log.info("    📝 Auto-registers agents in usercache.json")
    log.info("    📝 Auto-registers agents in usernamecache.json")
    log.info("    🔄 UUID generation (Minecraft offline mode)")
    log.info("    🏷️  Naming: AI_<n> for NPCs, GOD_<type>_<n> for gods")
    log.info("=" * 70)
    log.info("")
    log.info("⚠️  IMPORTANT: Configure server folder for agent registration!")
    log.info("   Use: POST /api/server/configure")
    log.info("   Body: {\"server_folder\": \"/path/to/minecraft/server\"}")
    log.info("")
    log.info("✅ Server started and ready for Minecraft mod connections")
    
    yield
    
    # Shutdown
    log.info("🛑 Shutting down management server...")
    
    # Stop all agents
    agent_manager.cleanup_all()
    
    log.info("✅ Shutdown complete")


app = FastAPI(
    title="Divine World Management Server",
    version="3.0.0",
    description="Agent Management & Packaging Server (Endpoints corrected for Java mod)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# AGENT PROCESS MANAGER 
# =============================================================================


class AgentProcessManager:
    """Manages agent processes running independently."""
    
    def __init__(self):
        self.agent_processes: Dict[str, subprocess.Popen] = {}
        self.agent_info: Dict[str, Dict[str, Any]] = {}
        
        self.spawner = EnhancedAgentSpawner(
            client_jar_path=str(Config.CLIENT_JAR) if Config.CLIENT_JAR else None,
            auto_package=True,
            package_output_dir=str(Config.NPC_APPLICATIONS_DIR)
        )
        
        log.info("AgentProcessManager initialized")
    
    def start_agent_process(self, agent_id: str, mode: str = 'autonomous',
                           load_brain: Optional[str] = None,
                           additional_args: List[str] = None,
                           agent_type: str = 'npc',  # 'npc' or 'god_<type>'
                           custom_name: Optional[str] = None) -> bool:
        """Start agent in separate process with auto-packaging."""
        if agent_id in self.agent_processes:
            log.warning(f"Agent {agent_id} already running")
            return False
        
        try:
            # Check if packaged exe exists
            exe_path = Path(Config.NPC_APPLICATIONS_DIR) / agent_id / f"DW_Agent_{agent_id}"
            if exe_path.exists():
                cmd = [str(exe_path)]
                log.info(f"Running packaged agent: {exe_path}")
            else:
                agent_script = Path(__file__).parent.parent / "ai_core" / "agent.py"
                
                cmd = [
                    sys.executable,
                    str(agent_script),
                    '--agent-id', agent_id,
                    '--mode', mode,
                    '--log-level', 'INFO'
                ]
                
                if load_brain:
                    cmd.extend(['--load-brain', load_brain])
                
                if additional_args:
                    cmd.extend(additional_args)
            
            log.info(f"Starting agent process: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            self.agent_processes[agent_id] = process
            self.agent_info[agent_id] = {
                'agent_id': agent_id,
                'mode': mode,
                'pid': process.pid,
                'started_at': asyncio.get_event_loop().time(),
                'brain_path': load_brain,
                'status': 'running',
                'agent_type': agent_type,
                'custom_name': custom_name or "Unnamed"
            }
            
            asyncio.create_task(self._monitor_process_logs(agent_id, process))
            
            # AUTO-PACKAGE: Wait for brain to be created, then package
            asyncio.create_task(self._auto_package_agent(agent_id, agent_type, custom_name))
            
            log.info(f"✅ Agent {agent_id} started (PID: {process.pid})")
            return True
            
        except Exception as e:
            log.error(f"Failed to start agent {agent_id}: {e}")
            return False
    
    async def _auto_package_agent(self, agent_id: str, agent_type: str, custom_name: Optional[str]):
        """
        Automatically package agent after brain is created.
        Waits for brain file to exist, then packages it.
        """
        try:
            # Wait for agent to initialize and create brain file
            brain_path = Config.get_agent_brain_path(agent_id)
            
            log.info(f"[Auto-Package] Waiting for brain file: {brain_path}")
            
            # Wait up to 60 seconds for brain file to be created
            max_wait = 60
            for i in range(max_wait):
                if brain_path.exists():
                    log.info(f"[Auto-Package] Brain file found after {i} seconds")
                    break
                await asyncio.sleep(1)
            else:
                log.warning(f"[Auto-Package] Brain file not created after {max_wait}s: {agent_id}")
                return
            
            # Give brain a moment to finish writing
            await asyncio.sleep(2)
            
            log.info(f"[Auto-Package] Starting package for {agent_id} (type: {agent_type})")
            
            # Package the agent
            package_path = self.spawner.package_agent(
                agent_id=agent_id,
                brain_path=str(brain_path),
                agent_type=agent_type,
                custom_name=custom_name or "Unnamed"
            )
            
            if package_path:
                log.info(f"✅ [Auto-Package] Agent {agent_id} packaged: {package_path}")
                
                # Update agent info
                if agent_id in self.agent_info:
                    self.agent_info[agent_id]['package_path'] = str(package_path)
                    self.agent_info[agent_id]['packaged'] = True
            else:
                log.warning(f"⚠️ [Auto-Package] Failed to package {agent_id}")
            
        except Exception as e:
            log.error(f"[Auto-Package] Error packaging {agent_id}: {e}")
    
    async def _monitor_process_logs(self, agent_id: str, process: subprocess.Popen):
        """Monitor and log agent process output."""
        try:
            loop = asyncio.get_event_loop()
            while process.poll() is None:
                # Read stdout
                if process.stdout:
                    try:
                        line = await loop.run_in_executor(None, process.stdout.readline)
                        if line:
                            log.info(f"[{agent_id}] {line.strip()}")
                    except Exception as e:
                        log.debug(f"Error reading stdout for {agent_id}: {e}")
                
                await asyncio.sleep(0.1)
            
            # Log final status
            if process.returncode == 0:
                log.info(f"Agent {agent_id} exited successfully (code: {process.returncode})")
            else:
                log.warning(f"Agent {agent_id} exited with code: {process.returncode}")
            
            # Update agent info
            if agent_id in self.agent_info:
                self.agent_info[agent_id]['status'] = 'stopped'
                self.agent_info[agent_id]['exit_code'] = process.returncode
        
        except Exception as e:
            log.error(f"Error monitoring logs for {agent_id}: {e}")
        finally:
            # Clean up process reference
            if agent_id in self.agent_processes:
                del self.agent_processes[agent_id]
    
    def cleanup_all(self):
        """Clean up all agent processes and spawner resources."""
        log.info("Cleaning up agent processes...")
        
        if hasattr(self.spawner, 'cleanup_all'):
            self.spawner.cleanup_all()
        
        for agent_id, proc in self.agent_processes.items():
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception as e:
                log.error(f"Error terminating {agent_id}: {e}")
        
        self.agent_processes.clear()
        self.agent_info.clear()
        log.info("Agent cleanup complete")


# Updated spawn_god endpoint with proper agent_type
@app.post("/api/gods/spawn")
async def spawn_god(request: Request):
    """
    Spawn god-tier entity.
    Called by: PythonBackendClient.spawnGodAgent
    """
    try:
        data = await request.json()
        
        god_type = data.get('god_type')
        spawner_name = data.get('spawner')
        world_name = data.get('world')
        spawn_pos = data.get('spawn_position', {})
        
        # God configurations
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
            'ender_dragon': {
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
                'description': 'Wise entity that provides guidance - dual-gendered mystic'
            },
            'creaking': {
                'memory_mb': 2048,
                'persona_traits': {
                    'curiosity': 0.8,
                    'boldness': 0.4,
                    'neuroticism': 0.6,
                    'sociability': -0.2
                },
                'description': 'Mysterious pale garden entity - dual-gendered forest spirit'
            },
            'elder_guardian': {
                'memory_mb': 2560,
                'persona_traits': {
                    'boldness': 0.85,
                    'agreeableness': -0.6,
                    'conscientiousness': 0.7,
                    'sociability': -0.5
                },
                'description': 'Ancient ocean temple guardian - dual-gendered aquatic deity'
            }
        }
        
        if god_type not in GOD_CONFIGS:
            log.warning(f"Unknown god type: {god_type}, using default config")
            config = {
                'memory_mb': 2048,
                'persona_traits': {}
            }
        else:
            config = GOD_CONFIGS[god_type]
        
        # Generate god agent ID (unique identifier)
        timestamp = int(time.time() * 1000)
        agent_id = f"{god_type}_{timestamp}"
        
        # Display name is "Unnamed" for gods
        display_name = "Unnamed"
        
        log.info(f"👑 Spawning god: {god_type} (ID: {agent_id}, Name: {display_name}) - DUAL GENDERED")
        
        # Start god process with CORRECT agent_type for packaging
        success = agent_manager.start_agent_process(
            agent_id=agent_id,
            mode='minecraft',
            additional_args=[
                '--gender', 'dual',  # Gods are dual-gendered
                '--personality', json.dumps(config['persona_traits']),
                '--memory-mb', str(config['memory_mb']),
                '--spawn-x', str(spawn_pos.get('x', 0)),
                '--spawn-y', str(spawn_pos.get('y', 64)),
                '--spawn-z', str(spawn_pos.get('z', 0))
            ],
            agent_type=f'god_{god_type}',  # ✅ CRITICAL: Proper god type for packaging
            custom_name=display_name  # Gods are "Unnamed"
        )
        
        if success:
            return {
                "status": "success",
                "god_type": god_type,
                "agent_id": agent_id,
                "display_name": display_name,
                "gender": "dual",
                "spawner": spawner_name,
                "world": world_name,
                "position": spawn_pos,
                "personality": config['persona_traits'],
                "memory_mb": config['memory_mb'],
                "divine_attributes": {
                    "gender_type": "dual (hermaphroditic - both male and female)",
                    "can_breed": False,
                    "can_breed_with_npcs": True,
                    "offspring_type": "demigod (50% god traits + 50% NPC traits)",
                    "divine_power": 100,
                    "genesis_immune": True
                },
                "god_description": config.get('description', f"{god_type} god entity"),
                "note": "God will be auto-packaged after brain creation",
                "packaging": "Auto-packaging enabled - package will be created in ~5 seconds"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to spawn god {god_type}"
            )
    
    except Exception as e:
        log.error(f"God spawn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NEW ENDPOINT: Spawn single agent (for /dw npc spawn command)
@app.post("/api/agents/spawn_single")
async def spawn_single_agent(request: Request):
    """
    Spawn a single NPC agent (NOT genesis - for /dw npc spawn)
    
    Body format:
        {
            "agent_name": "Alice",
            "spawner": "PlayerName",
            "world": "minecraft:overworld",
            "spawn_position": {"x": 100, "y": 64, "z": 200},
            "gender": "female" (optional, default: random),
            "personality": {...} (optional)
        }
    """
    try:
        data = await request.json()
        
        agent_name = data.get('agent_name')
        spawner_name = data.get('spawner')
        world_name = data.get('world')
        spawn_pos = data.get('spawn_position', {})
        gender = data.get('gender', 'random')
        personality = data.get('personality')
        
        if not agent_name:
            raise HTTPException(status_code=400, detail="Missing agent_name")
        
        # Generate unique agent ID
        timestamp = int(time.time() * 1000)
        agent_id = f"npc_{agent_name.lower().replace(' ', '_')}_{timestamp}"
        
        log.info(f"🧑 Spawning single NPC: {agent_name} (ID: {agent_id})")
        
        # Random gender if not specified
        if gender == 'random':
            import random
            gender = random.choice(['male', 'female'])
        
        # Default personality if not provided
        if not personality:
            personality = {
                'boldness': 0.7,
                'curiosity': 0.8,
                'agreeableness': 0.7,
                'conscientiousness': 0.7,
                'neuroticism': 0.3,
                'openness': 0.7,
                'sociability': 0.7
            }
        
        # Start agent process
        success = agent_manager.start_agent_process(
            agent_id=agent_id,
            mode='minecraft',
            additional_args=[
                '--gender', gender,
                '--personality', json.dumps(personality),
                '--spawn-x', str(spawn_pos.get('x', 0)),
                '--spawn-y', str(spawn_pos.get('y', 64)),
                '--spawn-z', str(spawn_pos.get('z', 0))
            ],
            agent_type='npc',  # Regular NPC
            custom_name=agent_name  # Use provided name
        )
        
        if success:
            return {
                "status": "success",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "gender": gender,
                "spawner": spawner_name,
                "world": world_name,
                "position": spawn_pos,
                "personality": personality,
                "message": f"NPC {agent_name} spawned successfully",
                "note": "Agent will be auto-packaged after brain creation"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to spawn NPC {agent_name}"
            )
    
    except Exception as e:
        log.error(f"Single agent spawn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Global manager instance
agent_manager = AgentProcessManager()

# Integrate with auto-connect system
integrate_with_backend(app, agent_manager)


# =============================================================================
# SERVER CONFIGURATION ENDPOINTS
# =============================================================================

@app.post("/api/server/configure")
async def configure_server_folder():
    """
    Server folder is configured at startup.
    This endpoint only reports status.
    """
    if not server_integration.server_folder:
        raise HTTPException(
            status_code=500,
            detail="Server folder not initialized"
        )

    registered = server_integration.list_registered_agents()

    return {
        "status": "success",
        "message": "Server folder already configured",
        "server_folder": str(server_integration.server_folder),
        "usercache_path": str(server_integration.usercache_path),
        "usernamecache_path": str(server_integration.usernamecache_path),
        "existing_agents": registered,
        "agent_count": len(registered)
    }

@app.get("/api/server/status")
async def get_server_status():
    """Get server integration status"""
    try:
        if not server_integration.server_folder:
            return {
                "status": "not_configured",
                "message": "Server folder not configured. Use POST /api/server/configure"
            }
        
        registered = server_integration.list_registered_agents()
        
        return {
            "status": "configured",
            "server_folder": str(server_integration.server_folder),
            "usercache_path": str(server_integration.usercache_path),
            "usernamecache_path": str(server_integration.usernamecache_path),
            "registered_agents": registered,
            "agent_count": len(registered),
            "files_exist": {
                "usercache.json": server_integration.usercache_path.exists() if server_integration.usercache_path else False,
                "usernamecache.json": server_integration.usernamecache_path.exists() if server_integration.usernamecache_path else False
            }
        }
    
    except Exception as e:
        log.error(f"Server status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/server/agents")
async def list_server_agents():
    """List all agents registered in server files"""
    try:
        registered = server_integration.list_registered_agents()
        
        return {
            "status": "success",
            "agents": registered,
            "count": len(registered),
            "npcs": [a for a in registered if a['type'] == 'npc'],
            "gods": [a for a in registered if a['type'] == 'god']
        }
    
    except Exception as e:
        log.error(f"List server agents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENDPOINTS - MATCHING JAVA MOD
# =============================================================================

# ===== PLAYER EVENT ENDPOINT (DWEventHandler.java) =====
@app.post("/api/player_event")
async def handle_player_event(request: Request):
    """
    Handle player connection/disconnection events from Minecraft.
    Called by: DWEventHandler.java (notifyBackendPlayerConnected/Disconnected)
    
    Body format from Java:
        {
            "agent_id": "AI_alice",
            "player_uuid": "uuid-string",
            "agent_type": "npc" or "god_<type>",
            "event": "connected" or "disconnected"
        }
    """
    try:
        data = await request.json()
        
        agent_id = data.get('agent_id')
        player_uuid = data.get('player_uuid')
        agent_type = data.get('agent_type')
        event = data.get('event')
        
        log.info(f"[Player Event] {event}: {agent_id} (type: {agent_type}, UUID: {player_uuid})")
        
        if event == 'connected':
            # Agent connected to Minecraft server
            if agent_id not in agent_manager.agent_processes:
                # Auto-start agent if not running
                log.info(f"Auto-starting agent {agent_id} for Minecraft connection")
                
                mode = 'minecraft'
                args = []
                
                # Check if it's a god
                if agent_type and agent_type.startswith('god_'):
                    god_type = agent_type.replace('god_', '')
                    args.extend(['--gender', 'dual'])  # Gods are dual-gendered
                
                agent_manager.start_agent_process(
                    agent_id=agent_id,
                    mode=mode,
                    additional_args=args,
                    agent_type='npc'  # Player connections are NPCs
                )
            
            return {
                "status": "success",
                "message": f"Agent {agent_id} connected",
                "agent_id": agent_id,
                "player_uuid": player_uuid,
                "agent_type": agent_type
            }
        
        elif event == 'disconnected':
            # Agent disconnected from Minecraft
            log.info(f"Agent {agent_id} disconnected from Minecraft")
            
            # Optional: Stop agent process after disconnect
            # For now, keep running - agent may reconnect
            
            return {
                "status": "success",
                "message": f"Agent {agent_id} disconnected",
                "agent_id": agent_id,
                "player_uuid": player_uuid
            }
        
        else:
            log.warning(f"Unknown player event type: {event}")
            return {
                "status": "unknown_event",
                "event": event
            }
    
    except Exception as e:
        log.error(f"Player event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== BREEDING EVENT ENDPOINT (BreedingEventHandler.java) =====
@app.post("/api/breeding/event")
async def handle_breeding_event(request: Request):
    """
    Handle AI agent breeding events.
    Called by: BreedingEventHandler.java (via PythonBackendClient.notifyBreeding)
    
    Body format from Java:
        {
            "event": "breeding",
            "parent_a_id": "agent1",
            "parent_b_id": "agent2",
            "parent_a_type": "npc" or "god",
            "parent_b_type": "npc" or "god",
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        parent_a_id = data.get('parent_a_id')
        parent_b_id = data.get('parent_b_id')
        parent_a_type = data.get('parent_a_type')
        parent_b_type = data.get('parent_b_type')
        
        log.info(f"[Breeding] {parent_a_id} ({parent_a_type}) x {parent_b_id} ({parent_b_type})")
        
        # Create offspring agent
        offspring_id = f"offspring_{parent_a_id}_{parent_b_id}_{int(time.time())}"
        
        # Determine offspring gender (random)
        import random
        offspring_gender = random.choice(['male', 'female'])
        
        # Inherit traits from parents
        # Load parent personalities if available
        parent_a_personality = {}
        parent_b_personality = {}
        
        try:
            parent_a_brain = Config.get_agent_brain_path(parent_a_id)
            if parent_a_brain.exists():
                from ai_core.brain_capsule import BrainCapsule
                capsule_a = BrainCapsule.load(str(parent_a_brain))
                parent_a_personality = capsule_a.personality or {}
        except Exception as e:
            log.warning(f"Could not load parent A personality: {e}")
        
        try:
            parent_b_brain = Config.get_agent_brain_path(parent_b_id)
            if parent_b_brain.exists():
                from ai_core.brain_capsule import BrainCapsule
                capsule_b = BrainCapsule.load(str(parent_b_brain))
                parent_b_personality = capsule_b.personality or {}
        except Exception as e:
            log.warning(f"Could not load parent B personality: {e}")
        
        # Genetic inheritance: blend parent traits
        offspring_personality = {}
        
        # Get traits from both parents
        all_traits = set(parent_a_personality.keys()) | set(parent_b_personality.keys())
        
        for trait in all_traits:
            val_a = parent_a_personality.get(trait, 0.5)
            val_b = parent_b_personality.get(trait, 0.5)
            
            # Blend with slight mutation
            mutation = random.uniform(-0.1, 0.1)
            blended = ((val_a + val_b) / 2.0) + mutation
            
            # Clamp to valid range
            offspring_personality[trait] = max(-1.0, min(1.0, blended))
        
        log.info(f"Creating offspring: {offspring_id} ({offspring_gender})")
        log.info(f"  Parent A: {parent_a_id} ({parent_a_type})")
        log.info(f"  Parent B: {parent_b_id} ({parent_b_type})")
        log.info(f"  Inherited personality: {offspring_personality}")
        
        # Spawn offspring agent with "Unnamed" as display name
        success = agent_manager.start_agent_process(
            agent_id=offspring_id,
            mode='minecraft',
            additional_args=[
                '--parent-a', parent_a_id,
                '--parent-b', parent_b_id,
                '--gender', offspring_gender,
                '--personality', json.dumps(offspring_personality)
            ],
            agent_type='npc',  # Offspring are NPCs
            custom_name="Unnamed"  # Offspring start unnamed
        )
        
        if success:
            return {
                "status": "success",
                "message": "Breeding successful - offspring created",
                "offspring_id": offspring_id,
                "offspring_gender": offspring_gender,
                "parent_a": parent_a_id,
                "parent_b": parent_b_id,
                "parent_types": {
                    "a": parent_a_type,
                    "b": parent_b_type
                },
                "inherited_personality": offspring_personality,
                "genetic_info": {
                    "inheritance": "50% parent A + 50% parent B + random mutation",
                    "mutation_range": "±0.1",
                    "traits_inherited": len(offspring_personality)
                }
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to spawn offspring"
            )
    
    except Exception as e:
        log.error(f"Breeding event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== GENESIS SPAWN ENDPOINT (DivineCommands.java) =====
@app.post("/api/genesis/spawn")
async def genesis_spawn(request: Request):
    """
    Spawn initial Genesis agents (Adam & Eve).
    Called by: PythonBackendClient.spawnGenesisAgents
    
    Body format from Java:
        {
            "event": "genesis",
            "spawner": "PlayerName",
            "world": "minecraft:overworld",
            "spawn_count": 2,
            "spawn_positions": [
                {"x": 100, "y": 64, "z": 200, "gender": "male"},
                {"x": 102, "y": 64, "z": 200, "gender": "female"}
            ],
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        spawner_name = data.get('spawner')
        world_name = data.get('world')
        spawn_positions = data.get('spawn_positions', [])
        
        log.info(f"🌟 GENESIS: Spawning {len(spawn_positions)} agents by {spawner_name}")
        
        agents_spawned = []
        
        for i, spawn_data in enumerate(spawn_positions):
            gender = spawn_data.get('gender', 'random')
            pos = f"({spawn_data.get('x')}, {spawn_data.get('y')}, {spawn_data.get('z')})"
            
            # Generate unique agent ID
            timestamp = int(time.time() * 1000)
            
            # Generate agent ID based on gender
            if gender == 'male':
                agent_id = f"adam_{timestamp}_{i}"
                display_name = "Adam"  # Clean name without timestamp
                # Male personality: higher boldness, curiosity
                personality = {
                    'boldness': 0.8,
                    'curiosity': 0.9,
                    'agreeableness': 0.5,
                    'conscientiousness': 0.6,
                    'neuroticism': 0.3,
                    'openness': 0.7,
                    'sociability': 0.6
                }
            elif gender == 'female':
                agent_id = f"eve_{timestamp}_{i}"
                display_name = "Eve"  # Clean name without timestamp
                # Female personality: higher agreeableness, conscientiousness
                personality = {
                    'boldness': 0.6,
                    'curiosity': 0.7,
                    'agreeableness': 0.9,
                    'conscientiousness': 0.8,
                    'neuroticism': 0.4,
                    'openness': 0.7,
                    'sociability': 0.8
                }
            else:
                # Random gender
                import random
                gender = random.choice(['male', 'female'])
                agent_id = f"genesis_{gender}_{timestamp}_{i}"
                display_name = "Unnamed"  # Default name
                # Balanced personality
                personality = {
                    'boldness': 0.7,
                    'curiosity': 0.8,
                    'agreeableness': 0.7,
                    'conscientiousness': 0.7,
                    'neuroticism': 0.3,
                    'openness': 0.7,
                    'sociability': 0.7
                }
            
            # Start agent process with custom name
            success = agent_manager.start_agent_process(
                agent_id=agent_id,
                mode='minecraft',
                additional_args=[
                    '--gender', gender,
                    '--personality', json.dumps(personality),
                    '--spawn-x', str(spawn_data.get('x')),
                    '--spawn-y', str(spawn_data.get('y')),
                    '--spawn-z', str(spawn_data.get('z')),
                    '--genesis-ancestor', 'true'  # Mark as genesis ancestor
                ],
                agent_type='npc',  # Genesis agents are NPCs
                custom_name=display_name  # Use clean name
            )
            
            if success:
                agents_spawned.append({
                    'agent_id': agent_id,
                    'display_name': display_name,
                    'gender': gender,
                    'position': pos,
                    'role': 'Genesis ancestor',
                    'personality': personality,
                    'description': f"First {gender} - ancestor of all agents"
                })
                
                log.info(f"✅ Genesis agent spawned: {display_name} (ID: {agent_id}, {gender}) at {pos}")
                log.info(f"   Personality: {personality}")
        
        return {
            "status": "success",
            "message": f"Genesis complete - {len(agents_spawned)} agents spawned",
            "spawner": spawner_name,
            "world": world_name,
            "agents": agents_spawned,
            "count": len(agents_spawned),
            "genetic_info": {
                "adam_traits": "Higher boldness (0.8) and curiosity (0.9)",
                "eve_traits": "Higher agreeableness (0.9) and conscientiousness (0.8)",
                "offspring_will_inherit": "Blend of parent traits with mutation"
            }
        }
    
    except Exception as e:
        log.error(f"Genesis spawn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== DIVINE RESET ENDPOINT (DivineCommands.java) =====
@app.post("/api/divine_reset")
async def divine_reset(request: Request):
    """
    Divine Reset: Kill all AI agents and clear memories.
    Called by: PythonBackendClient.notifyDivineReset
    
    Body format from Java:
        {
            "event": "divine_reset",
            "world": "minecraft:overworld",
            "agent_count": 5,
            "agent_ids": ["agent1", "agent2", ...],
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        world_name = data.get('world')
        agent_ids = data.get('agent_ids', [])
        
        log.warning(f"⚠️  DIVINE RESET: Purging {len(agent_ids)} agents from {world_name}")
        
        # Stop and delete all specified agents
        agents_killed = []
        brains_deleted = 0
        
        for agent_id in agent_ids:
            # Stop process
            if agent_id in agent_manager.agent_processes:
                agent_manager.stop_agent_process(agent_id)
                agents_killed.append(agent_id)
            
            # Delete brain
            brain_path = Config.get_agent_brain_path(agent_id)
            if brain_path.exists():
                brain_path.unlink()
                brains_deleted += 1
                log.info(f"🗑️  Deleted brain: {agent_id}")
        
        log.info(f"✅ Divine reset complete: {len(agents_killed)} agents killed, {brains_deleted} brains deleted")
        
        return {
            "status": "success",
            "message": "Divine reset complete",
            "world": world_name,
            "agents_killed": len(agents_killed),
            "brains_deleted": brains_deleted,
            "killed_agents": agents_killed
        }
    
    except Exception as e:
        log.error(f"Divine reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== CLEAR MEMORIES ENDPOINT (DivineCommands.java) =====
@app.post("/api/agents/clear_memories")
async def clear_memories(request: Request):
    """
    Clear agent memories selectively.
    Called by: PythonBackendClient.clearAgentMemories
    
    Body format from Java:
        {
            "event": "clear_memories",
            "agent_ids": ["agent1", "agent2"],
            "exceptions": ["agent3"],
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        agent_ids = data.get('agent_ids', [])
        exceptions = data.get('exceptions', [])
        
        log.info(f"🧹 Clearing memories for {len(agent_ids)} agents (exceptions: {exceptions})")
        
        results = {}
        
        for agent_id in agent_ids:
            if agent_id in exceptions:
                results[agent_id] = {
                    "status": "skipped",
                    "reason": "In exception list"
                }
                continue
            
            try:
                brain_path = Config.get_agent_brain_path(agent_id)
                
                if brain_path.exists():
                    from ai_core.brain_capsule import BrainCapsule
                    capsule = BrainCapsule.load(str(brain_path))
                    
                    # Clear memories
                    capsule.memory_snapshot = []
                    capsule.language_state = None
                    
                    # Save
                    capsule.save(str(brain_path))
                    
                    results[agent_id] = {
                        "status": "success",
                        "cleared": ["episodic", "language"]
                    }
                    
                    log.info(f"✅ Cleared memories: {agent_id}")
                else:
                    results[agent_id] = {
                        "status": "not_found",
                        "message": "Brain file not found"
                    }
            
            except Exception as e:
                results[agent_id] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "status": "success",
            "results": results,
            "total_cleared": sum(1 for r in results.values() if r.get('status') == 'success')
        }
    
    except Exception as e:
        log.error(f"Clear memories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== GOD SPAWN ENDPOINT (DivineCommands.java) =====
@app.post("/api/gods/spawn")
async def spawn_god(request: Request):
    """
    Spawn god-tier entity.
    Called by: PythonBackendClient.spawnGodAgent
    
    Body format from Java:
        {
            "event": "spawn_god",
            "god_type": "wither",
            "spawner": "PlayerName",
            "world": "minecraft:overworld",
            "spawn_position": {"x": 100, "y": 64, "z": 200},
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        god_type = data.get('god_type')
        spawner_name = data.get('spawner')
        world_name = data.get('world')
        spawn_pos = data.get('spawn_position', {})
        
        # God configurations
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
            'ender_dragon': {  # Alias for dragon
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
                'description': 'Wise entity that provides guidance - dual-gendered mystic'
            },
            'creaking': {
                'memory_mb': 2048,
                'persona_traits': {
                    'curiosity': 0.8,
                    'boldness': 0.4,
                    'neuroticism': 0.6,
                    'sociability': -0.2
                },
                'description': 'Mysterious pale garden entity - dual-gendered forest spirit'
            },
            'elder_guardian': {
                'memory_mb': 2560,
                'persona_traits': {
                    'boldness': 0.85,
                    'agreeableness': -0.6,
                    'conscientiousness': 0.7,
                    'sociability': -0.5
                },
                'description': 'Ancient ocean temple guardian - dual-gendered aquatic deity'
            }
        }
        
        if god_type not in GOD_CONFIGS:
            log.warning(f"Unknown god type: {god_type}, using default config")
            config = {
                'memory_mb': 2048,
                'persona_traits': {}
            }
        else:
            config = GOD_CONFIGS[god_type]
        
        # Generate god agent ID (unique identifier)
        timestamp = int(time.time() * 1000)
        agent_id = f"{god_type}_{timestamp}"
        
        # Display name is "Unnamed" for gods
        display_name = "Unnamed"
        
        log.info(f"👑 Spawning god: {god_type} (ID: {agent_id}, Name: {display_name}) - DUAL GENDERED")
        
        # Start god process
        success = agent_manager.start_agent_process(
            agent_id=agent_id,
            mode='minecraft',
            additional_args=[
                '--gender', 'dual',  # Gods are dual-gendered
                '--personality', json.dumps(config['persona_traits']),
                '--memory-mb', str(config['memory_mb']),
                '--spawn-x', str(spawn_pos.get('x', 0)),
                '--spawn-y', str(spawn_pos.get('y', 64)),
                '--spawn-z', str(spawn_pos.get('z', 0))
            ],
            agent_type=f'god_{god_type}',  # Pass god type for proper UUID generation
            custom_name=display_name  # Gods are "Unnamed"
        )
        
        if success:
            return {
                "status": "success",
                "god_type": god_type,
                "agent_id": agent_id,
                "display_name": display_name,
                "gender": "dual",  # Gods are dual-gendered (both male and female)
                "spawner": spawner_name,
                "world": world_name,
                "position": spawn_pos,
                "personality": config['persona_traits'],
                "memory_mb": config['memory_mb'],
                "divine_attributes": {
                    "gender_type": "dual (hermaphroditic - both male and female)",
                    "can_breed": False,  # Gods cannot breed with each other
                    "can_breed_with_npcs": True,  # Gods can breed with NPCs
                    "offspring_type": "demigod (50% god traits + 50% NPC traits)",
                    "divine_power": 100,
                    "genesis_immune": True
                },
                "god_description": config.get('description', f"{god_type} god entity"),
                "note": "God spawns with name 'Unnamed' - UUID is unique based on agent_id"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to spawn god {god_type}"
            )
    
    except Exception as e:
        log.error(f"God spawn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== GOD ABILITY ENDPOINT (DivineCommands.java) =====
@app.post("/api/gods/ability")
async def god_use_ability(request: Request):
    """
    Activate god ability.
    Called by: PythonBackendClient.godUseAbility
    
    Body format from Java:
        {
            "event": "god_ability",
            "agent_id": "GOD_wither_123",
            "ability": "summon_wither_skulls",
            "parameters": [],
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        agent_id = data.get('agent_id')
        ability = data.get('ability')
        parameters = data.get('parameters', [])
        
        log.info(f"⚡ God ability: {agent_id} using {ability}")
        
        # TODO: Send ability command to agent process via IPC
        # For now, just acknowledge
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "ability": ability,
            "parameters": parameters,
            "message": f"God ability {ability} activated"
        }
    
    except Exception as e:
        log.error(f"God ability error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== GOD TRANSFORM ENDPOINT (DivineCommands.java) =====
@app.post("/api/gods/transform")
async def god_transform(request: Request):
    """
    Transform god into different mob.
    Called by: PythonBackendClient.godTransform
    
    Body format from Java:
        {
            "event": "god_transform",
            "agent_id": "GOD_oracle_123",
            "target_mob": "villager",
            "timestamp": 1234567890
        }
    """
    try:
        data = await request.json()
        
        agent_id = data.get('agent_id')
        target_mob = data.get('target_mob')
        
        log.info(f"🔄 God transform: {agent_id} -> {target_mob}")
        
        # TODO: Send transform command to agent process
        # For now, just acknowledge
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "target_mob": target_mob,
            "message": f"God transformed into {target_mob}"
        }
    
    except Exception as e:
        log.error(f"God transform error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ADDITIONAL MANAGEMENT ENDPOINTS
# =============================================================================

@app.get("/api/agents/list")
async def list_agents():
    """List all agents (running + available brains)"""
    try:
        running = agent_manager.list_running_agents()
        
        # Find available brains
        brains_dir = Config.BRAINS_DIR
        available_brains = []
        
        if brains_dir.exists():
            for agent_dir in brains_dir.iterdir():
                if agent_dir.is_dir():
                    brain_file = agent_dir / "brain.pcap"
                    if brain_file.exists():
                        available_brains.append({
                            'agent_id': agent_dir.name,
                            'brain_path': str(brain_file),
                            'size_mb': brain_file.stat().st_size / 1024 / 1024
                        })
        
        return {
            "running": running,
            "running_count": len(running),
            "available_brains": available_brains,
            "running_details": {
                agent_id: agent_manager.get_agent_status(agent_id)
                for agent_id in running
            }
        }
    
    except Exception as e:
        log.error(f"List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/start")
async def start_agent(request: Request):
    """Start agent manually"""
    try:
        data = await request.json()
        
        agent_id = data.get('agent_id')
        mode = data.get('mode', 'autonomous')
        load_brain = data.get('load_brain')
        args = data.get('args', [])
        
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id")
        
        success = agent_manager.start_agent_process(
            agent_id=agent_id,
            mode=mode,
            load_brain=load_brain,
            additional_args=args,
            agent_type=data.get('agent_type', 'npc'),  # Allow specifying type
            custom_name=data.get('custom_name')  # Allow custom name
        )
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} started",
                "agent_id": agent_id,
                "mode": mode,
                "process_info": agent_manager.get_agent_status(agent_id)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start agent {agent_id}"
            )
    
    except Exception as e:
        log.error(f"Start agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop agent process"""
    try:
        success = agent_manager.stop_agent_process(agent_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} stopped",
                "agent_id": agent_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} not running"
            )
    
    except Exception as e:
        log.error(f"Stop agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Get agent process status"""
    try:
        status = agent_manager.get_agent_status(agent_id)
        
        if status:
            return status
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} not found"
            )
    
    except Exception as e:
        log.error(f"Status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/package")
async def package_agent(agent_id: str):
    """Package agent for distribution"""
    try:
        brain_path = Config.get_agent_brain_path(agent_id)
        
        if not brain_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Brain not found for agent {agent_id}"
            )
        
        # Use auto-packager
        package_path = agent_manager.spawner.package_agent(
            agent_id=agent_id,
            brain_path=str(brain_path)
        )
        
        if package_path:
            return {
                "status": "success",
                "agent_id": agent_id,
                "package_path": str(package_path),
                "message": "Agent packaged successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Packaging failed"
            )
    
    except Exception as e:
        log.error(f"Package error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/cleanup")
async def cleanup_agent(agent_id: str, delete_brain: bool = False):
    """Cleanup agent resources"""
    try:
        # Stop if running
        if agent_id in agent_manager.agent_processes:
            agent_manager.stop_agent_process(agent_id)
        
        # Delete brain if requested
        if delete_brain:
            brain_path = Config.get_agent_brain_path(agent_id)
            if brain_path.exists():
                brain_path.unlink()
                log.info(f"Deleted brain: {brain_path}")
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "brain_deleted": delete_brain
        }
    
    except Exception as e:
        log.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HEALTH & MONITORING
# =============================================================================

@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "service": "Divine World Management Server",
        "version": "3.0.0",
        "agents_running": len(agent_manager.list_running_agents()),
        "uptime": asyncio.get_event_loop().time() - startup_time
    }


@app.get("/health/detailed")
async def detailed_health():
    """Detailed system health"""
    running = agent_manager.list_running_agents()
    
    # System resources
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    return {
        "status": "healthy",
        "version": "3.0.0",
        "uptime": asyncio.get_event_loop().time() - startup_time,
        "agents": {
            "running": running,
            "count": len(running),
            "details": {
                agent_id: agent_manager.get_agent_status(agent_id)
                for agent_id in running
            }
        },
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available / 1024 / 1024
        },
        "config": {
            "data_dir": str(Config.DATA_DIR),
            "brains_dir": str(Config.BRAINS_DIR),
            "backend_port": Config.BASE_BACKEND_PORT
        }
    }


# =============================================================================
# ROOT ENDPOINT
# =============================================================================

@app.get("/")
async def root():
    """API documentation"""
    return {
        "service": "Divine World Management Server",
        "version": "3.0.0",
        "description": "Manages AI agents for Divine World Minecraft mod",
        "note": "Endpoints corrected to match Java mod API calls + Server integration",
        
        "server_integration": {
            "note": "Agents are automatically registered in Minecraft server files",
            "endpoints": {
                "POST /api/server/configure": {
                    "description": "Configure Minecraft server folder",
                    "body": {"server_folder": "/path/to/minecraft/server"}
                },
                "GET /api/server/status": "Get server integration status",
                "GET /api/server/agents": "List agents in server files"
            },
            "features": [
                "Auto-registration in usercache.json",
                "Auto-registration in usernamecache.json",
                "Offline UUID generation (OfflinePlayer:<username>)",
                "Agent naming: AI_<n> for NPCs, GOD_<type>_<n> for gods",
                "Automatic cleanup on agent removal"
            ],
            "uuid_generation": {
                "format": "UUID v3 (MD5 of 'OfflinePlayer:AI_<type>_<agent_id>')",
                "note": "UUID is unique per agent, NOT per name",
                "example_npc": "OfflinePlayer:AI_NPC_alice → unique UUID",
                "example_god": "OfflinePlayer:AI_GOD_wither_123 → unique UUID",
                "name_independent": "Multiple agents can have same display name but different UUIDs"
            },
            "naming_system": {
                "display_names": {
                    "genesis_adam": "Adam",
                    "genesis_eve": "Eve",
                    "offspring": "Unnamed",
                    "gods": "Unnamed",
                    "custom": "Can be set via custom_name parameter"
                },
                "agent_ids": {
                    "genesis": "adam_<timestamp>_0, eve_<timestamp>_1",
                    "offspring": "offspring_<parent1>_<parent2>_<timestamp>",
                    "gods": "<god_type>_<timestamp>",
                    "custom": "User-defined"
                },
                "note": "Display name can be anything (or 'Unnamed'), UUID is generated from agent_id + type"
            }
        },
        
        "minecraft_integration": {
            "note": "These endpoints are called by the Java mod",
            "endpoints": {
                "POST /api/player_event": {
                    "description": "Player connection/disconnection events",
                    "called_by": "DWEventHandler.java",
                    "body": {
                        "agent_id": "AI_alice",
                        "player_uuid": "uuid-string",
                        "agent_type": "npc or god_<type>",
                        "event": "connected or disconnected"
                    }
                },
                "POST /api/breeding/event": {
                    "description": "AI agent breeding events",
                    "called_by": "BreedingEventHandler.java",
                    "body": {
                        "event": "breeding",
                        "parent_a_id": "agent1",
                        "parent_b_id": "agent2",
                        "parent_a_type": "npc or god",
                        "parent_b_type": "npc or god"
                    }
                },
                "POST /api/genesis/spawn": {
                    "description": "Spawn initial Genesis agents",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "genesis",
                        "spawner": "PlayerName",
                        "world": "minecraft:overworld",
                        "spawn_count": 2,
                        "spawn_positions": [
                            {"x": 100, "y": 64, "z": 200, "gender": "male"},
                            {"x": 102, "y": 64, "z": 200, "gender": "female"}
                        ]
                    }
                },
                "POST /api/divine_reset": {
                    "description": "Kill all agents and clear memories",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "divine_reset",
                        "world": "minecraft:overworld",
                        "agent_count": 5,
                        "agent_ids": ["agent1", "agent2", "..."]
                    }
                },
                "POST /api/agents/clear_memories": {
                    "description": "Clear agent memories selectively",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "clear_memories",
                        "agent_ids": ["agent1", "agent2"],
                        "exceptions": ["agent3"]
                    }
                },
                "POST /api/gods/spawn": {
                    "description": "Spawn god-tier entity",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "spawn_god",
                        "god_type": "wither|warden|dragon|oracle|creaking|elder_guardian",
                        "spawner": "PlayerName",
                        "world": "minecraft:overworld",
                        "spawn_position": {"x": 100, "y": 64, "z": 200}
                    }
                },
                "POST /api/gods/ability": {
                    "description": "Activate god ability",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "god_ability",
                        "agent_id": "GOD_wither_123",
                        "ability": "summon_wither_skulls",
                        "parameters": []
                    }
                },
                "POST /api/gods/transform": {
                    "description": "Transform god into different mob",
                    "called_by": "DivineCommands.java -> PythonBackendClient",
                    "body": {
                        "event": "god_transform",
                        "agent_id": "GOD_oracle_123",
                        "target_mob": "villager"
                    }
                }
            }
        },
        
        "management_endpoints": {
            "POST /api/agents/start": "Start agent process manually",
            "POST /api/agents/{id}/stop": "Stop agent process",
            "GET /api/agents/{id}/status": "Get agent status",
            "GET /api/agents/list": "List all agents",
            "POST /api/agents/{id}/package": "Package agent for distribution",
            "POST /api/agents/{id}/cleanup": "Cleanup agent resources"
        },
        
        "health_endpoints": {
            "GET /health": "Basic health check",
            "GET /health/detailed": "Detailed system health"
        },
        
        "god_types": [
            "wither",
            "warden",
            "dragon",
            "ender_dragon",
            "oracle",
            "creaking",
            "elder_guardian"
        ],
        
        "mob_types": [
            "player",
            "villager",
            "pig",
            "cow",
            "zombie",
            "skeleton",
            "wither",
            "dragon"
        ],
        
        "running_agents": agent_manager.list_running_agents(),
        
        "java_mod_info": {
            "mod_id": "divineworld",
            "minecraft_version": "1.20.1",
            "java_files_analyzed": [
                "DWEventHandler.java",
                "BreedingEventHandler.java",
                "PythonBackendClient.java",
                "DivineCommands.java",
                "GodCommand.java"
            ],
            "features": [
                "Genesis spawning (2 initial NPCs)",
                "God entity spawning (7 types)",
                "Divine reset (nuclear option)",
                "NPC breeding system",
                "God abilities",
                "God transformation",
                "Auto-packaging support",
                "Player event tracking"
            ]
        },
        
        "agent_naming_convention": {
            "genesis_agents": "Adam_<timestamp> or Eve_<timestamp>",
            "god_agents": "GOD_<type>_<timestamp>",
            "offspring_agents": "offspring_<parent1>_<parent2>_<timestamp>",
            "regular_agents": "AI_<name> or custom naming"
        }
    }


# =============================================================================
# STARTUP/SHUTDOWN
# =============================================================================

startup_time = 0


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Divine World Management Server - Corrected Endpoints"
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=Config.BASE_BACKEND_PORT,
        help=f'Server port (default: {Config.BASE_BACKEND_PORT})'
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Server host (default: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload (development)'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("  🎮 Divine World Management Server")
    print("=" * 70)
    print(f"  Starting on {args.host}:{args.port}")
    print("  Endpoints corrected for Divine World Minecraft mod")
    print("=" * 70)
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )
#try to make a gui for this 

#add inputing forge server's run.sh absolute path

#add editing agent's personality through gui

#add starting/stopping/killing agent processes through gui

#add every other api endpoint to gui

#add creating new agents through gui

#cache files of the server's username files and usercache when an agent is produced