# Divine World Development Guide

This guide is for developers looking to modify the Divine World system, build custom agents, or develop Forge mods.

---

## 🏗️ Project Structure

- `py_backend/`: FastAPI management server and AI core.
  - `ai_core/`: Core agent logic (perception, reasoning, memory).
  - `rl/`: Reinforcement learning policies and models.
- `DivineWorld/`: Server-side Forge mod (agent registration, God entities).
- `DWClientBot/`: Client-side Forge mod (agent perception and control).
- `dw_agent/`: React frontend (dashboard) and Electron wrapper.
- `npc_applications/`: Canonical output directory for packaged agents.
- `data/`: Local storage for brains, logs, and temporary files.

---

## 🛠️ Building from Source

### 1. Building Forge Mods
The mods use Gradle and the `shadowJar` plugin to bundle dependencies.

**DivineWorld Mod:**
```bash
cd DivineWorld
./gradlew shadowJar
```

**DWClientBot Mod:**
```bash
cd DWClientBot
./gradlew shadowJar
```
Compiled JARs are located in `build/libs/`.

### 2. Building Agent Executables
Agent packaging is handled by `py_backend/packager.py`. This process creates a self-contained `.exe` (on Windows) or binary (on Linux) using PyInstaller.

The management server automatically triggers this via `auto_packager.py` when an agent is first spawned. To manually trigger packaging for a running agent:
- **GUI**: Click the **Package** button in the agent's Config tab.
- **API**: `POST /api/agents/{agent_id}/package`.

### 3. Frontend Development
The dashboard is a React app located in `dw_agent/electron/react-app`.
```bash
cd dw_agent/electron/react-app
npm install
npm run dev
```

---

## 🧠 AI Agent Development

### Agent Logic (`ai_core/`)
- **`agent.py`**: The main `NPCAgent` class.
- **`brain_core.py`**: Handles deliberation and reasoning.
- **`memory.py`**: Manages the episodic and semantic memory systems.
- **`brain_capsule.py`**: Handles serialization of the agent's state (`.pcap` files).

### Mod Perception & Actions
To add new perception data:
1.  Modify `PerceptionProvider` in the `DWClientBot` mod.
2.  Update the data model in `py_backend/ai_core/vision.py` or `ai_core/agent.py`.
3.  Implement the action handler in `DWClientBot` to react to new AI decisions.

---

## 🧪 Testing

### Manual Testing
Start the management server in CLI mode for detailed logs:
```bash
python py_backend/main.py --cli
```

### API Testing
Use the provided `curl` commands in the **[API Reference](./API_REFERENCE.md)** or root `README.md` to test specific agent behaviors.

### Remote Agent Testing
To test the architecture without the AI brain, you can create a "Remote Agent" that redirects control to the frontend, allowing a human user to act as the agent's brain.
