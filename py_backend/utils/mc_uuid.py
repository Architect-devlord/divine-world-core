import hashlib
import uuid
import os
import json
import random
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any

log = logging.getLogger("agent_name_manager")

def get_minecraft_uuid(username: str) -> str:
    """
    Generates a deterministic Minecraft offline-mode UUID (v3) for a username.
    Matches Java's UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(StandardCharsets.UTF_8))
    """
    name = f"OfflinePlayer:{username}"
    # Minecraft uses MD5 (UUID v3) but with a specific approach
    hash_bytes = hashlib.md5(name.encode('utf-8')).digest()

    # Convert to list of bytes to modify
    hash_list = list(hash_bytes)

    # Set version to 3 (MD5)
    hash_list[6] = (hash_list[6] & 0x0f) | 0x30
    # Set variant to IETF
    hash_list[8] = (hash_list[8] & 0x3f) | 0x80

    return str(uuid.UUID(bytes=bytes(hash_list)))

class AgentNameManager:
    """
    Manages agent names in a JSON file located in Documents or Desktop.
    Matches the naming format and search logic of the DivineWorld Java mod.
    """

    DEFAULT_CONTENT = {
      "NPCs": {
        "male": [
          "Adam", "Abel", "Cain", "Noah", "Abraham", "Isaac", "Jacob", "David", "Solomon", "Marcus",
          "Julius", "Augustus", "Nero", "Thor", "Loki", "Odin", "Baldur", "Heimdall", "Tyr", "Freyr"
        ],
        "female": [
          "Eve", "Sarah", "Rebecca", "Rachel", "Leah", "Ruth", "Esther", "Deborah", "Miriam", "Diana",
          "Minerva", "Juno", "Venus", "Freyja", "Frigg", "Sif", "Idunn", "Skadi", "Hel", "Nanna"
        ]
      },
      "GODs": {
        "dual": [
          "Zeus", "Hera", "Poseidon", "Athena", "Apollo", "Artemis", "Ares", "Aphrodite", "Hephaestus",
          "Hermes", "Dionysus", "Demeter", "Odin", "Thor", "Freya", "Loki", "Ra", "Anubis", "Osiris",
          "Isis", "Horus", "Thoth", "Amaterasu", "Susanoo", "Tsukuyomi", "Inari", "Shiva", "Vishnu",
          "Brahma", "Kali", "Ganesh", "Quetzalcoatl", "Tezcatlipoca", "Huitzilopochtli"
        ]
      }
    }

    def __init__(self):
        self.config_path = self._find_config_path()
        self._ensure_config_exists()
        log.info(f"AgentNameManager initialized with config at: {self.config_path}")

    def _find_config_path(self) -> Path:
        """Find agents.json in common locations (Documents, Desktop)"""
        home = Path.home()

        # Search paths matching Java mod logic
        search_paths = [
            home / "Documents" / "agents.json",
            home / "Desktop" / "agents.json",
            home / "OneDrive" / "Documents" / "agents.json",
            home / "OneDrive" / "Desktop" / "agents.json"
        ]

        for path in search_paths:
            if path.exists():
                return path

        # Default to Documents if none found
        return home / "Documents" / "agents.json"

    def _ensure_config_exists(self):
        """Create agents.json if it doesn't exist"""
        if not self.config_path.exists():
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.DEFAULT_CONTENT, f, indent=2)
                log.info(f"Created default agents.json at {self.config_path}")
            except Exception as e:
                log.error(f"Failed to create agents.json: {e}")

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            return self.DEFAULT_CONTENT

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load agents.json: {e}")
            return self.DEFAULT_CONTENT

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to JSON file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save agents.json: {e}")

    def add_name(self, category: str, subcategory: str, name: str):
        """Add a name to a specific category and subcategory"""
        if not name or name == "Unnamed":
            return

        config = self.load_config()

        if category not in config:
            config[category] = {}
        if subcategory not in config[category]:
            config[category][subcategory] = []

        if name not in config[category][subcategory]:
            config[category][subcategory].append(name)
            self.save_config(config)
            log.info(f"Added name '{name}' to {category}/{subcategory}")

    def get_random_name(self, category: str, subcategory: str) -> Optional[str]:
        """Get a random name from a specific category and subcategory"""
        config = self.load_config()
        names = config.get(category, {}).get(subcategory, [])

        if names:
            return random.choice(names)

        # Fallback to default content if not found in loaded config
        names = self.DEFAULT_CONTENT.get(category, {}).get(subcategory, [])
        if names:
            return random.choice(names)

        return None
