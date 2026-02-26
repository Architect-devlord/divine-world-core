# -----------------------------------------------------------------------------
# auto_connect_system.py - AUTO-JOIN SERVER ON STARTUP
# Integrated with minecraft_launcher.py and main.py
# -----------------------------------------------------------------------------

import asyncio
import json
import logging
import time
from pathlib import Path
from py_backend.config import Config
from typing import Dict, List, Optional, Set

log = logging.getLogger("auto_connect")


class AutoConnectSystem:
    """
    Auto-connects agents in specific folder to server on startup.
    Waits for all agents to connect before starting any.
    Integrated with EnhancedAgentSpawner.
    """
    
    def __init__(self, agents_folder: str, server_addr: str = "127.0.0.1:25565"):
        self.agents_folder = Path(agents_folder)
        self.server_addr = server_addr
        self.required_agents: List[Dict] = []
        self.connected_agents: Set[str] = set()
        self.connection_callbacks: Dict[str, asyncio.Event] = {}
        
        log.info(f"AutoConnect System initialized")
        log.info(f"  Agents Folder: {self.agents_folder}")
        log.info(f"  Server: {self.server_addr}")
    
    def scan_agents_folder(self) -> List[Dict]:
        """
        Scan folder for agent applications with auto-connect enabled
        Returns list of agent configs
        """
        self.required_agents = []
        
        if not self.agents_folder.exists():
            log.warning(f"Agents folder does not exist: {self.agents_folder}")
            return []
        
        # Scan for packaged agent directories
        for agent_dir in self.agents_folder.glob("DW_Agent_*"):
            config_path = agent_dir / "config.json"
            
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                    
                    # Check if auto-connect is enabled
                    if config.get('auto_connect', False):
                        agent_info = {
                            'agent_id': config['agent_id'],
                            'agent_type': config.get('agent_type', 'npc'),
                            'god_type': config.get('god_type'),
                            'path': str(agent_dir),
                            'config': config
                        }
                        
                        self.required_agents.append(agent_info)
                        self.connection_callbacks[agent_info['agent_id']] = asyncio.Event()
                        
                        log.info(f"  Found auto-connect agent: {agent_info['agent_id']} "
                               f"(Type: {agent_info['agent_type']})")
                
                except Exception as e:
                    log.error(f"Failed to load config from {config_path}: {e}")
        
        log.info(f"✅ Found {len(self.required_agents)} agents with auto-connect enabled")
        return self.required_agents
    
    async def launch_all_agents(self, spawner) -> bool:
        """
        Launch all agents with auto-connect enabled
        Uses EnhancedAgentSpawner to launch packaged applications
        """
        if not self.required_agents:
            log.info("No agents to launch")
            return True
        
        log.info(f"🚀 Launching {len(self.required_agents)} agents...")
        
        # Launch all agents
        launch_tasks = []
        for agent_info in self.required_agents:
            task = self._launch_agent(spawner, agent_info)
            launch_tasks.append(task)
        
        # Wait for all to launch
        results = await asyncio.gather(*launch_tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if r is True)
        failed_count = len(results) - success_count
        
        if failed_count > 0:
            log.warning(f"⚠️ {failed_count}/{len(results)} agents failed to launch")
        
        log.info(f"✅ {success_count}/{len(results)} agents launched successfully")
        
        return failed_count == 0
    
    async def _launch_agent(self, spawner, agent_info: Dict) -> bool:
        """Launch a single agent"""
        agent_id = agent_info['agent_id']
        agent_type = agent_info['agent_type']

        try:
            log.info(f"Launching {agent_id}...")

            if agent_type == 'npc':
                # Launch normal NPC agent
                from ai_core.agent import NPCAgent
                agent = NPCAgent(
                    agent_id=agent_id,
                    autonomous=True,
                    mode='minecraft'
                )

            elif agent_type.startswith('god_'):
                # Launch god agent with god controls
                god_type = agent_info.get('god_type') or agent_type.replace('god_', '')
                agent = spawn_god_agent(
                    spawner,
                    god_type=god_type,
                    agent_id=agent_id
                )

            else:
                log.error(f"Unknown agent type: {agent_type}")
                return False

            if agent:
                log.info(f"✅ {agent_id} launched")
                return True
            else:
                log.error(f"❌ Failed to launch {agent_id}")
                return False

        except Exception as e:
            log.error(f"❌ Exception launching {agent_id}: {e}", exc_info=True)
            return False
    
    async def wait_for_all_connections(self, timeout: int = 60) -> bool:
        """
        Wait for all required agents to connect to the server.
        Shows warning if any fail to connect.
        
        Args:
            timeout: Maximum seconds to wait
        
        Returns:
            True if all connected, False if timeout or failures
        """
        if not self.required_agents:
            return True
        
        log.info(f"⏳ Waiting for {len(self.required_agents)} agents to connect...")
        log.info(f"   Timeout: {timeout} seconds")
        
        start_time = time.time()
        
        # Create timeout task
        timeout_task = asyncio.create_task(asyncio.sleep(timeout))
        
        # Create connection wait tasks
        wait_tasks = [
            self.connection_callbacks[agent['agent_id']].wait()
            for agent in self.required_agents
        ]
        
        # Wait for either all connections or timeout
        done, pending = await asyncio.wait(
            [*wait_tasks, timeout_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Check if we timed out
        if timeout_task in done:
            missing = [
                agent['agent_id'] 
                for agent in self.required_agents 
                if agent['agent_id'] not in self.connected_agents
            ]
            
            log.warning(f"⚠️ Connection timeout! Missing agents: {missing}")
            return False
        
        # All connected
        elapsed = time.time() - start_time
        log.info(f"✅ All {len(self.required_agents)} agents connected in {elapsed:.1f}s")
        
        return True
    
    def mark_connected(self, agent_id: str):
        """
        Mark agent as successfully connected.
        Called by backend when player_event is received.
        """
        if agent_id in [agent['agent_id'] for agent in self.required_agents]:
            self.connected_agents.add(agent_id)
            
            # Trigger the event
            if agent_id in self.connection_callbacks:
                self.connection_callbacks[agent_id].set()
            
            log.info(f"✅ {agent_id} connected ({len(self.connected_agents)}/{len(self.required_agents)})")
    
    def is_all_connected(self) -> bool:
        """Check if all required agents are connected"""
        return len(self.connected_agents) >= len(self.required_agents)
    
    def get_status(self) -> Dict:
        """Get connection status"""
        return {
            'total_agents': len(self.required_agents),
            'connected': len(self.connected_agents),
            'pending': len(self.required_agents) - len(self.connected_agents),
            'agents': [
                {
                    'agent_id': agent['agent_id'],
                    'connected': agent['agent_id'] in self.connected_agents
                }
                for agent in self.required_agents
            ]
        }


# ============================================================================
# INTEGRATION WITH MAIN.PY
# ============================================================================

def integrate_with_backend(app, agent_manager):
    """
    Add auto-connect endpoints to FastAPI backend
    """
    from fastapi import HTTPException
    
    # Create auto-connect system
    auto_connect = AutoConnectSystem(
        agents_folder=str(Config.NPC_APPLICATIONS_DIR),
        server_addr="127.0.0.1:25565"
    )
    
    # Store in app state
    app.state.auto_connect = auto_connect
    
    @app.post("/api/autoconnect/scan")
    async def scan_agents():
        """Scan for agents with auto-connect enabled"""
        agents = auto_connect.scan_agents_folder()
        return {
            "status": "success",
            "agents_found": len(agents),
            "agents": agents
        }
    
    @app.post("/api/autoconnect/launch")
    async def launch_agents():
        """Launch all agents with auto-connect"""
        success = await auto_connect.launch_all_agents(agent_manager.spawner)
        
        return {
            "status": "success" if success else "partial",
            "message": f"Launched {len(auto_connect.required_agents)} agents"
        }
    
    @app.post("/api/autoconnect/wait")
    async def wait_connections(timeout: int = 60):
        """Wait for all agents to connect"""
        success = await auto_connect.wait_for_all_connections(timeout)
        
        return {
            "status": "success" if success else "timeout",
            "all_connected": auto_connect.is_all_connected(),
            **auto_connect.get_status()
        }
    
    @app.get("/api/autoconnect/status")
    async def get_connection_status():
        """Get current connection status"""
        return {
            "status": "success",
            **auto_connect.get_status()
        }
    
    # Hook into player_event to mark connections
    original_player_event = app.routes[-1].endpoint  # Get the /api/player_event handler
    
    async def player_event_with_autoconnect(request):
        data = await request.json()
        
        agent_id = data.get("agent_id")
        event = data.get("event")
        
        # Mark as connected in auto-connect system
        if event == "connected" and agent_id:
            auto_connect.mark_connected(agent_id)
        
        # Call original handler
        return await original_player_event(request)
    
    # Note: You'll need to replace the route handler in your actual implementation
    #app.routes[-1].endpoint = player_event_with_autoconnect
    #return app
    log.info("✅ Auto-connect system integrated with backend")
def spawn_god_agent(spawner, god_type: str, agent_id: str, **kwargs):
    """
    Spawn a god agent with controls integrated.
    
    Usage in auto_connect system:
    """
    from ai_core.agent import NPCAgent
    
    # Create god agent with god_type parameter
    agent = NPCAgent(
        agent_id=agent_id,
        autonomous=True,
        mode='minecraft',
        god_type=god_type,  # This triggers god controls in __init__
        **kwargs
    )
    
    return agent