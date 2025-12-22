# py_backend/config.py - Centralized Configuration
"""
Configuration management for Divine World Backend.
Single source of truth for all paths, ports, and settings.
"""

import os
from pathlib import Path
from typing import Optional
import logging

log = logging.getLogger("config")


class Config:
    """Global configuration"""
    
    # ==================== PATHS ====================
    BASE_DIR = Path(__file__).parent.parent
    PY_BACKEND_DIR = Path(__file__).parent
    AI_CORE_DIR = PY_BACKEND_DIR / "ai_core"
    
    NPC_APPLICATIONS_DIR = BASE_DIR / "npc_applications"
    # Unify storage under `npc_applications/data` for portability
    DATA_DIR = NPC_APPLICATIONS_DIR / "data"
    BRAINS_DIR = DATA_DIR / "brains"
    UPLOADS_DIR = DATA_DIR / "uploads"
    AGENTS_DIR = DATA_DIR / "agents"
    DEMOS_DIR = DATA_DIR / "demos"
    TEACHING_DIR = DATA_DIR / "teaching_materials"
    
    # Frontend paths
    FRONTEND_DIR = BASE_DIR / "dw_agent" / "electron" / "react-app"
    FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
    
    # ==================== NETWORK ====================
    BASE_BACKEND_PORT = int(os.getenv("DW_BACKEND_PORT", "11400"))
    FRONTEND_PORT_OFFSET = 1
    WEBSOCKET_MAX_FPS = int(os.getenv("DW_MAX_FPS", "30"))
    WEBSOCKET_MAX_LATENCY_MS = int(os.getenv("DW_MAX_LATENCY_MS", "100"))
    
    # ==================== MINECRAFT ====================
    CLIENT_JAR = os.getenv("DW_CLIENT_JAR", "DWClientBot.jar")
    DEFAULT_SERVER = os.getenv("DW_SERVER", "127.0.0.1:25565")
    CLIENT_MEMORY_MB = int(os.getenv("DW_CLIENT_MEMORY", "2048"))
    
    # ==================== SAFETY LIMITS ====================
    MAX_BRAIN_SIZE_MB = 100
    MAX_UPLOAD_SIZE_MB = 50
    MAX_BRAIN_SAVE_WAIT_SECONDS = 30
    MAX_BRAIN_STABILITY_CHECKS = 5
    BRAIN_STABILITY_WAIT_SECONDS = 0.5
    
    # Auto-save intervals
    BRAIN_AUTOSAVE_INTERVAL_SECONDS = 300  # 5 minutes
    
    # ==================== PERFORMANCE ====================
    MAX_MEMORY_EVENTS = 10000
    MAX_EPISODIC_MEMORY = 10000
    MAX_MESSAGE_QUEUE_SIZE = 100
    MAX_LATENCY_HISTORY = 100
    
    # ==================== LOGGING ====================
    LOG_LEVEL = os.getenv("DW_LOG_LEVEL", "INFO")
    LOG_FORMAT = '[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
    
    # ==================== PYINSTALLER ====================
    PYINSTALLER_HIDDEN_IMPORTS = [
        'uvicorn',
        'fastapi',
        'websockets',
        'numpy',
        'torch',
        'ai_core',
        'ai_core.agent',
        'ai_core.brain_core',
        'ai_core.brain_language',
        'ai_core.brain_capsule',
        'ai_core.personality',
        'ai_core.emotion',
        'ai_core.memory',
        'ai_core.reward_system',
        'ai_core.planner',
        'ai_core.actuators',
        'ai_core.vision',
        'py_backend',
        'py_backend.main',
    ]
    
    @classmethod
    def ensure_dirs(cls):
        """Create all required directories"""
        dirs = [
            cls.DATA_DIR,
            cls.BRAINS_DIR,
            cls.UPLOADS_DIR,
            cls.AGENTS_DIR,
            cls.DEMOS_DIR,
            cls.TEACHING_DIR,
            cls.NPC_APPLICATIONS_DIR,
        ]
        
        for dir_path in dirs:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log.error(f"Failed to create directory {dir_path}: {e}")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        issues = []
        
        # Check critical paths exist
        if not cls.AI_CORE_DIR.exists():
            issues.append(f"ai_core directory not found: {cls.AI_CORE_DIR}")
        
        if not cls.PY_BACKEND_DIR.exists():
            issues.append(f"py_backend directory not found: {cls.PY_BACKEND_DIR}")
        
        # Check ports
        if not (1024 <= cls.BASE_BACKEND_PORT <= 65535):
            issues.append(f"Invalid backend port: {cls.BASE_BACKEND_PORT}")
        
        if issues:
            for issue in issues:
                log.error(f"Config validation failed: {issue}")
            return False
        
        return True
    
    @classmethod
    def get_agent_brain_path(cls, agent_id: str) -> Path:
        """Get brain path for agent"""
        return cls.BRAINS_DIR / agent_id / "brain.pcap"
    
    @classmethod
    def get_agent_upload_dir(cls, agent_id: str) -> Path:
        """Get upload directory for agent"""
        upload_dir = cls.UPLOADS_DIR / agent_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    # ==================== OBJECT STORAGE (MINIO/S3) ====================
    MINIO_ENDPOINT = os.getenv('DW_MINIO_ENDPOINT', 'http://127.0.0.1:9000')
    MINIO_ACCESS_KEY = os.getenv('DW_MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('DW_MINIO_SECRET_KEY', 'minioadmin')
    MINIO_BUCKET = os.getenv('DW_MINIO_BUCKET', 'divine-world')
    
    @classmethod
    def get_package_dir(cls, agent_id: str) -> Path:
        """Get package directory for agent"""
        return cls.NPC_APPLICATIONS_DIR / f"{agent_id}_portable"


# Initialize on import
Config.ensure_dirs()

if not Config.validate():
    log.warning("Configuration validation failed - some features may not work")