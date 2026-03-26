# Divine World Architecture

This document describes the high-level architecture and component interactions of the Divine World simulation system.

---

## 🛰️ System Overview

Divine World is a multi-layered system designed to bridge AI reasoning with complex 3D virtual environments (Minecraft).

1.  **Management Server (Python/FastAPI)**: The central controller (`py_backend/main.py`). It manages agent lifecycles, exposes REST/WebSocket APIs, and serves the Control Centre GUI.
2.  **Autonomous Agents (AI Core)**: Individual AI processes that run a perception-thinking-action loop. They use local LLMs (via Ollama) and reinforcement learning policies for deliberation.
3.  **Forge Mods (Java)**:
    - **`DivineWorld`**: Server-side mod for agent registration, god-tier entity management, and event handling.
    - **`DWClientBot`**: Client-side mod that provides the AI with "eyes" (perception data) and "limbs" (simulated input).
4.  **UltimMC Automation**: Automates the creation and launching of dedicated Minecraft instances for each agent.
5.  **Control Centre (React/GUI)**: A real-time web interface for monitoring agent states, editing personalities, and managing memories.

---

## 🔄 Component Interaction

### 1. Agent Lifecycle (The "Packaged" Flow)
1.  **Spawn Request**: A request is made to the Management Server (via GUI or API).
2.  **Initialization**: The server starts the `NPCAgent` process.
3.  **Auto-Packaging**: Once the agent's brain file (`brain.pcap`) is first saved, `AgentPackager` creates a portable executable in `npc_applications/{agent_id}/`.
4.  **Minecraft Setup**: The server uses `UltimMCLauncher` to clone and configure a Minecraft instance inside the agent's application folder.
5.  **Launch**: The agent process uses its bundled UltimMC copy to launch Minecraft and auto-join the game server.

### 2. The Perception-Action Loop
- **Perception (Java → Python)**: The `DWClientBot` mod collects game data (health, position, entities, vision) and sends it as a WebSocket message (JSON or binary) to the AI process.
- **Thinking (Python)**: The AI process deliberation engine (`brain_core.py`) evaluates the data against its personality, memories, and goals.
- **Action (Python → Java)**: The chosen action is sent back to the mod, which simulates the necessary inputs (move, click, keypress).

---

## 🌀 Mental Matrix

The **Mental Matrix** is a 3D simulation environment built into the frontend using Three.js. It allows agents to visualize their thought processes, simulate physics interactions, and test scenarios (e.g., "Will I survive this jump?") before executing them in the game.

---

## 🤖 Agent Registry (`agents.json`)

The **Agent Registry** is a synchronization system that ensures the Python backend and Java mods share a consistent view of all active agents.

- **Backend**: Automatically registers every spawned agent with its name, gender, and type in the registry.
- **Java Mod**: Loads the registry to validate commands, provide autocomplete suggestions, and display agent statistics in-game.

---

## ⚡ God Entities

God entities (e.g., Wither, Warden, Ender Dragon) use a specialized `LLMOracleBrain`. They have access to global world state and "god-tier" abilities (transformation, entity summoning) that standard NPC agents do not.
