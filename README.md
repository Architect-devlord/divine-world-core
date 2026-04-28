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
- 🛠️ **Automated Management**: Automated management of Minecraft instances and agent deployment via UltimMC.
- 🌐 **Comprehensive API**: REST and WebSocket endpoints for full system control.
- 📊 **Real-time Dashboard**: Integrated GUI for monitoring agent state, editing personalities, and managing memories.

## 🚀 Quick Start

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Start the Management Server**:
    ```bash
    # For CLI mode
    python py_backend/main.py --cli

    # For GUI mode (opens browser automatically)
    python py_backend/main.py --gui
    ```
3.  **Spawn Agents**:
    Use the GUI at `http://localhost:11400/gui` to spawn your first NPC or God entity.

For more detailed instructions, see the **[Getting Started](./docs/GETTING_STARTED.md)** guide.

## API Endpoints for testing
- **Health & Status**
```bash
# Basic health
curl http://localhost:11400/health

# Detailed health
curl http://localhost:11400/health/detailed

# Get server status
curl http://localhost:11400/api/server/status
```

- **Agent Management**
```bash
# List all agents (running and available brains)
curl http://localhost:11400/api/agents/list

# Spawn an NPC
curl -X POST http://localhost:11400/api/agents/spawn_single \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Alice",
    "mode": "minecraft"
  }'

# Stop an agent
curl -X POST http://localhost:11400/api/agents/alice_1/stop
```

- **God Entities**
```bash
# Spawn a God (types: wither, warden, ender_dragon, oracle, etc.)
curl -X POST http://localhost:11400/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "god_type": "oracle",
    "custom_name": "TheOracle"
  }'
```

Replace `localhost:11400` with your actual host/port if different.

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
- **py_backend**: FastAPI-powered management server and AI core.
- **dw_agent**: React-based frontend (dashboard) for monitoring agents.

---

## 🔐 Licensing and Ownership

This project is under the full ownership and copyright of **Devlord the Architect (2025)**. It is **NOT** open source and is **NOT** for redistribution.

- **License**: See **[License.txt](License.txt)**
- **Authorization**: See **[Authorization.txt](Authorization.txt)**

Do not distribute or modify without explicit permission from the author.

---

Created with 🧠 by **Devlord the Architect**.
