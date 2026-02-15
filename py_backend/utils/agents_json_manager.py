"""
Agents JSON Manager
Manages agents.json file for Divine World agent registry.
Syncs with AgentConfigLoader.java on the Java side.

Format:
{
    "NPCs": {
        "male": ["Adam", "Bob", "Charlie"],
        "female": ["Eve", "Alice", "Diana"]
    },
    "GODs": {
        "dual": ["Zeus", "Odin", "Ra"]
    }
}
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Literal

log = logging.getLogger("agents_json_manager")


class AgentsJsonManager:
    """Manages agents.json file for Divine World"""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize manager with optional custom config path.
        If not provided, searches Documents/Desktop (same as AgentConfigLoader.java).
        """
        self.config_path = config_path
        if not self.config_path:
            self.config_path = self._find_or_create_config()

    @staticmethod
    def _find_or_create_config() -> Path:
        """Find agents.json in Documents/Desktop, or create in Documents"""
        home = Path.home()
        
        # Paths to search
        documents = home / "Documents" / "agents.json"
        desktop = home / "Desktop" / "agents.json"
        
        # If found, use it
        if documents.exists():
            log.info(f"Found agents.json at: {documents}")
            return documents
        if desktop.exists():
            log.info(f"Found agents.json at: {desktop}")
            return desktop
        
        # Create in Documents if not found
        documents.parent.mkdir(parents=True, exist_ok=True)
        log.info(f"Creating agents.json at: {documents}")
        
        # Initialize with default structure
        default_config = {
            "NPCs": {
                "male": [],
                "female": []
            },
            "GODs": {
                "dual": []
            }
        }
        
        with open(documents, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2)
        
        return documents

    def load_config(self) -> Dict:
        """Load agents.json configuration"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    log.debug(f"Loaded config from: {self.config_path}")
                    return config
        except Exception as e:
            log.warning(f"Failed to load config: {e}")
        
        # Return default if not found
        return {
            "NPCs": {"male": [], "female": []},
            "GODs": {"dual": []}
        }

    def save_config(self, config: Dict) -> bool:
        """Save agents.json configuration"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            log.info(f"Saved config to: {self.config_path}")
            return True
        except Exception as e:
            log.error(f"Failed to save config: {e}")
            return False

    def register_npc(self, name: str, gender: Literal['male', 'female']) -> bool:
        """Register an NPC in agents.json"""
        try:
            config = self.load_config()
            
            if gender not in ['male', 'female']:
                log.error(f"Invalid gender: {gender}")
                return False
            
            # Avoid duplicates
            if name in config["NPCs"][gender]:
                log.warning(f"NPC '{name}' already registered as {gender}")
                return True
            
            config["NPCs"][gender].append(name)
            success = self.save_config(config)
            
            if success:
                log.info(f"✅ Registered NPC: {name} ({gender})")
            
            return success
            
        except Exception as e:
            log.error(f"Failed to register NPC {name}: {e}")
            return False

    def register_god(self, name: str, god_type: str = 'dual') -> bool:
        """Register a God in agents.json"""
        try:
            config = self.load_config()
            
            if god_type not in config["GODs"]:
                config["GODs"][god_type] = []
            
            # Avoid duplicates
            if name in config["GODs"][god_type]:
                log.warning(f"God '{name}' already registered as {god_type}")
                return True
            
            config["GODs"][god_type].append(name)
            success = self.save_config(config)
            
            if success:
                log.info(f"✅ Registered GOD: {name} ({god_type})")
            
            return success
            
        except Exception as e:
            log.error(f"Failed to register God {name}: {e}")
            return False

    def unregister_npc(self, name: str, gender: Literal['male', 'female']) -> bool:
        """Unregister an NPC from agents.json"""
        try:
            config = self.load_config()
            
            if name in config["NPCs"][gender]:
                config["NPCs"][gender].remove(name)
                success = self.save_config(config)
                
                if success:
                    log.info(f"✅ Unregistered NPC: {name} ({gender})")
                
                return success
            
            log.warning(f"NPC '{name}' not found in {gender} list")
            return True
            
        except Exception as e:
            log.error(f"Failed to unregister NPC {name}: {e}")
            return False

    def unregister_god(self, name: str, god_type: str = 'dual') -> bool:
        """Unregister a God from agents.json"""
        try:
            config = self.load_config()
            
            if god_type in config["GODs"] and name in config["GODs"][god_type]:
                config["GODs"][god_type].remove(name)
                success = self.save_config(config)
                
                if success:
                    log.info(f"✅ Unregistered GOD: {name} ({god_type})")
                
                return success
            
            log.warning(f"God '{name}' not found in {god_type} list")
            return True
            
        except Exception as e:
            log.error(f"Failed to unregister God {name}: {e}")
            return False

    def get_all_male_npcs(self) -> List[str]:
        """Get all registered male NPCs"""
        config = self.load_config()
        return config["NPCs"]["male"].copy()

    def get_all_female_npcs(self) -> List[str]:
        """Get all registered female NPCs"""
        config = self.load_config()
        return config["NPCs"]["female"].copy()

    def get_all_gods(self, god_type: str = 'dual') -> List[str]:
        """Get all registered gods"""
        config = self.load_config()
        return config["GODs"].get(god_type, []).copy()

    def get_stats(self) -> Dict:
        """Get agent registry statistics"""
        config = self.load_config()
        return {
            'male_npcs': len(config["NPCs"]["male"]),
            'female_npcs': len(config["NPCs"]["female"]),
            'gods': len(config["GODs"].get("dual", [])),
            'total_agents': (
                len(config["NPCs"]["male"]) + 
                len(config["NPCs"]["female"]) + 
                len(config["GODs"].get("dual", []))
            )
        }


# Global instance
_manager: Optional[AgentsJsonManager] = None


def get_manager() -> AgentsJsonManager:
    """Get or create global manager instance"""
    global _manager
    if _manager is None:
        _manager = AgentsJsonManager()
    return _manager
