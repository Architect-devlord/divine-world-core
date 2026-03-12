# py_backend/utils/validation.py
"""
Request validation and sanitization with Pydantic.
Prevents injection attacks and ensures data integrity.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Chat message validation."""
    message:  str = Field(..., min_length=1, max_length=10_000)
    agent_id: str = Field(default="demo", pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator('message')
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        v = v.strip()
        v = v.replace('\x00', '')
        v = re.sub(r'\n{4,}', '\n\n\n', v)
        # Keep printable chars + newline + tab
        v = ''.join(c for c in v if ord(c) >= 32 or c in '\n\t')
        return v

    @field_validator('agent_id')
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("agent_id contains invalid characters")
        return v


class FileUploadRequest(BaseModel):
    """File upload validation."""
    filename: str = Field(..., max_length=255)
    agent_id: str = Field(default="demo", pattern=r"^[a-zA-Z0-9_-]+$")
    filetype: str = Field(default="application/octet-stream")

    @field_validator('filename')
    @classmethod
    def safe_filename(cls, v: str) -> str:
        safe = Path(v).name
        safe = re.sub(r'[^\w\s.-]', '', safe)
        if safe.startswith('.'):
            safe = 'file' + safe
        if not safe or safe.isspace():
            safe = 'unnamed_file'
        if len(safe) > 200:
            parts = safe.rsplit('.', 1)
            safe = (parts[0][:190] + '.' + parts[1]) if len(parts) == 2 else safe[:200]
        return safe

    @field_validator('filetype')
    @classmethod
    def validate_filetype(cls, v: str) -> str:
        allowed = ['text/', 'image/', 'audio/', 'video/',
                   'application/json', 'application/pdf',
                   'application/octet-stream']
        return v if any(v.startswith(t) for t in allowed) else 'application/octet-stream'


class AgentSpawnRequest(BaseModel):
    """
    Agent spawn validation.

    agent_type values:
      'npc'          — regular NPC (god_type ignored)
      'god'          — god entity, god_type auto-selected if omitted
      'god_<type>'   — god entity with explicit type

    god_type values (optional, only used when agent_type starts with 'god'):
      'ender_dragon', 'wither', 'warden', 'oracle',
      'elder_guardian', 'creaking'
      If omitted, AgentSpawner.spawn_god() auto-selects from SPAWNABLE_GOD_TYPES.
    """
    agent_id:     str  = Field(..., pattern=r"^[a-zA-Z0-9_-]+$",
                               min_length=1, max_length=50)
    agent_type:   str  = Field(default="npc")
    god_type:     Optional[str] = Field(default=None)
    custom_name:  Optional[str] = Field(default=None, max_length=64)
    gender:       Optional[str] = Field(default=None,
                                        pattern=r"^(male|female|dual)$")
    server_addr:  str  = Field(default="127.0.0.1:25565")
    persona_traits: Optional[Dict[str, float]] = None

    _VALID_AGENT_TYPES = {"npc", "god"}
    _VALID_GOD_TYPES   = {
        "ender_dragon", "wither", "warden",
        "oracle", "elder_guardian", "creaking",
    }

    @field_validator('agent_type')
    @classmethod
    def validate_agent_type(cls, v: str) -> str:
        # Allow 'npc', 'god', or 'god_<type>' for backwards compat
        if v == 'npc':
            return v
        if v == 'god':
            return v
        if v.startswith('god_'):
            suffix = v[4:]
            valid  = {
                "ender_dragon", "wither", "warden",
                "oracle", "elder_guardian", "creaking",
            }
            if suffix in valid:
                return v
        raise ValueError(
            f"Invalid agent_type {v!r}. "
            f"Use 'npc', 'god', or 'god_<type>' where type is one of: "
            f"ender_dragon, wither, warden, oracle, elder_guardian, creaking"
        )

    @field_validator('god_type')
    @classmethod
    def validate_god_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {
            "ender_dragon", "wither", "warden",
            "oracle", "elder_guardian", "creaking",
        }
        if v not in valid:
            raise ValueError(
                f"Invalid god_type {v!r}. Available: {', '.join(sorted(valid))}"
            )
        return v

    @field_validator('server_addr')
    @classmethod
    def validate_server(cls, v: str) -> str:
        if not re.match(r'^[\w.-]+:\d{1,5}$', v):
            raise ValueError("Invalid server address (expected host:port)")
        port = int(v.split(':')[-1])
        if not (1 <= port <= 65535):
            raise ValueError("Port must be 1–65535")
        return v

    @field_validator('persona_traits')
    @classmethod
    def validate_traits(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        if v is None:
            return None
        valid_keys = {
            'openness', 'conscientiousness', 'extraversion',
            'agreeableness', 'neuroticism', 'boldness',
            'curiosity', 'sociability',
        }
        filtered = {
            k: max(-1.0, min(1.0, float(val)))
            for k, val in v.items()
            if k in valid_keys
        }
        return filtered or None


class ControllerActivationRequest(BaseModel):
    """Controller mode activation validation."""
    agent_id:        str            = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    permissions:     List[str]      = Field(default_factory=list)
    acknowledged:    bool           = Field(default=False)
    camera_index:    Optional[int]  = Field(default=None, ge=0, le=10)
    mic_device_index:Optional[int]  = Field(default=None, ge=0, le=10)
    resolution:      List[int]      = Field(default=[640, 480])
    fps:             int            = Field(default=20, ge=1, le=60)
    mic_sample_rate: int            = Field(default=16_000, ge=8_000, le=48_000)

    @field_validator('permissions')
    @classmethod
    def validate_permissions(cls, v: List[str]) -> List[str]:
        return [p for p in v if p in ('camera', 'microphone', 'filesystem', 'network')]

    @field_validator('resolution')
    @classmethod
    def validate_resolution(cls, v: List[int]) -> List[int]:
        if len(v) != 2:
            return [640, 480]
        w = v[0] if 160 <= v[0] <= 1920 else 640
        h = v[1] if 120 <= v[1] <= 1080 else 480
        return [w, h]


class TaskSwitchRequest(BaseModel):
    """Continual learning task switch validation."""
    task_id: int = Field(..., ge=0, le=1000)


class PlayerEventRequest(BaseModel):
    """Player connection event validation."""
    agent_id:    str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    player_uuid: str = Field(..., pattern=r"^[a-f0-9-]+$")
    agent_type:  str = Field(default="npc")
    event:       str = Field(..., pattern=r"^(connected|disconnected)$")

    @field_validator('player_uuid')
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        if not re.match(
            r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
            v.lower()
        ):
            raise ValueError("Invalid UUID format")
        return v.lower()


__all__ = [
    'ChatRequest',
    'FileUploadRequest',
    'AgentSpawnRequest',
    'ControllerActivationRequest',
    'TaskSwitchRequest',
    'PlayerEventRequest',
]