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

- **License**: See `License.txt`
- **Authorship**: See `Authorization.txt`

Do not distribute or modify without explicit permission from the author.

---

Created with 🧠 by **Devlord the Architect**.
