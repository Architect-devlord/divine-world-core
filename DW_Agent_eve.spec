# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/home/devlord/divine-world-core/npc_applications/eve/launcher.py'],
    pathex=['/home/devlord/divine-world-core', '/home/devlord/divine-world-core/py_backend/ai_core', '/home/devlord/divine-world-core/py_backend'],
    binaries=[],
    datas=[('/home/devlord/divine-world-core/npc_applications/eve/brain.pcap', '.'), ('/home/devlord/divine-world-core/npc_applications/eve/config.json', '.'), ('/home/devlord/divine-world-core/npc_applications/eve/brain.pcap.json', '.'), ('/home/devlord/divine-world-core/npc_applications/eve/frontend', 'frontend'), ('/home/devlord/divine-world-core/py_backend', 'py_backend'), ('/home/devlord/divine-world-core/py_backend/ai_core', 'ai_core')],
    hiddenimports=['uvicorn', 'fastapi', 'websockets', 'numpy', 'torch', 'pydantic', 'uvicorn', 'fastapi', 'websockets', 'numpy', 'torch', 'ai_core', 'ai_core.agent', 'ai_core.brain_core', 'ai_core.brain_language', 'ai_core.brain_capsule', 'ai_core.personality', 'ai_core.emotion', 'ai_core.memory', 'ai_core.reward_system', 'ai_core.planner', 'ai_core.actuators', 'ai_core.vision', 'py_backend', 'py_backend.main'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DW_Agent_eve',
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
