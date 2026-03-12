# py_backend/utils/mc_uuid.py
"""
Minecraft UUID utilities and agent name registry.
===================================================
Provides:

  get_minecraft_uuid(username)  — offline-mode UUID matching Java's
                                  UUID.nameUUIDFromBytes logic.

  AgentNameManager              — reads/writes agents.json in
                                  ~/Documents (or ~/Desktop as fallback).
                                  Used by AgentSpawner to resolve and
                                  persist agent display names.

agents.json format (matches AgentConfigLoader.java):
{
    "NPCs": {
        "male":   ["Adam", "Abel", ...],
        "female": ["Eve", "Sarah", ...]
    },
    "GODs": {
        "dual": ["Zeus", "Odin", ...]
    }
}

Name-assignment rules (enforced by AgentSpawner, not here):
  - Name given explicitly  → use it, register it in agents.json.
  - No name, type = npc    → pick random from NPCs[gender] pool.
  - No name, type = god    → pick random from GODs["dual"] pool.
  - No god_type given      → auto-select from SPAWNABLE_GOD_TYPES.
"""

import hashlib
import json
import logging
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger("mc_uuid")


# ---------------------------------------------------------------------------
# UUID helper
# ---------------------------------------------------------------------------

def get_minecraft_uuid(username: str) -> str:
    """
    Generate a deterministic Minecraft offline-mode UUID (version 3 / MD5).
    Matches Java:
        UUID.nameUUIDFromBytes(("OfflinePlayer:" + name)
                               .getBytes(StandardCharsets.UTF_8))
    """
    raw = hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest()
    b   = bytearray(raw)
    b[6] = (b[6] & 0x0F) | 0x30   # version = 3
    b[8] = (b[8] & 0x3F) | 0x80   # variant = IETF
    return str(uuid.UUID(bytes=bytes(b)))


# ---------------------------------------------------------------------------
# AgentNameManager
# ---------------------------------------------------------------------------

class AgentNameManager:
    """
    Manages the agents.json name registry.

    On first use, if agents.json is not found in ~/Documents or ~/Desktop,
    it is created there with the built-in DEFAULT_CONTENT name pool.

    Thread-safety note: each method does a fresh load + save cycle, so
    concurrent writes from multiple spawner threads are safe at the OS
    level (last-write wins on a single JSON file is acceptable for this
    use-case because spawn events are rare relative to I/O speed).
    """

    # God types available for auto-selection when none is specified.
    # Matches the five non-wither choices the user specified; wither can
    # still be spawned explicitly but is excluded from random selection.
    SPAWNABLE_GOD_TYPES: List[str] = [
        'wither','ender_dragon', 'oracle', 'elder_guardian', 'creaking', 'warden',
    ]

    DEFAULT_CONTENT: Dict[str, Any] = {
        "NPCs": {
            "male": [
                "Adam", "Abel", "Cain", "Noah", "Abraham", "Isaac", "Jacob",
                "David", "Solomon", "Marcus", "Julius", "Augustus", "Nero",
                "Thor", "Loki", "Odin", "Baldur", "Heimdall", "Tyr", "Freyr",
            ],
            "female": [
                "Eve", "Sarah", "Rebecca", "Rachel", "Leah", "Ruth", "Esther",
                "Deborah", "Miriam", "Diana", "Minerva", "Juno", "Venus",
                "Freyja", "Frigg", "Sif", "Idunn", "Skadi", "Hel", "Nanna",
            ],
        },
        "GODs": {
            "dual": {
                "wither":         ["Mortis", "Necros", "Vexis", "Umbra"],
                "ender_dragon":   ["Draconis", "Voidwing", "Abyss", "Sable"],
                "warden":         ["Tenebris", "Obsidius", "Cavern", "Gloom"],
                "oracle":         ["Zeus", "Odin", "Ra", "Athena", "Thoth",
                                   "Apollo", "Hermes", "Isis", "Brahma", "Inari"],
                "elder_guardian": ["Pelagius", "Thetis", "Nereus", "Triton"],
                "creaking":       ["Sylvanus", "Arbor", "Rootweald", "Grimwood"],
            },
        },
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config_path()
        self._ensure_config_exists()
        log.info(f"AgentNameManager: {self.config_path}")

    # ------------------------------------------------------------------
    # Path discovery (mirrors AgentConfigLoader.java search logic)
    # ------------------------------------------------------------------

    def _find_config_path(self) -> Path:
        home = Path.home()
        candidates = [
            home / "Documents"          / "agents.json",
            home / "Desktop"            / "agents.json",
            home / "OneDrive" / "Documents" / "agents.json",
            home / "OneDrive" / "Desktop"   / "agents.json",
        ]
        for p in candidates:
            if p.exists():
                log.info(f"Found agents.json: {p}")
                return p
        # Default write location
        return home / "Documents" / "agents.json"

    def _ensure_config_exists(self):
        if not self.config_path.exists():
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self.DEFAULT_CONTENT, f, indent=2)
                log.info(f"Created default agents.json: {self.config_path}")
            except Exception as e:
                log.error(f"Failed to create agents.json: {e}")

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {k: {sk: list(v) for sk, v in sv.items()}
                    for k, sv in self.DEFAULT_CONTENT.items()}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load agents.json: {e}")
            return {k: {sk: list(v) for sk, v in sv.items()}
                    for k, sv in self.DEFAULT_CONTENT.items()}

    def save_config(self, config: Dict[str, Any]) -> bool:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            log.error(f"Failed to save agents.json: {e}")
            return False

    # ------------------------------------------------------------------
    # Name resolution  (used by AgentSpawner)
    # ------------------------------------------------------------------

    def get_random_name(self, category: str, subcategory: str) -> Optional[str]:
        """
        Pick a random name from agents.json[category][subcategory].
        For GODs, subcategory is the god_type nested under GODs.dual.{god_type}.
        Falls back to DEFAULT_CONTENT if the list is empty or missing.
        """
        config = self.load_config()
        if category == "GODs":
            names = config.get("GODs", {}).get("dual", {}).get(subcategory, [])
            if not names:
                names = self.DEFAULT_CONTENT.get("GODs", {}).get("dual", {}).get(subcategory, [])
        else:
            names = config.get(category, {}).get(subcategory, [])
            if not names:
                names = self.DEFAULT_CONTENT.get(category, {}).get(subcategory, [])
        return random.choice(names) if names else None

    def get_random_god_type(self) -> str:
        """
        Auto-select a god type from SPAWNABLE_GOD_TYPES at random.
        Called when spawn_god() is invoked without a specific god_type.
        """
        return random.choice(self.SPAWNABLE_GOD_TYPES)

    # ------------------------------------------------------------------
    # Registration  (called after a name is chosen / given)
    # ------------------------------------------------------------------

    def add_name(self, category: str, subcategory: str, name: str):
        """
        Register a name in agents.json.
        For GODs, writes to GODs.dual.{subcategory} (god_type).
        No-ops silently if name is empty, 'Unnamed', or already present.
        """
        if not name or name == "Unnamed":
            return
        config = self.load_config()
        if category == "GODs":
            config.setdefault("GODs", {}).setdefault("dual", {}).setdefault(subcategory, [])
            lst = config["GODs"]["dual"][subcategory]
            if name not in lst:
                lst.append(name)
                self.save_config(config)
                log.info(f"Registered '{name}' → GODs/dual/{subcategory}")
        else:
            config.setdefault(category, {}).setdefault(subcategory, [])
            if name not in config[category][subcategory]:
                config[category][subcategory].append(name)
                self.save_config(config)
                log.info(f"Registered '{name}' → {category}/{subcategory}")

    # ------------------------------------------------------------------
    # High-level resolvers  (single call from AgentSpawner)
    # ------------------------------------------------------------------

    def resolve_npc_name(self, agent_id: str,
                         custom_name: Optional[str] = None,
                         gender: str = "male") -> str:
        """
        Return the display name to use for an NPC and register it.

          custom_name given  → register under NPCs/<gender>, return it
          custom_name absent → pick random from NPCs/<gender>, return it
        """
        gender = gender if gender in ("male", "female") else "male"
        name   = (
            custom_name
            if custom_name and custom_name not in ("Unnamed", "")
            else (self.get_random_name("NPCs", gender) or agent_id)
        )
        self.add_name("NPCs", gender, name)
        return name

    def resolve_god_name(self, agent_id: str,
                         custom_name: Optional[str] = None,
                         god_type:    Optional[str] = None) -> tuple:
        """
        Return (display_name, god_type) and register the name.

          god_type absent    → pick random from SPAWNABLE_GOD_TYPES
          custom_name given  → register under GODs/<god_type>, return it
          custom_name absent → pick random from GODs/dual, return it

        Returns:
            (name: str, god_type: str)
        """
        valid_types = self.SPAWNABLE_GOD_TYPES + ["wither"]
        if not god_type or god_type not in valid_types:
            god_type = self.get_random_god_type()
            log.info(f"Auto-selected god type: {god_type!r}")

        name = (
            custom_name
            if custom_name and custom_name not in ("Unnamed", "")
            else (
                self.get_random_name("GODs", god_type)
                or self.get_random_name("GODs", "oracle")  # fallback god pool
                or agent_id
            )
        )
        self.add_name("GODs", god_type, name)
        return name, god_type

    # ------------------------------------------------------------------
    # Individual registration helpers
    # ------------------------------------------------------------------

    def register_npc(self, name: str, gender: str) -> bool:
        """Register an NPC. gender must be 'male' or 'female'."""

        """Register an NPC. gender must be 'male' or 'female'."""
        if gender not in ("male", "female"):
            log.error(f"Invalid gender: {gender!r}")
            return False
        self.add_name("NPCs", gender, name)
        return True

    def register_god(self, name: str, god_type: str = "oracle") -> bool:
        """Register a God under GODs.dual.{god_type}."""
        self.add_name("GODs", god_type, name)
        return True

    # ------------------------------------------------------------------
    # Unregister
    # ------------------------------------------------------------------

    def unregister_npc(self, name: str, gender: str) -> bool:
        config = self.load_config()
        lst    = config.get("NPCs", {}).get(gender, [])
        if name in lst:
            lst.remove(name)
            return self.save_config(config)
        log.warning(f"NPC '{name}' not in {gender} list")
        return True

    def unregister_god(self, name: str, god_type: str = None) -> bool:
        config   = self.load_config()
        dual     = config.get("GODs", {}).get("dual", {})
        subtypes = [god_type] if god_type else list(dual.keys())
        for st in subtypes:
            lst = dual.get(st, [])
            if name in lst:
                lst.remove(name)
                return self.save_config(config)
        log.warning(f"God '{name}' not found under GODs/dual")
        return True

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_all_male_npcs(self)   -> List[str]:
        return self.load_config().get("NPCs", {}).get("male",  [])

    def get_all_female_npcs(self) -> List[str]:
        return self.load_config().get("NPCs", {}).get("female", [])

    def get_all_gods(self)        -> List[str]:
        dual = self.load_config().get("GODs", {}).get("dual", {})
        return [name for lst in dual.values() for name in lst]

    def get_stats(self) -> Dict[str, int]:
        cfg   = self.load_config()
        male  = len(cfg.get("NPCs", {}).get("male",   []))
        fem   = len(cfg.get("NPCs", {}).get("female", []))
        dual  = cfg.get("GODs", {}).get("dual", {})
        gods  = sum(len(v) for v in dual.values())
        return {
            "male_npcs":    male,
            "female_npcs":  fem,
            "gods":         gods,
            "total_agents": male + fem + gods,
        }