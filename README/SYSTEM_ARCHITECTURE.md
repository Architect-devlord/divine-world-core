# System Architecture: Automated Agent Spawning with UltimMC

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DIVINE WORLD BACKEND                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  REST API Layer (main.py)                                                   │
│  ├─ POST /api/genesis/spawn  ──► Triggers agent spawning                    │
│  ├─ GET /agents              ──► List active agents                         │
│  └─ WebSocket /ws/agent/{id} ──► Real-time perception/action flow          │
│                                                                              │
│                                  ↓                                           │
│                                                                              │
│  Agent Management Layer (auto_packager.py)                                  │
│  ├─ EnhancedAgentSpawner                                                    │
│  │  ├─ Decides: Use UltimMC or legacy launch?                              │
│  │  ├─ Spawns agent + packages it                                          │
│  │  └─ Queues for auto-packaging                                           │
│  │                                                                           │
│  └─ AutoPackagingSystem                                                     │
│     ├─ Background worker thread                                             │
│     ├─ Monitors brain files                                                │
│     └─ Packages agents for standalone use                                  │
│                                                                              │
│                                  ↓                                           │
│                                                                              │
│  Spawning Engine (agent_spawner.py)                                         │
│  ├─ AgentSpawner (Base)                                                     │
│  │  ├─ spawn_npc(agent_id, traits, server, memory)                         │
│  │  ├─ spawn_god(god_type, server, traits)                                 │
│  │  └─ Manages agent lifecycle                                             │
│  │                                                                           │
│  ├─ EnhancedAgentSpawner (with UltimMC)                                     │
│  │  ├─ Detects UltimMC availability                                        │
│  │  ├─ spawn_npc_with_ultimmc(...) ─────┐                                  │
│  │  └─ Fallback to legacy if needed      │                                  │
│  │                                       ↓                                   │
│  ├─ AgentClientManager                  ↓                                   │
│  │  ├─ spawn_client() ─────────────────►                                    │
│  │  ├─ allocate_port()                 UltimMCLauncher                     │
│  │  └─ Monitor/log client output        ├─ setup_agent_instance()          │
│  │                                      │  ├─ create_account()             │
│  │                                      │  ├─ create_instance()            │
│  │                                      │  ├─ install_forge()              │
│  │                                      │  └─ install_mods()               │
│  │                                      │                                   │
│  │                                      └─ launch_agent()                   │
│  │                                         └─ Launch Java + system props    │
│  │                                                     ↓                     │
│  └─ NPCAgent (The Agent)                           Minecraft Client        │
│     ├─ agent_id: unique identifier                (UltimMC Instance)       │
│     ├─ client_process: Java subprocess                                      │
│     ├─ brain_capsule: AI decision maker           ~/.ultimmc/instances/    │
│     ├─ perception: game state                     agent_adam/               │
│     └─ actions: movement/interaction              ├─ mods/                 │
│                                                   │  ├─ DWClientBot.jar     │
│                                                   │  └─ DivineWorld.jar     │
│                                                   └─ instance.cfg           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

                                      ↓

┌─────────────────────────────────────────────────────────────────────────────┐
│                         MINECRAFT CLIENT (Java)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  System Properties (from Java command line)                                 │
│  ├─ -Ddw.agentId=adam                                                       │
│  ├─ -Ddw.server=127.0.0.1:25565                                             │
│  └─ -Ddw.backend=http://127.0.0.1:11400                                     │
│                      ↓                                                       │
│  Forge Mod Loader                                                            │
│  ├─ Loads DWClientBot.jar                                                   │
│  ├─ Loads DivineWorld.jar                                                   │
│  └─ Initializes mods                                                        │
│                      ↓                                                       │
│  DWClientBot Mod (The Bridge)                                               │
│  ├─ Reads system properties                                                │
│  ├─ Connects to backend API: http://127.0.0.1:11400                        │
│  ├─ Joins server: 127.0.0.1:25565                                          │
│  ├─ Perception Loop:                                                        │
│  │  └─ GET /agents/{id}/perception ──► Get game state                       │
│  │                                                                           │
│  └─ Action Loop:                                                            │
│     └─ POST /agents/{id}/action ──► Execute movement/interaction           │
│                                                                              │
│  Minecraft Server                                                            │
│  ├─ Player "adam" spawned                                                   │
│  ├─ DivineWorld mod enables agent registration                              │
│  └─ Agent participates in world                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

                                      ↔ HTTP/WebSocket

                    Backend ←→ DWClientBot ←→ Minecraft Server
```

---

## Component Interaction Sequence

### 1. Agent Spawn Sequence

```
Client                Backend              UltimMC              Minecraft
  │                    │                    │                      │
  ├─ POST /genesis/──► │                    │                      │
  │  spawn            │                    │                      │
  │                   ├─ spawn_npc()       │                      │
  │                   │                    │                      │
  │                   ├─ setup_agent ─────► │                      │
  │                   │  instance            ├─ create_account()    │
  │                   │                      ├─ create_instance()   │
  │                   │                      ├─ install_forge()     │
  │                   │                      └─ install_mods()      │
  │                   │                    │                      │
  │                   ├─ launch_agent ────► │                      │
  │                   │                      ├─ spawn() ──────────► │
  │                   │                      │                  launches
  │                   │                      │                      │
  │                   │◄──── process ──────┤                      │
  │                   │   handle             │                      │
  │                   │                      │                      │
  │                   ├─ queue_package      │                      │
  │                   │                      │                      │
  │ 200 OK ◄──────────┤                      │                      │
  │ {agents: [adam]}  │                      │                      │
  │                   │                      │                      │
  
     [30-60 seconds pass]
  
  │                   │                      │                    ┌─────┐
  │                   │                      │                    │Agent│
  │                   │                      │◄──── DWClientBot ──┤Join?│
  │                   │◄──── perception ─────┤◄─── Server Join ───└─────┘
  │                   │                      │                      │
  └─ Ready!           │                      │                      │
                      │                      │                      │
```

### 2. Perception & Action Loop

```
Backend                 DWClientBot Mod         Minecraft Client
  │                          │                         │
  ├─ Wait for perception      │                         │
  │                           │                         │
  │◄── send_perception() ──── ├─ Read game state ──────┤
  │   (position, health,      │   (keyboard input,      │ (User/AI
  │    inventory, etc.)       │    camera, blocks, etc) │  controls)
  │                           │                         │
  ├─ AI Brain decides action  │                         │
  │   (move_forward,          │                         │
  │    place_block, etc.)     │                         │
  │                           │                         │
  ├─ send_action() ──────────► ├─ Execute action ──────┤
  │   (action_type,           │   (keyboard press,      │ (Movement,
  │    duration, target)      │    right-click, etc.)   │  interaction)
  │                           │                         │
  │                           │                         │
  │◄─────── repeat ───────────┼────────── repeat ──────┤
  │                           │                         │
  │  [Loop: 20-30 times/sec]  │                         │
```

### 3. UltimMC Automation Sequence

```
User                UltimMC                File System             Java
  │                   │                       │                     │
  │                   │                       │                     │
  ├─ ultimmc -i ────► │                       │                     │
  │ agent_adam        │                       │                     │
  │ -a adam           ├─ Read config          │                     │
  │                   │                       │                     │
  │                   ├─ Find Java ──────────► ~/.ultimmc/           │
  │                   │                       └─ instances/          │
  │                   │                          agent_adam/         │
  │                   │                          ├─ mods/            │
  │                   │                          │  ├─ DWClientBot   │
  │                   │                          │  └─ DivineWorld   │
  │                   │                          └─ instance.cfg     │
  │                   │                       │                     │
  │                   ├─ Prepare Java cmd     │                     │
  │                   │  -Xmx2048M                                   │
  │                   │  -Ddw.agentId=adam                           │
  │                   │  -Ddw.server=...                             │
  │                   │  -Ddw.backend=...                            │
  │                   │                       │                     │
  │                   ├──────────────────────────────────────────────► spawn()
  │                   │                       │                     │
  │                   │                       │                  ┌──┴──┐
  │                   │                       │                  │Forge│
  │                   │                       │                  │Loads│
  │                   │                       │                  │Mods │
  │                   │                       │                  └──┬──┘
  │                   │                       │                     │
  │                   │                       │                     ├─ DWClientBot
  │                   │                       │                     │  reads props
  │                   │                       │                     │
  │                   │◄───── stdout/stderr ──┼─────────────────────┤
  │                   │   (logging)           │                     │
  │                   │                       │                     │
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent Spawning Flow                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Config                                                                  │
│  ├─ DW_USE_ULTIMMC (true/false)                                          │
│  ├─ DW_MINECRAFT_VERSION (1.20.1)                                        │
│  ├─ DW_FORGE_VERSION (47.3.0)                                            │
│  ├─ DW_SERVER (127.0.0.1:25565)                                          │
│  ├─ DW_CLIENT_MEMORY (2048)                                              │
│  ├─ DW_CLIENT_JAR (path to DWClientBot.jar)                              │
│  └─ DW_MOD_JAR (path to DivineWorld.jar)                                 │
│        │                                                                  │
│        ▼                                                                  │
│  EnhancedAgentSpawner.spawn_npc()                                        │
│        │                                                                  │
│        ├─ Check: USE_ULTIMMC enabled?                                    │
│        │   ├─ YES ──► UltimMCLauncher.setup_agent_instance()              │
│        │   │         (create account, instance, mods)                     │
│        │   │                                                              │
│        │   │         UltimMCLauncher.launch_agent()                       │
│        │   │         (launch Java with system properties)                 │
│        │   │                                                              │
│        │   └─ NO ───► AgentClientManager.spawn_client()                  │
│        │             (legacy Java launch)                                 │
│        │                                                                  │
│        ├─ Create NPCAgent object                                          │
│        │  ├─ agent_id (from parameter)                                    │
│        │  ├─ gender (auto-assigned or parameter)                          │
│        │  ├─ persona_traits (randomly generated or parameter)             │
│        │  ├─ client_process (MinecraftClientProcess)                      │
│        │  └─ brain_capsule (AI decision maker)                            │
│        │                                                                  │
│        ├─ Save brain to disk                                              │
│        │  └─ Config.BRAINS_DIR / agent_id / brain.pcap                   │
│        │                                                                  │
│        └─ Queue for auto-packaging                                        │
│           └─ AutoPackagingSystem.queue_agent_for_packaging()              │
│              ├─ Wait for brain file stability                             │
│              ├─ Call packager.package_agent()                             │
│              └─ Save to NPC_APPLICATIONS_DIR / {agent_id}_portable/       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      Minecraft Client Launch Flow                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  System Properties (from EnhancedAgentSpawner)                           │
│  ├─ -Ddw.agentId=adam                                                    │
│  ├─ -Ddw.server=127.0.0.1:25565                                          │
│  └─ -Ddw.backend=http://127.0.0.1:11400                                  │
│        │                                                                  │
│        ▼                                                                  │
│  UltimMCLauncher.launch_agent()                                          │
│        │                                                                  │
│        ├─ Build Java command:                                             │
│        │  java -Xmx2048M -Xms2048M \                                      │
│        │   -Ddw.agentId=adam \                                            │
│        │   -Ddw.server=127.0.0.1:25565 \                                  │
│        │   -Ddw.backend=http://127.0.0.1:11400 \                          │
│        │   -jar ~/.ultimmc/instances/agent_adam/minecraft.jar             │
│        │                                                                  │
│        ├─ subprocess.Popen(cmd) ──► Process handle                        │
│        │                                                                  │
│        └─ Monitor stdout/stderr ──► Log to backend logger                │
│              (connected to tail -f)                                       │
│                                                                          │
│  Process Environment:                                                    │
│  ├─ JAVA_HOME (auto-detected)                                            │
│  ├─ Classpath (Forge libraries)                                          │
│  └─ Working directory (~/.ultimmc/instances/agent_adam/)                 │
│                                                                          │
│  Minecraft Startup (inside Java):                                        │
│  ├─ Forge mod loader reads system properties                             │
│  ├─ Loads mods:                                                          │
│  │  ├─ DWClientBot.jar reads -Ddw.* properties                           │
│  │  │  ├─ dw.agentId ──► agent_id = "adam"                              │
│  │  │  ├─ dw.server ───► server_addr = "127.0.0.1:25565"                │
│  │  │  └─ dw.backend ──► backend_url = "http://127.0.0.1:11400"         │
│  │  │                                                                    │
│  │  │  └─ Initialize HTTP client to backend                             │
│  │  │     (register connection)                                         │
│  │  │                                                                    │
│  │  └─ DivineWorld.jar loads server-side mod                             │
│  │     (enables agent registration on server)                           │
│  │                                                                       │
│  ├─ Main game loop starts                                                 │
│  ├─ Minecraft client connects to server                                   │
│  └─ Player "adam" spawns on server                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    Perception & Action Loop                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Backend (Python)              ←→              Minecraft Client (Java)   │
│  ├─ NPCAgent                        DWClientBot Mod (Java)              │
│  │  ├─ brain_capsule (AI)          ├─ Reads game state                  │
│  │  ├─ perceive(frame)             │  ├─ Position (XYZ)                │
│  │  ├─ decide(perception)          │  ├─ Health (0-20)                 │
│  │  └─ execute(action)             │  ├─ Hunger (0-20)                 │
│  │                                  │  ├─ Vision (blocks ahead)         │
│  ├─ HTTP Client                     │  ├─ Inventory                     │
│  │  ├─ GET /agents/{id}/            │  └─ Entity list (mobs, players)   │
│  │  │   perception                  │                                   │
│  │  │   ◄────────────────────────────── POST /agents/adam/perception    │
│  │  │                                │  (frame data as JSON)             │
│  │  │                                │                                   │
│  │  ├─ [Process perception]          │                                   │
│  │  │  └─ AI brain generates action  │                                   │
│  │  │     (move_forward, attack, etc)│                                   │
│  │  │                                │                                   │
│  │  ├─ POST /agents/{id}/action      │                                   │
│  │  │   ────────────────────────────► GET /agents/{id}/action            │
│  │  │   (action_type, duration)      │  ◄────────────────────           │
│  │  │                                │                                   │
│  │  │                                ├─ [Execute action]                │
│  │  │                                │  ├─ Keyboard input               │
│  │  │                                │  ├─ Mouse movement               │
│  │  │                                │  └─ Right-click                  │
│  │  │                                │                                   │
│  │  └─ [Wait, then repeat]           │                                   │
│  │     (30-60 times per second)      │                                   │
│  │                                   │                                   │
│  └─ WebSocket updates (optional)     └─ World state updated              │
│     └─ Broadcast to frontend            └─ Player moves, interacts       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Class Hierarchy

```
                    Agent Spawner Hierarchy
                              
                              ┌──────────────────┐
                              │  AgentSpawner    │
                              │  (Base)          │
                              └────────┬─────────┘
                                       │
                      ┌────────────────┴────────────────┐
                      │                                 │
                      ▼                                 ▼
        ┌──────────────────────────────┐  ┌──────────────────────────────┐
        │ EnhancedAgentSpawner         │  │ EnhancedAgentSpawner         │
        │ (in agent_spawner.py)        │  │ (in auto_packager.py)        │
        │                              │  │                              │
        │ Adds:                        │  │ Adds:                        │
        │ - UltimMC support           │  │ - Auto-packaging             │
        │ - spawn_npc_with_ultimmc()  │  │ - AutoPackagingSystem        │
        │ - Graceful fallback         │  │ - Metadata tracking          │
        └──────────────┬───────────────┘  └──────────────┬───────────────┘
                       │                                 │
                       └─────────────┬───────────────────┘
                                     │
                        ┌────────────▼───────────┐
                        │  Used by main.py via   │
                        │  EnhancedAgentManager  │
                        │                        │
                        │  - Spawner handles     │
                        │    UltimMC setup       │
                        │  - Auto-packager       │
                        │    handles packaging   │
                        │  - No changes to main  │
                        └────────────────────────┘


                      Support Classes
                              
        ┌──────────────────┐      ┌─────────────────────┐
        │ UltimMCLauncher  │      │ AgentClientManager  │
        │ (minecraft_launcher)  │      │ (agent_spawner.py)  │
        │  .py)            │      │                     │
        │                  │      │ Manages:            │
        │ Manages:         │      │ - Java processes    │
        │ - Accounts       │      │ - Port allocation   │
        │ - Instances      │      │ - Client logging    │
        │ - Mods           │      │ - Chat-only mode    │
        │ - Minecraft      │      └─────────────────────┘
        │   launch         │
        └──────────────────┘      ┌─────────────────────┐
                                  │ MinecraftClientProc │
                                  │ (agent_spawner.py)  │
                                  │                     │
                                  │ Represents:         │
                                  │ - Java subprocess   │
                                  │ - Port allocation   │
                                  │ - Uptime tracking   │
                                  └─────────────────────┘
```

---

## Configuration Flow

```
Environment Variables
├─ DW_USE_ULTIMMC
├─ DW_ULTIMMC_PATH
├─ DW_MINECRAFT_VERSION
├─ DW_FORGE_VERSION
├─ DW_SERVER
├─ DW_CLIENT_MEMORY
├─ DW_CLIENT_JAR
└─ DW_MOD_JAR
        │
        ▼
Config.py (config.py)
├─ Reads environment variables
├─ Provides defaults
├─ Auto-detects jar paths
├─ Validates configuration
└─ Exposes as class attributes
        │
        ▼
EnhancedAgentSpawner.__init__()
├─ Reads Config.USE_ULTIMMC
├─ Reads Config.CLIENT_JAR
├─ Creates UltimMCLauncher if enabled
└─ Falls back if UltimMC unavailable
        │
        ▼
spawn_npc()
├─ Checks use_ultimmc flag
├─ Routes to spawn_npc_with_ultimmc() if enabled
├─ Falls back to super().spawn_npc() if disabled
└─ Queues for auto-packaging
```

---

## File Dependencies

```
minecraft_launcher.py
├─ No dependencies on other DW modules
├─ Only uses: subprocess, json, pathlib, logging
└─ Can be used standalone if needed

agent_spawner.py
├─ Imports: minecraft_launcher (UltimMCLauncher)
├─ Uses: config, personality
└─ Extends: existing AgentSpawner, AgentClientManager

auto_packager.py
├─ Imports: agent_spawner (EnhancedAgentSpawner)
├─ Uses: config, packager
└─ Manages: AutoPackagingSystem + Enhanced spawner

config.py
├─ No new dependencies
├─ Adds: UltimMC-specific paths and settings
└─ Used by: agent_spawner, main

main.py
├─ No changes required
├─ Already imports: EnhancedAgentSpawner from auto_packager
└─ Automatically uses UltimMC when available
```

---

## Summary

**Total Components Added/Modified:**
- ✅ 1 merged module (minecraft_launcher.py now unified)
- ✅ 1 new class in agent_spawner.py (EnhancedAgentSpawner)
- ✅ 1 enhanced class in auto_packager.py (EnhancedAgentSpawner)
- ✅ Configuration extensions in config.py
- ✅ 3 new documentation files

**Integration Points:**
- ✅ Seamless with existing main.py
- ✅ Graceful fallback if UltimMC unavailable
- ✅ No breaking changes to existing code
- ✅ Backwards compatible with all existing features

**Result:**
One API call spawns agents that automatically:
1. Get Minecraft accounts
2. Get Minecraft instances
3. Get Forge + mods installed
4. Launch Minecraft clients
5. Connect to backend
6. Join server
7. Start playing under AI control

All in 30-60 seconds per agent! 🎮
