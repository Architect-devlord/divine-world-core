# build_agent.spec - PyInstaller specification for standalone agents
"""
PyInstaller spec file for building standalone Divine World agents.

Usage:
    pyinstaller build_agent.spec
    
Or for specific agent:
    pyinstaller build_agent.spec --name DW_Agent_alice
"""

import sys
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
PY_BACKEND = BASE_DIR / "py_backend"
AI_CORE = PY_BACKEND / "ai_core"

# Hidden imports for PyInstaller
HIDDEN_IMPORTS = [
    # Core AI
    'ai_core',
    'ai_core.agent',
    'ai_core.agent_standalone',
    'ai_core.personality',
    'ai_core.emotion',
    'ai_core.brain_core',
    'ai_core.brain_language',
    'ai_core.brain_capsule',
    'ai_core.brain_integration',
    'ai_core.memory',
    'ai_core.unified_memory',
    'ai_core.reward_system',
    'ai_core.planner',
    'ai_core.cognitive_loop',
    'ai_core.actuators',
    'ai_core.vision',
    'ai_core.audio_processors',
    'ai_core.config_loader',
    'ai_core.config_manager',
    'ai_core.logger_setup',
    
    # Configuration
    'ai_core.config',
    'ai_core.communication_protocol',
    'ai_core.validation',
    
    # External packages
    'torch',
    'torch.nn',
    'torch.optim',
    'numpy',
    'fastapi',
    'fastapi.middleware',
    'uvicorn',
    'uvicorn.config',
    'websockets',
    'aiohttp',
    'msgpack',
]

# Data files to include
DATAS = [
    # Include AI core module
    (str(AI_CORE), 'ai_core'),
]

# Analysis
a = Analysis(
    [str(AI_CORE / 'agent.py')],
    pathex=[str(PY_BACKEND), str(BASE_DIR)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[
        'matplotlib',
        'pandas',
        'scipy',
        'sklearn',
        'django',
        'flask',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# PYZ
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# EXE
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DW_Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Collection (optional, for --onedir mode)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DW_Agent',
)

