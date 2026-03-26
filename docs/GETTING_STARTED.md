# Getting Started with Divine World

Welcome to Divine World, a proprietary world simulation and AI-driven Minecraft universe. This guide will walk you through setting up the entire environment on both Windows and Linux.

---

## 📋 Prerequisites

Regardless of your OS, you will need the following core dependencies:

1.  **Python 3.12+**: Required for the management server and AI core.
2.  **Java 17 (JDK)**: Required for Minecraft 1.20.1 and Forge 47.4.10.
3.  **Node.js & npm**: Required for building the agent dashboards and frontend.
4.  **Ollama**: Required for running the local LLM models (e.g., `phi3:mini`, `llama3`).
5.  **UltimMC**: A specialized Minecraft launcher used by agents for automation.

---

## 🐧 Linux Environment Setup

These instructions apply to most modern Linux distributions (Ubuntu, Debian, Arch, Fedora).

### 1. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip openjdk-17-jdk nodejs npm git
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip openjdk17-src nodejs npm git
```

### 2. Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
# Pull the default model
ollama pull phi3:mini
```

### 3. Setup UltimMC
- Download the latest Linux release from [UltimMC/Launcher](https://github.com/UltimMC/Launcher/releases).
- Extract to `~/UltimMC` or `~/.ultimmc`.
- Ensure `~/UltimMC/bin/UltimMC` is executable.

---

## 🪟 Windows Environment Setup

### 1. Install via Winget (Recommended)
Open PowerShell as Administrator and run:
```powershell
# Python 3.12
winget install Python.Python.3.12

# Java 17 (Temurin)
winget install EclipseAdoptium.Temurin.17.JDK

# Node.js
winget install OpenJS.NodeJS

# Git
winget install Git.Git
```

### 2. Install Ollama
- Download and run the Windows installer from [ollama.com](https://ollama.com/download/windows).
- Open PowerShell and pull the model:
  ```powershell
  ollama pull phi3:mini
  ```

### 3. Setup UltimMC
- Download the Windows zip from [UltimMC/Launcher](https://github.com/UltimMC/Launcher/releases).
- Extract to a folder like `C:\UltimMC`.
- The agents will expect the executable at `C:\UltimMC\bin\UltimMC.exe`.

---

## 🛠️ Project Initialization

Once the environment is ready, follow these steps to initialize Divine World:

### 1. Clone and Install Python Deps
```bash
git clone <repository-url>
cd divine-world-core
python -m venv venv

# Linux
source venv/bin/activate
# Windows
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Paths
If UltimMC is not in a standard location, set the environment variable:
- **Linux**: `export DW_ULTIMMC_PATH=~/path/to/UltimMC`
- **Windows**: `$env:DW_ULTIMMC_PATH="C:\path\to\UltimMC"`

### 3. Build Mods (Optional)
The management server usually handles mod bundling, but you can build them manually:
```bash
cd DivineWorld
./gradlew shadowJar
cd ../DWClientBot
./gradlew shadowJar
```

---

## 🚀 Running Divine World

### 1. Start the Management Server
```bash
# In the project root
python py_backend/main.py --gui
```
This will open the **Agent Control Centre** in your default browser at `http://localhost:11400/gui`.

### 2. Spawn your first Agent
1.  Ensure a Minecraft server is running at `127.0.0.1:25565` (or configured in the GUI).
2.  In the GUI, go to the **Spawn & Control** panel.
3.  Click **Spawn NPC** or **Genesis (Adam & Eve)**.
4.  The server will automatically:
    - Create the agent's "brain" file.
    - Package a standalone executable for the agent.
    - Launch a dedicated Minecraft instance via UltimMC.

---

## ❓ Troubleshooting

- **Minecraft fails to launch**: Ensure Java 17 is the default version (`java -version`).
- **Ollama connection error**: Ensure the Ollama service is running in the background.
- **Port already in use**: Divine World uses port `11400` by default. You can change this using `python py_backend/main.py --port <new_port>`.

For more details, see the **[API Reference](./API_REFERENCE.md)** or **[Architecture Guide](./ARCHITECTURE.md)**.
