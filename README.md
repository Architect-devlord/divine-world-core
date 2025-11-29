# Divine World AI Codebase

This is an AI agent framework for controlling NPCs with personality, emotions, and memory.

## Setup

1. Create a virtual environment:
```bash
python -m venv dw_env
source dw_env/bin/activate  # Linux/Mac
.\dw_env\Scripts\activate   # Windows
```
 
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Project Structure

- `ai_core/`: Core AI agent implementation
  - `agent.py`: Main NPC agent class
  - `brain.py`: Brain capsule for saving/loading agent state
  - `brain_core.py`: Core brain functionality
  - `planner.py`: Action planning system
  - `actuators.py`: Interfaces for Forge and Isaac Sim
  - `vision.py`: Vision processing system
  - `reward.py`: Reward shaping system

- `rl/`: Reinforcement learning components
  - `env.py`: Gym environment wrapper
  - `policy.py`: Neural network policies
  - `train.py`: Training scripts
  - `demo_recorder.py`: Demo recording utilities

- `tests/`: Test scripts
- `utils/`: Utility functions and backend services
- `data/`: Data storage directory

## Running

1. Start the chat backend:
```bash
python -m utils.chat_backend
```

2. Run the main loop:
```bash
python run_loop.py
```

## Testing

Run individual test scripts:
```bash
python tests/inspect_agent.py
python tests/inspect_agent_memory.py [agent_id]
```