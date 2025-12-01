# py_backend/utils/validation.py - PRODUCTION VERSION
"""
Request validation and sanitization with Pydantic.
Prevents injection attacks and ensures data integrity.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from pathlib import Path
import re

class ChatRequest(BaseModel):
    """Chat message validation"""
    message: str = Field(..., min_length=1, max_length=10000)
    agent_id: str = Field(default="demo", regex="^[a-zA-Z0-9_-]+$")
    
    @validator('message')
    def sanitize_message(cls, v):
        """Remove dangerous characters and limit formatting"""
        # Strip leading/trailing whitespace
        v = v.strip()
        
        # Remove null bytes
        v = v.replace('\x00', '')
        
        # Limit consecutive newlines (prevent spam)
        v = re.sub(r'\n{4,}', '\n\n\n', v)
        
        # Remove control characters except newline and tab
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\t')
        
        return v
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        """Ensure agent_id is safe"""
        if len(v) > 100:
            raise ValueError("agent_id too long (max 100 characters)")
        
        # No path traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("agent_id contains invalid characters")
        
        return v


class FileUploadRequest(BaseModel):
    """File upload validation"""
    filename: str = Field(..., max_length=255)
    agent_id: str = Field(default="demo", regex="^[a-zA-Z0-9_-]+$")
    filetype: str = Field(default="application/octet-stream")
    
    @validator('filename')
    def safe_filename(cls, v):
        """Prevent path traversal and sanitize filename"""
        # Get just the filename (no path components)
        safe_name = Path(v).name
        
        # Remove dangerous characters (keep alphanumeric, dots, dashes, underscores)
        safe_name = re.sub(r'[^\w\s.-]', '', safe_name)
        
        # Prevent hidden files
        if safe_name.startswith('.'):
            safe_name = 'file' + safe_name
        
        # Ensure not empty
        if not safe_name or safe_name.isspace():
            safe_name = 'unnamed_file'
        
        # Limit length
        if len(safe_name) > 200:
            name_parts = safe_name.rsplit('.', 1)
            if len(name_parts) == 2:
                safe_name = name_parts[0][:190] + '.' + name_parts[1]
            else:
                safe_name = safe_name[:200]
        
        return safe_name
    
    @validator('filetype')
    def validate_filetype(cls, v):
        """Ensure valid MIME type"""
        allowed_types = [
            'text/', 'image/', 'audio/', 'video/',
            'application/json', 'application/pdf',
            'application/octet-stream'
        ]
        
        if not any(v.startswith(t) for t in allowed_types):
            return 'application/octet-stream'
        
        return v


class AgentSpawnRequest(BaseModel):
    """Agent spawn validation"""
    agent_id: str = Field(..., regex="^[a-zA-Z0-9_-]+$", min_length=3, max_length=50)
    gender: Optional[str] = Field(default=None, regex="^(male|female|dual)$")
    agent_type: str = Field(default="npc", regex="^(npc|god_[a-z]+)$")
    server_addr: str = Field(default="127.0.0.1:25565")
    persona_traits: Optional[Dict[str, float]] = None
    
    @validator('server_addr')
    def validate_server(cls, v):
        """Validate server address format"""
        # Must be host:port or IP:port
        pattern = r'^[\w.-]+:\d{1,5}$'
        if not re.match(pattern, v):
            raise ValueError("Invalid server address format (expected host:port)")
        
        # Validate port range
        parts = v.split(':')
        port = int(parts[1])
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        
        return v
    
    @validator('persona_traits')
    def validate_traits(cls, v):
        """Validate personality traits"""
        if v is None:
            return None
        
        valid_traits = [
            'openness', 'conscientiousness', 'extraversion',
            'agreeableness', 'neuroticism', 'boldness',
            'curiosity', 'sociability'
        ]
        
        # Filter to valid traits only
        filtered = {
            k: float(v[k]) 
            for k in v 
            if k in valid_traits
        }
        
        # Clamp values to [-1, 1]
        for k in filtered:
            filtered[k] = max(-1.0, min(1.0, filtered[k]))
        
        return filtered if filtered else None


class ControllerActivationRequest(BaseModel):
    """Controller mode activation validation"""
    agent_id: str = Field(..., regex="^[a-zA-Z0-9_-]+$")
    permissions: List[str] = Field(default_factory=list)
    acknowledged: bool = Field(default=False)
    camera_index: Optional[int] = Field(default=None, ge=0, le=10)
    mic_device_index: Optional[int] = Field(default=None, ge=0, le=10)
    resolution: List[int] = Field(default=[640, 480])
    fps: int = Field(default=20, ge=1, le=60)
    mic_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    
    @validator('permissions')
    def validate_permissions(cls, v):
        """Ensure only valid permissions"""
        valid = ['camera', 'microphone', 'filesystem', 'network']
        return [p for p in v if p in valid]
    
    @validator('resolution')
    def validate_resolution(cls, v):
        """Ensure valid resolution"""
        if len(v) != 2:
            return [640, 480]
        
        width, height = v
        
        # Clamp to reasonable ranges
        if width < 160 or width > 1920:
            width = 640
        if height < 120 or height > 1080:
            height = 480
        
        return [width, height]


class TaskSwitchRequest(BaseModel):
    """Continual learning task switch validation"""
    task_id: int = Field(..., ge=0, le=1000)
    
    @validator('task_id')
    def validate_task_id(cls, v):
        """Ensure reasonable task ID"""
        if v < 0:
            return 0
        if v > 1000:
            return 1000
        return v


class PlayerEventRequest(BaseModel):
    """Player event validation"""
    agent_id: str = Field(..., regex="^[a-zA-Z0-9_-]+$")
    player_uuid: str = Field(..., regex="^[a-f0-9-]+$")
    agent_type: str = Field(default="npc")
    event: str = Field(..., regex="^(connected|disconnected)$")
    
    @validator('player_uuid')
    def validate_uuid(cls, v):
        """Validate UUID format"""
        # Standard UUID format: 8-4-4-4-12
        pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
        if not re.match(pattern, v.lower()):
            raise ValueError("Invalid UUID format")
        return v.lower()


# Export all validators
__all__ = [
    'ChatRequest',
    'FileUploadRequest',
    'AgentSpawnRequest',
    'ControllerActivationRequest',
    'TaskSwitchRequest',
    'PlayerEventRequest',
]