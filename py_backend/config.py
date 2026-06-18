# py_backend/config.py
"""
Configuration management for Divine World Backend.
Single source of truth for all paths, ports, and settings.
"""

import os
from pathlib import Path
import logging

log = logging.getLogger("config")


class Config:
    """Global configuration"""

    # ==================== PATHS ====================
    # __file__ is: .../divine-world-core/py_backend/config.py
    PY_BACKEND_DIR = Path(__file__).parent          # .../py_backend/
    BASE_DIR       = PY_BACKEND_DIR.parent          # .../divine-world-core/
    HOME           = BASE_DIR.parent                # parent of project root


    # it would look for divine-world-core/py_backend/ai_core/ instead of
    # divine-world-core/py_backend/ai_core/
    AI_CORE_DIR = PY_BACKEND_DIR / "ai_core"              # .../divine-world-core/py_backend/ai_core/

    SERVER_FOLDER = HOME / "DW_Server"

    NPC_APPLICATIONS_DIR = BASE_DIR / "npc_applications"
    DATA_DIR     = NPC_APPLICATIONS_DIR / "data"
    BRAINS_DIR   = DATA_DIR / "brains"
    UPLOADS_DIR  = DATA_DIR / "uploads"
    AGENTS_DIR   = DATA_DIR / "agents"
    DEMOS_DIR    = DATA_DIR / "demos"
    TEACHING_DIR = DATA_DIR / "teaching_materials"

    FRONTEND_DIR      = BASE_DIR / "dw_agent" / "electron" / "react-app"
    FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

    # ==================== NETWORK ====================
    BASE_BACKEND_PORT        = int(os.getenv("DW_BACKEND_PORT", "11400"))
    FRONTEND_PORT_OFFSET     = 1
    WEBSOCKET_MAX_FPS        = int(os.getenv("DW_MAX_FPS", "30"))
    WEBSOCKET_MAX_LATENCY_MS = int(os.getenv("DW_MAX_LATENCY_MS", "100"))

    # ==================== MINECRAFT ====================
    _env_client_jar    = os.getenv("DW_CLIENT_JAR")
    _default_built_jar = BASE_DIR / "DWClientBot" / "build" / "libs" / "dwclient-1.0.0.jar"
    if _env_client_jar:
        CLIENT_JAR = Path(_env_client_jar)
    elif _default_built_jar.exists():
        CLIENT_JAR = _default_built_jar
    else:
        CLIENT_JAR = None

    _env_mod_jar     = os.getenv("DW_MOD_JAR")
    _default_mod_jar = BASE_DIR / "DivineWorld" / "build" / "libs" / "divineworld-1.0.0-all.jar"
    if _env_mod_jar:
        MOD_JAR = Path(_env_mod_jar)
    elif _default_mod_jar.exists():
        MOD_JAR = _default_mod_jar
    else:
        MOD_JAR = None

    DEFAULT_SERVER   = os.getenv("DW_SERVER", "127.0.0.1:25565")
    CLIENT_MEMORY_MB = int(os.getenv("DW_CLIENT_MEMORY", "2048"))

    # ==================== ULTIMMC ====================
    USE_ULTIMMC       = os.getenv("DW_USE_ULTIMMC", "true").lower() in ("true", "1", "yes")
    ULTIMMC_PATH      = os.getenv("DW_ULTIMMC_PATH")
    MINECRAFT_VERSION = os.getenv("DW_MINECRAFT_VERSION", "1.20.1")
    FORGE_VERSION     = os.getenv("DW_FORGE_VERSION", "47.3.0")

    # ==================== SAFETY LIMITS ====================
    MAX_BRAIN_SIZE_MB            = 100
    MAX_UPLOAD_SIZE_MB           = 50
    MAX_BRAIN_SAVE_WAIT_SECONDS  = 30
    MAX_BRAIN_STABILITY_CHECKS   = 5
    BRAIN_STABILITY_WAIT_SECONDS = 0.5
    BRAIN_AUTOSAVE_INTERVAL_SECONDS = 300

    # ==================== PERFORMANCE ====================
    MAX_MEMORY_EVENTS      = 10000
    MAX_EPISODIC_MEMORY    = 10000
    MAX_MESSAGE_QUEUE_SIZE = 100
    MAX_LATENCY_HISTORY    = 100

    # ==================== LOGGING ====================
    LOG_LEVEL  = os.getenv("DW_LOG_LEVEL", "INFO")
    LOG_FORMAT = '[%(asctime)s] %(levelname)s - %(name)s - %(message)s'

    # ==================== PYINSTALLER ====================
    #
    # AGENT_HIDDEN_IMPORTS  -- modules bundled INTO a packaged agent exe.
    #   Rule: include only what a single running agent needs to perceive,
    #   think, act, save its brain, and serve its own FastAPI backend.
    #
    #   Excluded by design:
    #     py_backend.main              -- server-manager; not part of the agent
    #     py_backend.auto_packager     -- build-time tool; meaningless at runtime
    #     py_backend.packager          -- same as above
    #     py_backend.breeding_system   -- orchestrated by the server; agents only
    #                                     carry BreedingState inside brain_capsule
    #     py_backend.auto_connect_system -- server startup helper, not agent
    #     py_backend.minecraft_launcher  -- launcher helper, not agent
    #     py_backend.chat_system -- server-side router, not agent
    #     py_backend.agent_spawner     -- spawning belongs to the server
    #     ai_core.agent_spawner        -- same reason
    #
    #   RL / policy modules (rl.*) ARE included because the agent needs them
    #   to run its transformer policy during inference.
    #
    AGENT_HIDDEN_IMPORTS = [
        # -- web server (each agent runs its own FastAPI backend) --------
        'uvicorn', 'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.websockets', 'uvicorn.lifespan',
        'fastapi', 'fastapi.middleware.cors',
        'websockets', 'websockets.exceptions',
        'pydantic', 'starlette',

        # -- numerics / ML -----------------------------------------------
        'numpy', 'torch', 'torch.nn', 'torch.optim',
        'stable_baselines3', 'stable_baselines3.common',
        'stable_baselines3.common.policies',

        # -- ai_core: agent & brain --------------------------------------
        'py_backend.ai_core',
        'py_backend.ai_core.agent',                   # NPCAgent -- the agent itself
        'py_backend.ai_core.brain_core',              # deliberation engine
        'py_backend.ai_core.brain_capsule',           # save / load brain
        'py_backend.ai_core.brain_language',          # language intelligence (lazy)
        'py_backend.ai_core.cognitive_loop',          # background thinking thread
        'py_backend.ai_core.communication_protocol',  # WebSocket IPC with Minecraft mod
        'py_backend.ai_core.emotion',                 # emotion system
        'py_backend.ai_core.memory',                  # unified memory store
        'py_backend.ai_core.personality',             # personality + gender types
        'py_backend.ai_core.planner',                 # cognitive planner
        'py_backend.ai_core.actuators',               # action execution
        'py_backend.ai_core.reward_system',           # reward / intrinsic motivation
        'py_backend.ai_core.vision',                  # visual perception
        'py_backend.ai_core.audio_processors',        # audio perception (FIX: plural, matches audio_processors.py)
        'py_backend.ai_core.god_controls',            # god-tier abilities (no-op for NPCs)
        'py_backend.ai_core.web_browser',             # web-browsing tool
        'py_backend.ai_core.world_model',             # forward model (lazy)
        'py_backend.ai_core.config',                  # Config class

        # -- RL / policy (agent uses these for inference) ----------------
        'py_backend.rl',
        'py_backend.rl.policy',                       # TransformerPolicy / GodTransformerPolicy
        'py_backend.ai_core.reward_system',                # rl-specific reward shaping

        # -- py_backend: only the pieces the agent process needs ---------
        'py_backend',
        'py_backend.config',               # shared Config (paths, ports)
        'py_backend.utils',
        'py_backend.utils.mc_uuid',        # Minecraft UUID generation
        'py_backend.utils.agents_json_manager',
        'py_backend.utils.action_format_sync',
        'py_backend.utils.dw_controller',  # controller runtime (sensors)
        'py_backend.utils.validation',     # request validation
    ]

    # Back-compat alias — packager.py reads PYINSTALLER_HIDDEN_IMPORTS
    PYINSTALLER_HIDDEN_IMPORTS = AGENT_HIDDEN_IMPORTS

    # -- Explicitly excluded from the agent bundle -----------------------
    # Passed as --exclude-module to PyInstaller so they are never pulled in
    # through transitive imports.
    AGENT_EXCLUDE_MODULES = [
        # Server-manager modules (live in main.py process, not in agents)
        'py_backend.main',
        'py_backend.auto_packager',
        'py_backend.packager',
        'py_backend.breeding_system',
        'py_backend.agent_spawner',
        'py_backend.auto_connect_system',
        'py_backend.minecraft_launcher',
        'py_backend.chat_system',
        'py_backend.chat_launcher',
        'py_backend.ai_core.agent_spawner',
        # Heavy server-only deps (not needed inside an agent exe)
        'psutil',
        # Dev / test tools
        'pytest', 'IPython', 'jupyter',
    ]

    # ==================== HELPERS ====================

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.DATA_DIR, cls.BRAINS_DIR, cls.UPLOADS_DIR,
                  cls.AGENTS_DIR, cls.DEMOS_DIR, cls.TEACHING_DIR,
                  cls.NPC_APPLICATIONS_DIR]:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log.error(f"Failed to create {d}: {e}")

    @classmethod
    def validate(cls) -> bool:
        issues = []
        if not cls.AI_CORE_DIR.exists():
            issues.append(f"ai_core not found: {cls.AI_CORE_DIR}")
        if not cls.PY_BACKEND_DIR.exists():
            issues.append(f"py_backend not found: {cls.PY_BACKEND_DIR}")
        if not (1024 <= cls.BASE_BACKEND_PORT <= 65535):
            issues.append(f"Invalid port: {cls.BASE_BACKEND_PORT}")
        for issue in issues:
            log.error(f"Config: {issue}")
        return len(issues) == 0

    @classmethod
    def get_agent_brain_path(cls, agent_id: str) -> Path:
        return cls.BRAINS_DIR / agent_id / "brain.pcap"

    @classmethod
    def get_agent_upload_dir(cls, agent_id: str) -> Path:
        d = cls.UPLOADS_DIR / agent_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def get_package_dir(cls, agent_id: str) -> Path:
        return cls.NPC_APPLICATIONS_DIR / f"{agent_id}"

    # ==================== MINIO/S3 ====================
    MINIO_ENDPOINT   = os.getenv('DW_MINIO_ENDPOINT',   'http://127.0.0.1:9000')
    MINIO_ACCESS_KEY = os.getenv('DW_MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('DW_MINIO_SECRET_KEY', 'minioadmin')
    MINIO_BUCKET     = os.getenv('DW_MINIO_BUCKET',     'divine-world')


Config.ensure_dirs()

if not Config.validate():
    log.warning("Config validation failed — some features may not work")
