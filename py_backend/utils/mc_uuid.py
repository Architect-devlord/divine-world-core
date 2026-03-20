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

agents.json format:
{
    "NPCs": {
        "male":   {"Adam": 11401, "Abel": 11402, ...},
        "female": {"Eve": 11420, "Sarah": 11421, ...}
    },
    "GODs": {
        "dual": {
            "wither":         {"Mortis": 11440, "Necros": 11441, ...},
            "ender_dragon":   {"Draconis": 11444, ...},
            ...
        }
    }
}

Each name maps to a unique TCP port (starting at PORT_START = 11401) that
the DWClientMod TCPServer listens on for that specific agent.

Name-assignment rules (enforced by AgentSpawner, not here):
  - Name given explicitly  → use it, register in agents.json with next port.
  - No name, type = npc    → pick random key from NPCs[gender] dict.
  - No name, type = god    → pick random key from GODs["dual"][god_type] dict.
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
# Port allocation constants
# ---------------------------------------------------------------------------

PORT_START = 11401   # First port; increments for each new agent registered


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

    agents.json structure:
      NPCs.male   → {"Name": port, ...}
      NPCs.female → {"Name": port, ...}
      GODs.dual.<god_type> → {"Name": port, ...}

    Ports start at PORT_START (11401) and increment globally across all
    categories/subtypes.  Each registered name has exactly one port.

    On first use, if agents.json is not found, it is created with the
    built-in DEFAULT name pool (ports pre-assigned from PORT_START).
    """

    SPAWNABLE_GOD_TYPES: List[str] = [
        'wither', 'ender_dragon', 'oracle', 'elder_guardian', 'creaking', 'warden',
    ]

    # Raw name pools — ports are assigned dynamically by _build_default_content()
    _DEFAULT_NAMES: Dict[str, Any] = {
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

    # ------------------------------------------------------------------
    # Default content builder — assigns ports sequentially
    # ------------------------------------------------------------------

    @classmethod
    def _build_default_content(cls) -> Dict[str, Any]:
        """
        Convert the flat name lists in _DEFAULT_NAMES into {name: port} dicts
        with ports starting at PORT_START and incrementing globally.
        """
        port   = PORT_START
        result: Dict[str, Any] = {
            "NPCs": {"male": {}, "female": {}},
            "GODs": {"dual": {}},
        }

        for gender in ("male", "female"):
            for name in cls._DEFAULT_NAMES["NPCs"][gender]:
                result["NPCs"][gender][name] = port
                port += 1

        for god_type, names in cls._DEFAULT_NAMES["GODs"]["dual"].items():
            result["GODs"]["dual"][god_type] = {}
            for name in names:
                result["GODs"]["dual"][god_type][name] = port
                port += 1

        return result

    @classmethod
    def _default_content(cls) -> Dict[str, Any]:
        """Return the default content dict (cached after first call)."""
        if not hasattr(cls, "_cached_default"):
            cls._cached_default = cls._build_default_content()
        return cls._cached_default

    # ------------------------------------------------------------------
    # Init / path discovery
    # ------------------------------------------------------------------

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config_path()
        self._ensure_config_exists()
        log.info(f"AgentNameManager: {self.config_path}")

    def _find_config_path(self) -> Path:
        home = Path.home()
        candidates = [
            home / "Documents"              / "agents.json",
            home / "Desktop"                / "agents.json",
            home / "OneDrive" / "Documents" / "agents.json",
            home / "OneDrive" / "Desktop"   / "agents.json",
        ]
        for p in candidates:
            if p.exists():
                log.info(f"Found agents.json: {p}")
                return p
        return home / "Documents" / "agents.json"

    def _ensure_config_exists(self):
        if not self.config_path.exists():
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self._default_content(), f, indent=2)
                log.info(f"Created default agents.json: {self.config_path}")
            except Exception as e:
                log.error(f"Failed to create agents.json: {e}")

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self._default_content()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load agents.json: {e}")
            return self._default_content()

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
    # Port management
    # ------------------------------------------------------------------

    def _next_port(self, config: Dict[str, Any]) -> int:
        """
        Scan the entire config for the highest port in use and return +1.
        Minimum is PORT_START.
        """
        max_port = PORT_START - 1

        for gender_dict in config.get("NPCs", {}).values():
            if isinstance(gender_dict, dict):
                for v in gender_dict.values():
                    if isinstance(v, int):
                        max_port = max(max_port, v)

        for type_dict in config.get("GODs", {}).get("dual", {}).values():
            if isinstance(type_dict, dict):
                for v in type_dict.values():
                    if isinstance(v, int):
                        max_port = max(max_port, v)

        return max_port + 1

    def get_port(self, name: str) -> Optional[int]:
        """
        Return the TCP port assigned to *name* anywhere in agents.json.
        Returns None if the name is not registered.
        """
        config = self.load_config()

        for gender_dict in config.get("NPCs", {}).values():
            if isinstance(gender_dict, dict) and name in gender_dict:
                return gender_dict[name]

        for type_dict in config.get("GODs", {}).get("dual", {}).values():
            if isinstance(type_dict, dict) and name in type_dict:
                return type_dict[name]

        return None

    # get_port_for_name — convenience alias
    def get_port_for_name(self, name: str) -> Optional[int]:
        return self.get_port(name)


    def resolve_display_name(
        self,
        agent_id: str,
        custom_name: Optional[str] = None,
    ) -> str:
        """
        Resolve the Minecraft display name for an agent.
        Never adds DW_ / DWGOD_ prefixes — those are gone.

        Priority:
          1. custom_name  (if set and not empty / 'Unnamed')
          2. agents.json  — if agent_id itself IS a registered name
          3. agent_id as-is  (fallback — still no prefix)
        """
        if custom_name and custom_name not in ("Unnamed", ""):
            return custom_name
        # If the agent_id is itself a registered display name, use it
        if self.get_port(agent_id) is not None:
            return agent_id
        # Plain fallback — still no prefix
        return agent_id

    def get_all_ports(self) -> Dict[str, int]:
        """Return a flat {name: port} dict across all categories."""
        config = self.load_config()
        result: Dict[str, int] = {}
        for gender_dict in config.get("NPCs", {}).values():
            if isinstance(gender_dict, dict):
                result.update(gender_dict)
        for type_dict in config.get("GODs", {}).get("dual", {}).values():
            if isinstance(type_dict, dict):
                result.update(type_dict)
        return result

    # ------------------------------------------------------------------
    # Name resolution  (used by AgentSpawner)
    # ------------------------------------------------------------------

    def get_random_name(self, category: str, subcategory: str) -> Optional[str]:
        """
        Pick a random name (key) from agents.json[category][subcategory].
        Falls back to DEFAULT_CONTENT if the dict is empty or missing.
        """
        config = self.load_config()
        if category == "GODs":
            names_dict = config.get("GODs", {}).get("dual", {}).get(subcategory, {})
            if not names_dict:
                names_dict = self._default_content().get("GODs", {}).get("dual", {}).get(subcategory, {})
        else:
            names_dict = config.get(category, {}).get(subcategory, {})
            if not names_dict:
                names_dict = self._default_content().get(category, {}).get(subcategory, {})

        keys = list(names_dict.keys()) if isinstance(names_dict, dict) else []
        return random.choice(keys) if keys else None

    def get_random_god_type(self) -> str:
        return random.choice(self.SPAWNABLE_GOD_TYPES)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_name(self, category: str, subcategory: str, name: str) -> int:
        """
        Register a name in agents.json and return its assigned port.
        If the name is already registered, returns its existing port.
        No-ops (returns 0) if name is empty or 'Unnamed'.
        """
        if not name or name == "Unnamed":
            return 0

        config = self.load_config()

        if category == "GODs":
            config.setdefault("GODs", {}).setdefault("dual", {}).setdefault(subcategory, {})
            target: dict = config["GODs"]["dual"][subcategory]
        else:
            config.setdefault(category, {}).setdefault(subcategory, {})
            target = config[category][subcategory]

        # Migrate legacy list format if ever encountered
        if isinstance(target, list):
            log.warning(f"Migrating legacy list format for {category}/{subcategory}")
            port_counter = self._next_port(config)
            migrated = {}
            for n in target:
                migrated[n] = port_counter
                port_counter += 1
            target = migrated
            if category == "GODs":
                config["GODs"]["dual"][subcategory] = target
            else:
                config[category][subcategory] = target

        # Return existing port if already registered
        if name in target:
            return target[name]

        # Assign next available port
        port = self._next_port(config)
        target[name] = port
        self.save_config(config)

        log.info(f"Registered '{name}' → {category}/{subcategory} on port {port}")
        return port

    # ------------------------------------------------------------------
    # High-level resolvers  (single call from AgentSpawner)
    # ------------------------------------------------------------------

    def resolve_npc_name(self, agent_id: str,
                         custom_name: Optional[str] = None,
                         gender: str = "male") -> str:
        gender = gender if gender in ("male", "female") else "male"
        name = (
            custom_name
            if custom_name and custom_name not in ("Unnamed", "")
            else (self.get_random_name("NPCs", gender) or agent_id)
        )
        self.add_name("NPCs", gender, name)
        return name

    def resolve_god_name(self, agent_id: str,
                         custom_name: Optional[str] = None,
                         god_type: Optional[str] = None) -> tuple:
        valid_types = self.SPAWNABLE_GOD_TYPES + ["wither"]
        if not god_type or god_type not in valid_types:
            god_type = self.get_random_god_type()
            log.info(f"Auto-selected god type: {god_type!r}")

        name = (
            custom_name
            if custom_name and custom_name not in ("Unnamed", "")
            else (
                self.get_random_name("GODs", god_type)
                or self.get_random_name("GODs", "oracle")
                or agent_id
            )
        )
        self.add_name("GODs", god_type, name)
        return name, god_type

    # ------------------------------------------------------------------
    # Individual registration helpers
    # ------------------------------------------------------------------

    def register_npc(self, name: str, gender: str) -> bool:
        if gender not in ("male", "female"):
            log.error(f"Invalid gender: {gender!r}")
            return False
        self.add_name("NPCs", gender, name)
        return True

    def register_god(self, name: str, god_type: str = "oracle") -> bool:
        self.add_name("GODs", god_type, name)
        return True

    # ------------------------------------------------------------------
    # Unregister
    # ------------------------------------------------------------------

    def unregister_npc(self, name: str, gender: str) -> bool:
        config = self.load_config()
        target = config.get("NPCs", {}).get(gender, {})
        if isinstance(target, dict) and name in target:
            del target[name]
            return self.save_config(config)
        log.warning(f"NPC '{name}' not in {gender} list")
        return True

    def unregister_god(self, name: str, god_type: str = None) -> bool:
        config   = self.load_config()
        dual     = config.get("GODs", {}).get("dual", {})
        subtypes = [god_type] if god_type else list(dual.keys())
        for st in subtypes:
            target = dual.get(st, {})
            if isinstance(target, dict) and name in target:
                del target[name]
                return self.save_config(config)
        log.warning(f"God '{name}' not found under GODs/dual")
        return True

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_all_male_npcs(self) -> List[str]:
        d = self.load_config().get("NPCs", {}).get("male", {})
        return list(d.keys()) if isinstance(d, dict) else []

    def get_all_female_npcs(self) -> List[str]:
        d = self.load_config().get("NPCs", {}).get("female", {})
        return list(d.keys()) if isinstance(d, dict) else []

    def get_all_gods(self) -> List[str]:
        dual = self.load_config().get("GODs", {}).get("dual", {})
        return [name for type_dict in dual.values()
                if isinstance(type_dict, dict)
                for name in type_dict.keys()]

    def get_stats(self) -> Dict[str, int]:
        cfg  = self.load_config()
        male = len(cfg.get("NPCs", {}).get("male",   {}))
        fem  = len(cfg.get("NPCs", {}).get("female", {}))
        dual = cfg.get("GODs", {}).get("dual", {})
        gods = sum(len(v) for v in dual.values() if isinstance(v, dict))
        return {
            "male_npcs":    male,
            "female_npcs":  fem,
            "gods":         gods,
            "total_agents": male + fem + gods,
        }
