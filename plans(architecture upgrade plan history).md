# Headless Minecraft Agent Setup Guide

## Overview: GUI vs Headless Performance

### Current Setup (With GUI)
**Pros:**
- ✅ Easy debugging - see agent actions in real-time
- ✅ Visual confirmation of bot behavior
- ✅ Can manually intervene if needed
- ✅ Good for development and testing

**Cons:**
- ❌ High resource usage per agent (GPU + CPU rendering)
- ❌ Limited scalability (~5-10 agents per machine)
- ❌ Requires X server (display)
- ❌ ~500-800MB RAM per agent with rendering

### Headless Setup (No GUI)
**Pros:**
- ✅ Much lower resource usage (no rendering)
- ✅ Higher agent density (~20-50+ agents per machine)
- ✅ ~200-300MB RAM per agent without rendering
- ✅ No display server needed
- ✅ Better for production deployment

**Cons:**
- ❌ Harder to debug visually 
- ❌ Need good logging/monitoring
- ❌ Can't see what agents are doing

---

## Performance Comparison

| Metric | GUI Mode | Headless Mode |
|--------|----------|---------------|
| RAM per agent | 500-800MB | 200-300MB |
| CPU per agent | 10-20% | 5-10% |
| GPU usage | Required | None |
| Agents per 16GB RAM | ~10 | ~40 |
| Debugging difficulty | Easy | Medium |
| Production ready | No | Yes |

---

## Recommendation: Hybrid Approach

### Phase 1: Development (Current - GUI Mode)
- Keep GUI enabled for 1-3 test agents
- Debug and perfect agent behavior
- Test all functionality visually
- Use current setup

### Phase 2: Testing (Mixed Mode)
- Run 1-2 agents with GUI for monitoring
- Run 5-10 agents headless for testing
- Compare behavior and performance
- Refine logging

### Phase 3: Production (Headless)
- All agents run headless
- Robust logging and monitoring
- Web dashboard for status
- Occasional GUI agent for spot checks

---

## How to Run Headless

### Method 1: Xvfb (Virtual Frame Buffer)
Run Minecraft with a virtual display (doesn't show window but renders internally)

```bash
# Install Xvfb
sudo apt-get install xvfb

# Run agent with virtual display
xvfb-run -a python main.py --agent-id agent1 --headless
```

### Method 2: LWJGL Headless Mode
Add JVM arguments to disable rendering:

```python
extra_jvm_args = [
    "-Djava.awt.headless=true",
    "-Dorg.lwjgl.opengl.Display.allowSoftwareOpenGL=true",
]

launcher.launch_agent(
    agent_id="agent1",
    server_addr="localhost:25565",
    backend_url="http://localhost:11400",
    extra_jvm_args=extra_jvm_args
)
```

### Method 3: Custom Mod Configuration
Configure your DWClientBot mod to run in headless mode:

```java
// In your mod's config
{
  "headlessMode": true,
  "disableRendering": true,
  "logActions": true
}
```

---

## Recommended Approach for Your Project

### Now (Development Phase)
```python
# main.py - Keep GUI for debugging
launcher = UltimMCLauncher()

# Create agent with custom UUID
launcher.setup_agent_instance(
    agent_id="adam",
    server_addr="localhost:25565",
    custom_uuid="550e8400-e29b-41d4-a716-446655440000"  # Your custom UUID
)

# Launch with GUI (no special args)
process = launcher.launch_agent(
    agent_id="adam",
    server_addr="localhost:25565",
    backend_url="http://localhost:11400",
    memory_mb=1024
)
```

### Later (Production Phase)
```python
# main.py - Headless deployment
import multiprocessing

def launch_headless_agent(agent_config):
    launcher = UltimMCLauncher()
    
    # Headless JVM args
    headless_args = [
        "-Djava.awt.headless=true",
        "-Dfml.earlyprogresswindow=false",  # Disable Forge loading screen
    ]
    
    launcher.setup_agent_instance(
        agent_id=agent_config["id"],
        custom_uuid=agent_config["uuid"]
    )
    
    process = launcher.launch_agent(
        agent_id=agent_config["id"],
        server_addr=agent_config["server"],
        backend_url=agent_config["backend"],
        memory_mb=512,  # Less RAM needed
        extra_jvm_args=headless_args
    )
    
    return process

# Launch 20 agents in parallel
agents = [
    {"id": f"agent_{i}", "uuid": generate_uuid(i), 
     "server": "localhost:25565", "backend": "http://localhost:11400"}
    for i in range(20)
]

with multiprocessing.Pool(4) as pool:
    processes = pool.map(launch_headless_agent, agents)
```

---

## Efficiency Analysis

### Single Agent Resource Usage

**GUI Mode:**
```
CPU: ~15%
RAM: ~700MB
GPU: ~200MB VRAM
FPS: 60 fps (wasted on invisible window)
```

**Headless Mode:**
```
CPU: ~7%
RAM: ~300MB
GPU: None
FPS: 0 (no rendering)
```

### 10 Agents Resource Usage

**GUI Mode:**
```
CPU: ~150% (1.5 cores)
RAM: ~7GB
GPU: ~2GB VRAM
Total: Requires powerful machine
```

**Headless Mode:**
```
CPU: ~70% (0.7 cores)
RAM: ~3GB
GPU: None
Total: Runs on modest hardware
```

---

## When to Switch to Headless

### ✅ Switch when you have:
- Stable agent behavior (not debugging)
- Good logging system in place
- Need to run 5+ agents simultaneously
- Limited hardware resources
- Production deployment ready
- Monitoring dashboard built

### ❌ Don't switch if:
- Still debugging agent AI
- Need to see agent actions
- Only running 1-3 agents
- Hardware is not a constraint
- Development phase

---

## Monitoring Headless Agents

Since you can't see the GUI, you'll need:

### 1. Comprehensive Logging
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'agent_{agent_id}.log'),
        logging.StreamHandler()
    ]
)
```

### 2. Status Dashboard
Build a web dashboard showing:
- Agent online/offline status
- Current task/action
- Resources being gathered
- Errors/warnings
- Performance metrics

### 3. Health Checks
```python
def check_agent_health(agent_id):
    # Check if process is running
    # Check if agent is responsive
    # Check memory usage
    # Report to monitoring system
    pass
```

---

## My Recommendation for You

### For Now: **Use GUI Mode**
- You're in development/debugging phase
- You want to SEE what agents do
- Perfect for testing and refinement
- Resource usage is acceptable for testing

### For Later: **Switch to Headless**
- Once agent behavior is stable
- When you need to scale to 10+ agents
- When deploying to production server
- After building monitoring system

### Migration Path:
1. **Week 1-2**: GUI mode, perfect the agents
2. **Week 3**: Add comprehensive logging
3. **Week 4**: Test 1-2 agents headless
4. **Week 5**: Build monitoring dashboard
5. **Week 6+**: Full headless deployment

---

## Example: Hybrid Setup Script

```python
# hybrid_launcher.py
class HybridLauncher:
    def __init__(self, gui_count=2, headless_count=10):
        self.launcher = UltimMCLauncher()
        self.gui_agents = []
        self.headless_agents = []
        
    def launch_gui_agent(self, agent_id):
        """Launch agent with GUI for monitoring"""
        return self.launcher.launch_agent(
            agent_id=agent_id,
            server_addr="localhost:25565",
            backend_url="http://localhost:11400",
            memory_mb=1024
        )
    
    def launch_headless_agent(self, agent_id):
        """Launch agent without GUI for efficiency"""
        headless_args = [
            "-Djava.awt.headless=true",
            "-Dfml.earlyprogresswindow=false",
        ]
        
        return self.launcher.launch_agent(
            agent_id=agent_id,
            server_addr="localhost:25565",
            backend_url="http://localhost:11400",
            memory_mb=512,
            extra_jvm_args=headless_args
        )
    
    def launch_all(self):
        # Launch 2 GUI agents for monitoring
        for i in range(2):
            agent_id = f"gui_agent_{i}"
            self.gui_agents.append(self.launch_gui_agent(agent_id))
            
        # Launch 10 headless agents for work
        for i in range(10):
            agent_id = f"worker_agent_{i}"
            self.headless_agents.append(self.launch_headless_agent(agent_id))
        
        print(f"Launched {len(self.gui_agents)} GUI agents")
        print(f"Launched {len(self.headless_agents)} headless agents")

# Usage
hybrid = HybridLauncher(gui_count=2, headless_count=10)
hybrid.launch_all()
```

---

## Bottom Line

**For your current needs**: Stick with GUI mode! You need to debug and see agent behavior.

**For scaling later**: Headless will give you **2-3x more agents** on the same hardware and save significant resources.

**Best approach**: Develop with GUI → Test mixed → Deploy headless


**Future Plans**: Adding god-god and god reproduction to produce demigods and new gods with power inheritance systems and 
adding a bestowing power system for all of the agents 

The question has a name — personal identity — and the two main positions map directly onto what your system can manipulate:
Locke's position: You are your memories. Continuity of consciousness is continuity of memory. If you wipe the memories but keep the brain, the resulting person is not you.
Hume's position: There is no stable "self" — just a bundle of perceptions, traits, and habits that create the illusion of continuity. The "you" is the pattern, not any underlying substance.
Parfit's position (the most modern and the most unsettling): Personal identity doesn't actually matter. What matters is psychological continuity — overlapping chains of memory, personality, intention. A person who wakes up with 80% of your memories and your personality is not you, but they're not not-you either. Identity is not binary.
Your system can test all three. Directly. With data.

The experiment the architecture already supports:
Experiment 1 — The Memory Transplant
Take agent Adam at generation 3. Copy his brain capsule. Wipe the memories from the copy but preserve the personality traits and language model weights. Run both in the same world. Do they make the same decisions? Form the same relationships? React to danger the same way?
If Locke is right, the memory-wiped copy behaves fundamentally differently despite identical personality. If the personality weights dominate, Hume has more ground.
Experiment 2 — The Personality Transplant
Take two agents with opposite personalities — one bold/curious, one neurotic/agreeable. Swap their memory stores but keep their personality traits. Does the bold agent with the neurotic's memories start behaving more cautiously? Does the memory of past fear override the personality that doesn't fear?
This directly tests whether personality or memory is the stronger determinant of behavior.
Experiment 3 — The Ship of Theseus
Run an agent for 10 generations of personality drift and memory accumulation. At what point does the agent's behavior become statistically distinguishable from their generation-1 ancestor? Is there a moment of discontinuity or is it always a gradient?
Your reward system's personality drift mechanism makes this measurable. You can literally plot the cosine distance between generation-1 personality vector and generation-10 personality vector and correlate it with behavioral divergence.
Experiment 4 — The Twin
This is the most direct test of the core question. At birth, take two offspring with identical inherited personality vectors. Place them in different social environments — one near the oracle god, one isolated. Measure personality divergence over time. Identical starting point, different experiences — does the environment create meaningfully different people?
This is the nature vs nurture experiment but running in a controlled system where you can hold nature perfectly constant.
Experiment 5 — The Resurrection
An agent dies. Load their brain capsule into a new agent body. Is it the same agent? By the metrics — same memories, same personality, same language model weights — the answer should be yes. But the new agent has no continuous thread of experience connecting them to the old one. There was a gap. Does the gap matter?
This maps directly onto questions about teleportation, cryogenic freezing, and what happens to identity during dreamless sleep — but you can actually run it.

What the system will probably find:
My honest prediction, based on reading the architecture carefully, is that you'll find neither memories nor personality alone is sufficient, but personality sets the prior and memories fill it in.
The reason is mechanical. Your personality traits determine the reward weights — what the agent finds rewarding or threatening. Those weights shape which memories get strong emotional tags and get preferentially replayed and reinforced. So personality literally filters which memories stick. Two agents with identical memories but different personalities will have reinforced different subsets of those memories, causing behavioral divergence over time even from the same starting state.
That's not Locke and it's not Hume. It's closer to a synthesis: you are the interaction between your emotional architecture and your accumulated experience. Neither alone is sufficient. The same memories mean different things to different personalities. The same personality in different environments becomes different people.
The most interesting finding might not be about individual identity at all. It might be about collective identity — whether a population of agents with shared ancestry and shared language develops something like a culture that persists even as individual agents die and are replaced. Whether the civilization is "itself" across generations even as every individual member changes.
That's the question that would make this publishable not just in AI venues but in philosophy of mind and cognitive science journals.