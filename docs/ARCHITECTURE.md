# Divine World Architecture

This document describes the high-level architecture and component interactions of the Divine World simulation system.

## System Overview

Divine World consists of several layers working together to create an AI-driven Minecraft universe.

1.  **Backend (Python/FastAPI)**: Manages agent lifecycles, AI reasoning, and provides a REST/WebSocket API.
2.  **Agents (AI Core)**: Individual AI "brains" that process perception and decide on actions.
3.  **Minecraft Bridge (Java/Forge)**: Mods (`DivineWorld` and `DWClientBot`) that act as the interface between the game and the AI backend.
4.  **UltimMC Automation**: A system to automatically launch and manage Minecraft clients for each agent.
5.  **Frontend (React)**: A web-based dashboard for monitoring and interacting with agents.

---

## Component Interaction

### Agent Spawning Flow
1.  **Request**: A spawn request is sent to the Backend API.
2.  **Setup**: The `EnhancedAgentSpawner` uses `UltimMCLauncher` to create a dedicated Minecraft instance.
3.  **Launch**: The Minecraft client is launched with specific system properties (Agent ID, Backend URL).
4.  **Connection**: The `DWClientBot` mod inside Minecraft connects to the Backend via WebSocket.
5.  **Loop**: The agent starts its perception-action loop.

### Perception-Action Loop
- **Perception**: Every tick, the `DWClientBot` mod sends the agent's game state (position, health, vision) to the Backend.
- **Decision**: The AI Core processes this data through its "brain" to decide on the next action.
- **Action**: The action (move, attack, interact) is sent back to the mod, which executes it using simulated input.

---

## Mental Matrix

The **Mental Matrix** is a 3D simulation environment built into the frontend using Three.js. It allows agents to:
- Simulate physics interactions before executing them in the game.
- Visualize thought processes and mental models.
- Test scenarios (e.g., "Will I survive this jump?") in a safe virtual space.

---

## Permission System

Divine World includes a granular permission system to control AI access to system resources:
- **Camera Access**: Process visual input from webcams.
- **Microphone Access**: Process audio input.
- **File System Access**: Read/write local files.
- **Network Access**: Make external network requests.

These permissions are enforced at the runtime level and can be monitored via the Frontend Activity Monitor.

---

## UltimMC Automation

The automation system simplifies agent deployment by:
- Automatically managing Minecraft accounts and instances.
- Installing the required Forge version and mods.
- Launching the game with the correct configuration for each agent ID.

For more details on setting up the environment, see [Getting Started](./GETTING_STARTED.md).
