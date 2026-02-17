# Getting Started with Divine World

Welcome to Divine World, a proprietary world simulation and AI-driven Minecraft universe. This guide will help you get the system up and running.

## Prerequisites

### System Requirements
- **OS**: Linux, macOS, or Windows (with WSL2)
- **Python**: 3.9+ (3.13 recommended)
- **RAM**: 8GB minimum (16GB recommended for multiple agents)
- **Disk Space**: 10GB+ (includes Minecraft, agents, and AI models)
- **Java**: Default JRE (for Minecraft)

### Required Software
1. **Ollama**: Install Ollama and download a lightweight model (e.g., `phi3:mini`, `mistral`, or `llama3`). `phi3:mini` is the default.
2. **Minecraft Launcher (UltimMC)**: Download from [UltimMC Releases](https://github.com/UltimMC/Launcher/releases).
3. **Forge**: Minecraft 1.20.1 with Forge version 47.4.10.

---

## Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd divine-world-core
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup UltimMC
Agents use UltimMC to manage Minecraft instances automatically.
- Place UltimMC in `~/UltimMC/` or `~/.ultimmc/`.
- Launch UltimMC once to create a 1.20.1 instance with Forge.
- Close UltimMC (the agents will manage it).

---

## Building Agents

Before running, you need to build the agent executables and mods.

```bash
chmod +x build_agents.sh
./build_agents.sh all
```

This creates executables in `build/agents/dist/` and compiles the necessary Forge mods.

---

## Quick Start

### 1. Start the Backend
Ensure the Ollama daemon is running, then start the Divine World backend:

```bash
cd py_backend
./start_backend.sh
```

The backend runs on `http://localhost:11400`.

### 2. Run an Agent
You can run an agent with or without Minecraft integration.

**With Minecraft:**
```bash
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft
```

**Without Minecraft (Chat only):**
```bash
./build/agents/dist/DW_Agent_alice --agent-id alice
```

### 3. Access the Web UI
Open your browser to `http://localhost:8001` (default port for the first agent) to monitor the agent's mental state and control its actions.

---

## Common Commands

- **Spawn Agents via API:**
  ```bash
  curl -X POST http://localhost:11400/api/genesis/spawn
  ```
- **List Active Agents:**
  ```bash
  curl http://localhost:11400/api/divineworld/list_agents
  ```
- **Stop All Agents:**
  ```bash
  pkill -f "DW_Agent_"
  ```

For more detailed information, see the [Architecture](./ARCHITECTURE.md), [API Reference](./API_REFERENCE.md), and [Agent Deployment](./agents/DEPLOYMENT.md).
