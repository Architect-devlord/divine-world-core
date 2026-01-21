# Agent Spawning & Minecraft Integration Guide

## Overview

When you spawn agents via `/api/genesis/spawn`, the Divine World Backend creates AI agents that can control Minecraft bodies and interact with the server. Here's the complete flow:

---

## 1. Genesis Spawn Flow

### Request
```bash
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

### What Happens

1. **Agent Creation** (`spawn_npc` in `AgentSpawner`)
   - Two agents named "adam" and "eve" are created
   - Each agent gets unique personality traits, gender, and memory
   - Brain capsule is serialized to `npc_applications/data/brains/<agent_id>/brain.pcap`

2. **Minecraft Client Launch** (`spawn_client` in `AgentClientManager`)
   - Java process is spawned with system properties:
     ```
     -Ddw.agentId=adam
     -Ddw.server=127.0.0.1:25565
     -Ddw.backend=http://127.0.0.1:11400
     ```
   - This launches the **DWClientBot** mod (embedded in the Forge/Fabric client)
   - The mod reads these system properties and configures itself

3. **DWClientBot Mod Initialization**
   - DWClientBot connects to the backend using `-Ddw.backend`
   - DWClientBot gets the agent ID from `-Ddw.agentId`
   - DWClientBot is configured to join the server at `-Ddw.server`

4. **Agent Joins Server**
   - DWClientBot (running as a Minecraft client mod) joins the server
   - The mod creates a player entity for the agent in Minecraft
   - The agent's AI brain controls the player's actions in-game

5. **Auto-Packaging** (Background)
   - AutoPackagingSystem detects the new brain file
   - Packager creates a standalone `.exe` with:
     - Brain capsule
     - DivineWorld mod jar
     - DWClientBot mod jar
     - React frontend
   - Packaged executable placed in `npc_applications/<agent_id>_portable/`

---

## 2. Agent-Server Communication

### Backend ↔ DWClientBot Mod

The DWClientBot mod communicates with the backend via HTTP/WebSocket:

```
Agent ID: adam
Backend URL: http://127.0.0.1:11400

Perception Flow:
  Minecraft Client (DWClientBot) 
    → Reads game state (position, health, hunger, vision)
    → Sends to Backend REST API
  
  Backend (Python AI)
    → NPCAgent processes perception
    → Brain generates action (move, place block, attack, etc.)
    → Returns action via API
  
  Minecraft Client (DWClientBot)
    → Executes action in game
    → Player performs movement/action in Minecraft world
```

### System Properties Used

| Property | Value | Purpose |
|----------|-------|---------|
| `dw.agentId` | `adam` or `eve` | Identifies the agent to the backend |
| `dw.server` | `127.0.0.1:25565` | Minecraft server address to join |
| `dw.backend` | `http://127.0.0.1:11400` | Backend API URL for perception/action |

---

## 3. For Packaged Agent Executables

When you run a packaged agent `.exe`:

1. **Launcher Starts Backend**
   - The launcher is a Python script compiled to `.exe` via PyInstaller
   - It starts the FastAPI backend on the configured port
   - Loads the agent's brain from `brain.pcap`

2. **User Manually Launches Minecraft**
   - Copy `mods/` folder to your Minecraft installation
   - Install Forge/Fabric (if required)
   - Create a Minecraft profile
   - Join the server manually with username matching the agent ID

3. **Manual Server Connection**
   - When you launch Minecraft and join the server, the DWClientBot mod activates
   - The mod reads the agent's backend URL from the launcher's output
   - The mod connects to the backend and starts sending perception data
   - The AI brain controls the player from that point forward

**Note**: Packaged executables require user intervention to launch Minecraft. For full automation, use the `/api/genesis/spawn` endpoint which launches both the backend AND the Minecraft client automatically.

---

## 4. Complete Spawning Workflow (Diagram)

```
┌─────────────────────────────────────────────────────────────────┐
│ POST /api/genesis/spawn                                         │
│ (Backend starts processing)                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │ Create Agent "adam"  │
                │ Create Agent "eve"   │
                └──────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
      ┌────────────────┐      ┌────────────────┐
      │ Save adam's    │      │ Save eve's     │
      │ brain to disk  │      │ brain to disk  │
      └────────────────┘      └────────────────┘
                │                       │
        ┌───────┴───────────────────────┴────────┐
        ▼                                         ▼
  ┌─────────────────────┐          ┌─────────────────────┐
  │ Launch Java Client  │          │ Launch Java Client  │
  │ with props:         │          │ with props:         │
  │ dw.agentId=adam     │          │ dw.agentId=eve      │
  │ dw.server=...       │          │ dw.server=...       │
  │ dw.backend=...      │          │ dw.backend=...      │
  └─────────────────────┘          └─────────────────────┘
        │                                   │
        ▼                                   ▼
  ┌─────────────────────┐          ┌─────────────────────┐
  │ DWClientBot Mod     │          │ DWClientBot Mod     │
  │ Connects to Server  │          │ Connects to Server  │
  │ Joins as "adam"     │          │ Joins as "eve"      │
  └─────────────────────┘          └─────────────────────┘
        │                                   │
        ▼                                   ▼
  ┌─────────────────────┐          ┌─────────────────────┐
  │ Agent Perception    │          │ Agent Perception    │
  │ ↓ Backend API ↓     │          │ ↓ Backend API ↓     │
  │ Brain Decides       │          │ Brain Decides       │
  │ ↓ Backend API ↓     │          │ ↓ Backend API ↓     │
  │ DWClientBot Acts    │          │ DWClientBot Acts    │
  └─────────────────────┘          └─────────────────────┘
        │                                   │
        ▼                                   ▼
  ┌─────────────────────────────────────────────────────┐
  │ Both agents playing in Minecraft, controlled by AI! │
  └─────────────────────────────────────────────────────┘
```

---

## 5. Key Files & Directories

```
npc_applications/
├── adam/                          # Intermediate build directory
│   ├── brain.pcap                 # Agent brain state
│   ├── config.json                # Agent configuration
│   ├── launcher.py                # Generated launcher script
│   ├── mods/                      # Included mods
│   │   ├── divineworld-1.0.0.jar  # DivineWorld server mod
│   │   └── DWClientBot.jar        # DWClientBot client mod
│   └── frontend/                  # React frontend (if built)
│
├── adam_portable/                 # Final packaged agent
│   ├── DW_Agent_adam.exe          # Standalone executable
│   ├── brain.pcap                 # Agent brain
│   ├── config.json                # Configuration
│   ├── mods/                      # Mods for user to copy
│   │   ├── divineworld-1.0.0.jar
│   │   └── DWClientBot.jar
│   ├── frontend/                  # Frontend assets
│   └── README.md                  # Instructions for user
│
├── eve/                           # Same structure for eve
├── eve_portable/
│
└── package_registry.json          # Metadata for all packages
```

---

## 6. Configuration

### Backend Configuration (`config.py`)

```python
DEFAULT_SERVER = "127.0.0.1:25565"        # Server to join
BASE_BACKEND_PORT = 11400                 # Backend port
CLIENT_JAR = Path(".../DWClientBot.jar")  # DWClientBot mod jar
```

### Per-Agent Configuration (`config.json`)

```json
{
  "agent_id": "adam",
  "agent_type": "npc",
  "gender": "male",
  "default_server": "127.0.0.1:25565",
  "backend_port": 11400,
  "frontend_port": 11401,
  "modes": {
    "chat": true,
    "controller": true,
    "headless": true
  }
}
```

---

## 7. Troubleshooting

### Agent Spawned But Not In Server

1. **Check Java Process**: Verify that the Java client was launched
   ```bash
   ps aux | grep java
   # Look for process with -Ddw.agentId
   ```

2. **Check Server Logs**: Look for connection attempts
   - Minecraft server logs should show player join event
   - DivineWorld mod logs should show agent initialization

3. **Check Backend Logs**: Verify perception/action flow
   ```bash
   # Backend should log WebSocket connections from DWClientBot
   [Client:adam] Successfully connected
   [Perception] Received frame from adam
   [Action] Sent move_forward=true to adam
   ```

4. **Verify Mods Are Installed**
   - DivineWorld.jar in `~/.minecraft/mods/`
   - DWClientBot.jar in `~/.minecraft/mods/`
   - Forge/Fabric installed and loaded

### Backend Not Responding

1. Check if backend is running:
   ```bash
   curl http://127.0.0.1:11400/health
   ```

2. Check if port is already in use:
   ```bash
   lsof -i :11400
   ```

3. Review backend logs for errors

### DWClientBot Mod Not Activating

1. **Missing System Properties**: Java must be launched with:
   - `-Ddw.agentId=<agent_name>`
   - `-Ddw.server=<server_address>`
   - `-Ddw.backend=<backend_url>`

2. **Mod Not In Mods Folder**: Copy DWClientBot.jar to:
   - Windows: `%APPDATA%/.minecraft/mods/DWClientBot.jar`
   - Linux: `~/.minecraft/mods/DWClientBot.jar`

3. **Wrong Minecraft Version**: Ensure mods match Minecraft version (e.g., 1.20.1)

---

## 8. Summary

| Step | Component | Action |
|------|-----------|--------|
| 1 | Frontend/User | POST `/api/genesis/spawn` |
| 2 | Backend | Create agents + save brains |
| 3 | Backend | Launch Java clients with mod |
| 4 | DWClientBot Mod | Connect to server as player |
| 5 | DWClientBot Mod | Send perception to backend |
| 6 | AI Brain | Process perception + decide action |
| 7 | DWClientBot Mod | Execute action in Minecraft |
| 8 | Repeats | Loop steps 5-7 continuously |

The entire cycle happens in real-time (multiple times per second) allowing the AI agents to interact fluidly with the Minecraft world and other players!

---

## Quick Start

### Option A: Using `/api/genesis/spawn` (Recommended)

```bash
# Make sure Minecraft server is running at 127.0.0.1:25565
# Backend is running at http://127.0.0.1:11400

# Spawn agents (automatically launches clients and joins server)
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"

# Agents "adam" and "eve" should now be in the server!
```

### Option B: Using Packaged Executables

```bash
# 1. Start the packaged agent launcher
./npc_applications/adam_portable/DW_Agent_adam.exe

# 2. Copy mods to Minecraft
cp npc_applications/adam_portable/mods/* ~/.minecraft/mods/

# 3. Launch Minecraft manually and join the server
# Use username: adam

# 4. Backend will detect the connection and start controlling the player
```

---

**For questions or issues, check the server logs and backend logs for detailed error messages.**
