# Divine World Development Guide

This guide is for developers looking to modify the Divine World system, build custom agents, or develop Forge mods.

## Project Structure

- `DivineWorld/`: Server-side Forge mod logic.
- `DWClientBot/`: Client-side Forge mod for agent control.
- `py_backend/`: FastAPI backend and AI core.
- `dw_agent/`: React frontend for the agent dashboard.
- `data/`: Local storage for agent "brains", logs, and uploads.

---

## Building from Source

### Building Mods
The mods use Gradle for builds.
```bash
cd DivineWorld
./gradlew build

cd ../DWClientBot
./gradlew build
```
The compiled JARs will be located in the `build/libs/` directory of each project.

### Building Standalone Agents
Agents can be packaged into standalone executables using PyInstaller.
```bash
./build_agents.sh alice bob
```
This script bundles the Python backend, the necessary mods, and the frontend assets into a single executable located in `build/agents/dist/`.

---

## Customizing Agents

### Personalities
Agent personalities are defined in `py_backend/ai_core/agent.py`. You can add custom traits and behaviors by modifying the `CUSTOM_PERSONALITIES` dictionary.

### Brain Logic
The AI reasoning logic is located in the `ai_core` directory. The `NPCAgent` class manages the interaction between perception data and the AI model (e.g., Ollama).

---

## Mod Development
Divine World uses Minecraft Forge 1.20.1.
- `DivineWorld` mod handles server-side registration of agents and God entities.
- `DWClientBot` handles client-side perception (reading game state) and action (simulating inputs).

### Perception Data
To add new perception features, modify the `PerceptionProvider` in the `DWClientBot` mod and update the corresponding handler in the Python backend's `NPCAgent.perceive()` method.
