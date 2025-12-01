# -----------------------------------------------------------------------------
# auto_connect_system.py - AUTO-JOIN SERVER ON STARTUP
# -----------------------------------------------------------------------------

import asyncio
from asyncio import log
import json
from pathlib import Path
import time


class AutoConnectSystem:
    """
    Auto-connects agents in specific folder to server on startup.
    Waits for all agents to connect before starting any.
    """
    
    def __init__(self, agents_folder: str, server_addr: str):
        self.agents_folder = Path(agents_folder)
        self.server_addr = server_addr
        self.required_agents = []
        self.connected_agents = set()
    
    def scan_agents_folder(self):
        """Scan folder for agent applications"""
        self.required_agents = []
        
        for agent_dir in self.agents_folder.glob("DW_Agent_*"):
            config_path = agent_dir / "config.json"
            
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                
                # Check if auto-connect is enabled
                if config.get('auto_connect', False):
                    self.required_agents.append(config['agent_id'])
    
    async def wait_for_all_connections(self, timeout: int = 30):
        """
        Wait for all required agents to connect.
        Shows warning if any fail to connect.
        """
        start_time = time.time()
        
        while len(self.connected_agents) < len(self.required_agents):
            if time.time() - start_time > timeout:
                # Timeout - show warning
                missing = set(self.required_agents) - self.connected_agents
                log.warning(f"Some agents failed to connect: {missing}")
                return False
            
            await asyncio.sleep(0.5)
        
        log.info("All required agents connected")
        return True
    
    def mark_connected(self, agent_id: str):
        """Mark agent as successfully connected"""
        if agent_id in self.required_agents:
            self.connected_agents.add(agent_id)
