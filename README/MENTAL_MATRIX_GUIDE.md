# Mental Matrix Integration Guide

## Overview

The Mental Matrix Simulator is a Blender-like 3D simulation environment integrated into the Divine World frontend. It allows agents to:

- **Create and manipulate 3D objects** in a virtual space
- **Simulate physics interactions** (gravity, collisions, momentum)
- **Test scenarios** before executing them in the actual world
- **Visualize thought processes** and mental models in real-time
- **Export/import simulations** for analysis and sharing

## Architecture

### Frontend Components

1. **MentalMatrixSimulator.jsx** - Main 3D viewport using Three.js
   - Full 3D rendering with interactive controls
   - Real-time physics simulation
   - Object manipulation tools
   - Time scaling and playback controls

2. **MentalMatrixModal.jsx** - Modal wrapper
   - Fullscreen simulation environment
   - Export/import controls
   - Integration with main app

3. **Integration in App.jsx**
   - "Mental Matrix" button in navbar
   - WebSocket communication with backend
   - State management for simulations

### Backend Services

1. **mental_matrix_service.py** - Core simulation engine
   - `MentalMatrixSimulation` - Per-agent simulation state
   - Physics calculations (gravity, velocity, collisions)
   - Object management
   - State history tracking

2. **mental_matrix_websocket.py** - Real-time communication
   - WebSocket connection management
   - Command handlers
   - Event broadcasting

3. **mental_matrix_agent_client.py** - Agent interface
   - Simple API for agents to interact with simulations
   - Scenario testing
   - Physics interaction testing

4. **mental_matrix_api.py** - REST and WebSocket routes
   - Can be registered into any FastAPI app
   - Provides HTTP and WebSocket endpoints

## Usage

### For Frontend Users

#### Opening Mental Matrix
1. Click the **"🧠 Mental Matrix"** button in the Agent Thoughts navbar
2. A fullscreen modal opens with the 3D simulation environment

#### Using the Simulator

**Adding Objects:**
- Click "Add Object" dropdown
- Select object type: Cube, Sphere, or Cylinder
- Objects spawn randomly in the space

**Controls:**
- **Left Mouse Drag**: Rotate view
- **Right Mouse Drag**: Pan camera
- **Mouse Wheel**: Zoom in/out
- **Play/Pause Button**: Start/stop simulation
- **Reset Button**: Clear all objects

**Object Properties:**
1. Click an object to select it
2. Edit properties in the Properties panel:
   - Velocity X, Y, Z
   - Physics settings
   - Custom metadata

**Simulation Controls:**
- **Time Scale**: Slow down (0.1x) or speed up (5x) physics
- **Grid Toggle**: Show/hide reference grid
- **Physics**: Enable/disable physics visualization

**Export/Import:**
- Click "Export" to save simulation state as JSON
- Click "Import" to load a previously saved simulation
- Use "Share Simulation" to collaborate

### For Agent Developers

#### Connecting to Mental Matrix

```python
from mental_matrix_agent_client import MentalMatrixAgentClient

client = MentalMatrixAgentClient(agent_id="my_agent")

# Connect
if await client.connect():
    print("Connected!")
```

#### Adding Objects

```python
await client.add_object(
    object_type="sphere",
    position={"x": 0, "y": 5, "z": 0},
    color=0xFF6B6B,  # Red
    physics={
        "velocity": {"x": 1, "y": 0, "z": 0},
        "use_gravity": True,
        "mass": 1.0,
    }
)
```

#### Running Simulations

```python
# Run a scenario
results = await client.simulate_scenario(
    scenario_name="gravity_test",
    duration_seconds=5.0,
    objects=[
        {
            "type": "cube",
            "position": {"x": 0, "y": 10, "z": 0},
            "color": 0x4CAF50,
            "physics": {"use_gravity": True},
        },
        {
            "type": "sphere",
            "position": {"x": 5, "y": 10, "z": 0},
            "color": 0x4ECDC4,
            "physics": {"use_gravity": True},
        }
    ]
)

print(results)  # Get final simulation state
```

#### Testing Physics Interactions

```python
# Test how objects interact
results = await client.test_physics_interaction(
    object1_type="cube",
    object2_type="sphere",
    force_magnitude=10.0
)
```

#### Exporting Simulations

```python
from pathlib import Path

# Export to file
await client.export_simulation(Path("simulation.json"))

# Import from file
await client.import_simulation(Path("simulation.json"))
```

### For Service Integration

#### Registering with FastAPI App

```python
from fastapi import FastAPI
from mental_matrix_api import register_mental_matrix

app = FastAPI()

# Register the mental matrix service
register_mental_matrix(app)

# Now you have:
# - POST /mental-matrix/simulate/{agent_id}
# - GET /mental-matrix/status/{agent_id}
# - POST /mental-matrix/add-object/{agent_id}
# - DELETE /mental-matrix/remove-object/{agent_id}/{obj_id}
# - POST /mental-matrix/impulse/{agent_id}/{obj_id}
# - POST /mental-matrix/control/{agent_id}
# - WS /mental-matrix/ws
# - GET /mental-matrix/health
```

#### REST API Examples

```bash
# Get simulation status
curl http://localhost:8000/mental-matrix/status/agent1

# Add object
curl -X POST http://localhost:8000/mental-matrix/add-object/agent1 \
  -H "Content-Type: application/json" \
  -d '{
    "type": "cube",
    "position": {"x": 0, "y": 5, "z": 0},
    "color": 16711680
  }'

# Apply impulse
curl -X POST http://localhost:8000/mental-matrix/impulse/agent1/cube_0_0 \
  -H "Content-Type: application/json" \
  -d '{"x": 5, "y": 0, "z": 0}'

# Control simulation
curl -X POST http://localhost:8000/mental-matrix/control/agent1 \
  -H "Content-Type: application/json" \
  -d '{"command": "start"}'
```

## WebSocket Protocol

The Mental Matrix uses a simple JSON-based WebSocket protocol.

### Client → Server Commands

```json
{
  "type": "add_object",
  "data": {
    "type": "cube",
    "position": {"x": 0, "y": 5, "z": 0},
    "color": 16711680,
    "physics": {
      "velocity": {"x": 0, "y": 0, "z": 0},
      "use_gravity": true,
      "mass": 1.0
    }
  }
}
```

### Server → Client Events

```json
{
  "type": "object_added",
  "agent_id": "agent1",
  "object": {
    "id": "cube_0_0",
    "type": "cube",
    "position": {"x": 0, "y": 5, "z": 0},
    "color": 16711680,
    "physics": {...},
    "created_at": "2024-01-01T00:00:00"
  }
}
```

## Simulation Physics

### Forces Applied

- **Gravity**: 9.81 m/s² (configurable per object)
- **Velocity**: Direct manipulation of object velocity
- **Friction**: Reduces velocity over time (configurable)
- **Elasticity**: Controls bounce coefficient on collision

### Object Properties

```python
{
    "id": "cube_0_0",
    "type": "cube",  # cube, sphere, cylinder
    "position": {"x": 0, "y": 5, "z": 0},
    "rotation": {"x": 0, "y": 0, "z": 0},
    "scale": {"x": 1, "y": 1, "z": 1},
    "color": 16711680,  # RGB as hex integer
    "physics": {
        "velocity": {"x": 0, "y": 0, "z": 0},
        "acceleration": {"x": 0, "y": 0, "z": 0},
        "mass": 1.0,
        "use_gravity": true,
        "elasticity": 0.6,  # Bounciness
        "friction": 0.1,    # Resistance
        "show_velocity_vector": false
    }
}
```

## Use Cases

### 1. Physical Reasoning
Agents can test object interactions before acting:
```python
# Does a ball roll down a hill?
# Does a cube tip over at this velocity?
# What trajectory will result from this impulse?
```

### 2. Scenario Planning
Test multiple scenarios to choose the best action:
```python
# Run scenario A: Jump with 5 force
# Run scenario B: Jump with 10 force
# Compare results to choose optimal action
```

### 3. Mental Model Visualization
Show what an agent is thinking about:
```python
# Visualize threat zones as objects
# Show pathfinding as moving objects
# Display social relationships as connected objects
```

### 4. Collaborative Problem Solving
Multiple agents can share simulations:
```python
# Export simulation with problem
# Send to another agent
# They import and test solutions
# Share results back
```

## Performance Considerations

- Simulations update at 60 FPS
- Each frame takes ~16ms
- Physics calculations are O(n) where n = object count
- Recommended: < 500 objects per simulation
- State history keeps last 1000 frames

## Data Persistence

Simulations can be exported as JSON for:
- Analysis and debugging
- Sharing between agents
- Training data generation
- Replay and review

Export format:
```json
{
  "agent_id": "agent1",
  "is_running": false,
  "frame": 300,
  "elapsed_time": 5.0,
  "time_scale": 1.0,
  "objects": [
    {
      "id": "cube_0_0",
      "type": "cube",
      ...
    }
  ],
  "object_count": 1
}
```

## Troubleshooting

### Objects fall through ground
- Ensure `use_gravity` is enabled
- Check ground collision detection

### WebSocket disconnects
- Check backend is running
- Verify agent_id is correct
- Check network connectivity

### Objects not visible
- Check position values are reasonable
- Verify camera view
- Enable grid for reference

### Performance issues
- Reduce number of objects
- Lower time scale
- Disable velocity vector visualization

## Future Enhancements

- [ ] Constraint-based physics (joints, springs)
- [ ] Complex shapes (meshes, heightmaps)
- [ ] Networking for multi-agent simulations
- [ ] Recording and playback with timeline
- [ ] Custom shaders and materials
- [ ] Audio feedback for collisions
- [ ] VR headset support
- [ ] Machine learning integration for physics prediction
