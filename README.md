# Divine World

> **Proprietary World Simulation | AI-driven Minecraft Universe**
> Created by Devlord the Architect — All rights reserved

---

## 🌐 About

Divine World is a comprehensive world simulation system featuring AI-driven agents, god-tier entities, and deep integration with Minecraft. It bridges the gap between Large Language Models and complex virtual environments, providing agents with a "Mental Matrix" for reasoning and perception.

## ✨ Key Features

- 🧠 **Autonomous Agents**: Self-driven NPCs with distinct personalities and memory persistence.
- ⚡ **Mental Matrix**: 3D simulation environment for agent reasoning and physics testing.
- 🎮 **Minecraft Integration**: Deep integration via custom Forge mods (`DivineWorld` and `DWClientBot`).
- 🛠️ **UltimMC Automation**: Automated management of Minecraft instances and agent deployment.
- 🌐 **Comprehensive API**: REST and WebSocket endpoints for full system control.
- 📊 **Real-time Dashboard**: React-based frontend for monitoring agent state and telemetry.

## 🚀 Quick Start

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Build Components**:
    ```bash
    chmod +x build_agents.sh
    ./build_agents.sh all
    ```
3.  **Start Backend**:
    ```bash
    cd py_backend
    ./start_backend.sh
    ```
4.  **Run an Agent**:
    ```bash
    ./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft
    ```

For more detailed instructions, see the **[Getting Started](./docs/GETTING_STARTED.md)** guide.

## Curl commands for testing all of the endpoints
- **Health**
```bash
# Basic health
curl http://localhost:11400/health

# Detailed health
curl http://localhost:11400/health/detailed

# Root/docs
curl http://localhost:11400/
```

- **Server Configuration**
```bash
# Get server status
curl http://localhost:11400/api/server/status

# Get configured server info
curl -X POST http://localhost:11400/api/server/configure

# List server agents
curl http://localhost:11400/api/server/agents
```

- **Agent Management**
```bash
# List all agents
curl http://localhost:11400/api/agents/list

# Start agent manually
curl -X POST http://localhost:11400/api/agents/start \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "alice",
    "mode": "minecraft",
    "agent_type": "npc",
    "custom_name": "Alice"
  }'

# Stop agent
curl -X POST http://localhost:11400/api/agents/alice/stop

# Get agent status
curl http://localhost:11400/api/agents/alice/status

# Package agent
curl -X POST http://localhost:11400/api/agents/alice/package

# Cleanup agent (add ?delete_brain=true to also delete brain)
curl -X POST http://localhost:11400/api/agents/alice/cleanup
curl -X POST "http://localhost:11400/api/agents/alice/cleanup?delete_brain=true"

# Clear memories
curl -X POST http://localhost:11400/api/agents/clear_memories \
  -H "Content-Type: application/json" \
  -d '{
    "event": "clear_memories",
    "agent_ids": ["alice", "bob"],
    "exceptions": ["bob"]
  }'
```

- **Minecraft Mod Endpoints**
```bash
# Player connect event
curl -X POST http://localhost:11400/api/player_event \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "AI_alice",
    "player_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "agent_type": "npc",
    "event": "connected"
  }'

# Player disconnect event
curl -X POST http://localhost:11400/api/player_event \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "AI_alice",
    "player_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "agent_type": "npc",
    "event": "disconnected"
  }'

# Spawn single NPC
curl -X POST http://localhost:11400/api/agents/spawn_single \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Alice",
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200},
    "gender": "female"
  }'

# Genesis spawn (Adam & Eve)
curl -X POST http://localhost:11400/api/genesis/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "event": "genesis",
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_count": 2,
    "spawn_positions": [
      {"x": 100, "y": 64, "z": 200, "gender": "male"},
      {"x": 102, "y": 64, "z": 200, "gender": "female"}
    ]
  }'

# Breeding event
curl -X POST http://localhost:11400/api/breeding/event \
  -H "Content-Type: application/json" \
  -d '{
    "event": "breeding",
    "parent_a_id": "adam",
    "parent_b_id": "eve",
    "parent_a_type": "npc",
    "parent_b_type": "npc",
    "timestamp": 1234567890
  }'

# Divine reset
curl -X POST http://localhost:11400/api/divine_reset \
  -H "Content-Type: application/json" \
  -d '{
    "event": "divine_reset",
    "world": "minecraft:overworld",
    "agent_count": 2,
    "agent_ids": ["adam", "eve"]
  }'
```
- **God Endpoints**
```bash
# Spawn god (types: wither, warden, dragon, ender_dragon, oracle, creaking, elder_guardian)
curl -X POST http://localhost:11400/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "event": "spawn_god",
    "god_type": "wither",
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200}
  }'

# God use ability
curl -X POST http://localhost:11400/api/gods/ability \
  -H "Content-Type: application/json" \
  -d '{
    "event": "god_ability",
    "agent_id": "god1",
    "ability": "summon_wither_skulls",
    "parameters": []
  }'

# God transform
curl -X POST http://localhost:11400/api/gods/transform \
  -H "Content-Type: application/json" \
  -d '{
    "event": "god_transform",
    "agent_id": "god1",
    "target_mob": "villager"
  }'
```
Replace localhost:11400 with your actual host/port if different.

## 📂 Documentation

- 📖 **[Documentation Index](./docs/README.md)**: Overview of all documentation.
- 🚀 **[Getting Started](./docs/GETTING_STARTED.md)**: Installation and first steps.
- 🏗️ **[Architecture](./docs/ARCHITECTURE.md)**: System design and component flow.
- 🔌 **[API Reference](./docs/API_REFERENCE.md)**: API documentation.
- 🛠️ **[Development Guide](./docs/DEVELOPMENT.md)**: Building and customization.
- 🚢 **[Deployment](./docs/DEPLOYMENT.md)**: Production setup.

## 🤖 Agent Systems

Learn more about the agent synchronization and management:
- **[Agent Sync System](./docs/agents/SYNC_SYSTEM.md)**
- **[Technical Implementation](./docs/agents/IMPLEMENTATION.md)**

## 📦 Core Components

- **DivineWorld**: Server-side Forge mod for agent registration and God entities.
- **DWClientBot**: Client-side Forge mod for AI perception and action control.
- **dw_agent**: React-based dashboard for monitoring and training agents.
- **py_backend**: FastAPI-powered backend managing the AI core and simulation API.

---

## 🔐 Licensing and Ownership

This project is under the full ownership and copyright of **Devlord the Architect (2025)**. It is **NOT** open source and is **NOT** for redistribution.

- **License**: See **[License.txt](License.txt)**
- **Authorship**: See **[Authorship.txt](Authorship.txt)**

Do not distribute or modify without explicit permission from the author.

---

Created with 🧠 by **Devlord the Architect**.
