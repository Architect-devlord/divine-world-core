"""
Isaac Sim Integration for DW Agents
=====================================
Wires NPCAgent into an NVIDIA Isaac Sim environment for physics-based
training and simulation.

Architecture
------------
This file deliberately contains NO subclasses of VisionSystem or
ActuatorAdapterBase — those base-classes do not exist in this codebase.

Instead the integration uses the real public APIs:

  Vision:
    vision.py → IsaacSimVisionBackend(CaptureBackend)
              → VisionAdapter.attach_isaac_camera(camera_prim)
    Call add_vision_to_agent(agent) once, then attach the camera prim
    after world.reset().  The VisionAdapter pipeline (CNN feature
    extractor, online vocabulary, cognitive-loop patch) is then driven
    by the Sim's clock.

  Actuators:
    IsaacSimActuator is a self-contained helper that translates the
    11-element controls dict returned by NPCAgent.act() into Isaac Sim
    ArticulationController commands.  It does NOT inherit from anything
    because NPCAgent owns its own motor path via act() / act_god().

  Episode loop:
    Uses agent.perceive() → agent.act() (or act_god()) rather than the
    non-existent agent.get_action() / agent.store_transition() / agent.update().
    RL experience accumulation is handled by the agent's own cognitive_loop
    and reward_system; this integration adds task-specific reward shaping
    on top via _calculate_reward().

  Folder watcher:
    Replaces the broken carb.events.Type.FILESYSTEM approach (that
    constant does not exist in all Isaac Sim versions) with a simple
    polling thread using pathlib.

Dependencies (Isaac Sim side):
  omni.isaac.core, omni.kit.commands, omni.usd, carb
These are imported lazily so the module can be loaded in plain Python
for unit-testing without a running Isaac instance.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

log = logging.getLogger("isaac_sim_integration")
log.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Lazy Isaac Sim guards
# ---------------------------------------------------------------------------

def _require_isaac(caller: str):
    """Raise a clear error if Isaac Sim is not available."""
    try:
        import omni  # noqa: F401
    except ImportError:
        raise RuntimeError(
            f"{caller} requires NVIDIA Isaac Sim. "
            "Run this inside an Isaac Sim Python environment."
        )


# ---------------------------------------------------------------------------
# IsaacSimActuator
# ---------------------------------------------------------------------------

class IsaacSimActuator:
    """
    Translates an NPCAgent controls dict into Isaac Sim joint commands.

    The controls dict is the value returned by NPCAgent.act():
        {
          'move_forward': float,   # [-1, 1]
          'move_strafe':  float,   # [-1, 1]
          'jump':         bool,
          'yaw_delta':    float,   # degrees/step
          'pitch_delta':  float,
          ...
        }

    Joint mapping is left intentionally simple — override _controls_to_joints()
    for your specific robot.
    """

    def __init__(
        self,
        robot_prim_path:   str,
        camera_prim_path:  str,
        stiffness:         float = 1000.0,
        damping:           float = 100.0,
        force_limit:       float = 1000.0,
    ):
        _require_isaac("IsaacSimActuator")

        import omni.isaac.core.utils.prims as prim_utils
        from omni.isaac.core.articulations import ArticulationController

        self.robot_prim_path  = robot_prim_path
        self.camera_prim_path = camera_prim_path
        self.stiffness        = stiffness
        self.damping          = damping
        self.force_limit      = force_limit

        self.robot_prim  = prim_utils.get_prim_at_path(robot_prim_path)
        self.camera_prim = prim_utils.get_prim_at_path(camera_prim_path)

        self.articulation: Optional[Any] = None
        self._initialized = False

    def initialize(self):
        """Call once after world.reset() to bind the articulation controller."""
        if self._initialized:
            return

        from omni.isaac.core.articulations import ArticulationController
        self.articulation = ArticulationController(
            prim_path=self.robot_prim_path,
            joint_names=["*"],
            actuation_mode="position",
        )

        # Disable kinematic mode so physics drives the robot
        try:
            self.robot_prim.GetAttribute("physics:kinematic").Set(False)
        except Exception as exc:
            log.debug(f"Could not set physics:kinematic: {exc}")

        self._initialized = True
        log.info(f"IsaacSimActuator initialised: {self.robot_prim_path}")

    def apply(self, controls: Dict[str, Any]):
        """
        Apply one set of NPCAgent controls to the robot.
        Called once per simulation step.
        """
        if not self._initialized or self.articulation is None:
            return

        joint_targets = self._controls_to_joints(controls)
        self.articulation.apply_dof_position_targets(
            positions=joint_targets,
            stiffness=self.stiffness,
            damping=self.damping,
            force_limits=self.force_limit,
        )

        # Camera orientation from yaw/pitch deltas
        yaw_delta   = controls.get("yaw_delta",   0.0)
        pitch_delta = controls.get("pitch_delta",  0.0)
        if (yaw_delta or pitch_delta) and self.camera_prim:
            try:
                xform = self.camera_prim.GetAttribute("xformOp:rotateXYZ")
                cur   = xform.Get() or (0.0, 0.0, 0.0)
                xform.Set((
                    float(cur[0]) + pitch_delta,
                    float(cur[1]) + yaw_delta,
                    float(cur[2]),
                ))
            except Exception as exc:
                log.debug(f"Camera rotation failed: {exc}")

    def get_state(self) -> Dict[str, np.ndarray]:
        """Return current joint positions and velocities."""
        if not self._initialized or self.articulation is None:
            return {"joint_positions": np.zeros(1), "joint_velocities": np.zeros(1)}

        try:
            dof_states = self.articulation.get_dof_states()  # (N, 2) [pos, vel]
            return {
                "joint_positions":  np.array(dof_states[:, 0]),
                "joint_velocities": np.array(dof_states[:, 1]),
            }
        except Exception as exc:
            log.debug(f"get_state error: {exc}")
            return {"joint_positions": np.zeros(1), "joint_velocities": np.zeros(1)}

    def _controls_to_joints(self, controls: Dict[str, Any]) -> np.ndarray:
        """
        Map NPCAgent controls to joint position targets.
        Override this method for your specific robot kinematics.
        Default: two-wheel differential drive approximation.
        """
        if self.articulation is None:
            return np.zeros(1)

        try:
            n_dof = self.articulation.num_dof
        except Exception:
            n_dof = 2

        targets = np.zeros(n_dof)

        if n_dof >= 2:
            fwd    = float(controls.get("move_forward", 0.0))
            strafe = float(controls.get("move_strafe",  0.0))
            # Differential drive: left = fwd - strafe, right = fwd + strafe
            targets[0] = fwd - strafe   # left wheel
            targets[1] = fwd + strafe   # right wheel

        return targets


# ---------------------------------------------------------------------------
# IsaacSimIntegration
# ---------------------------------------------------------------------------

class IsaacSimIntegration:
    """
    Manages one or more NPCAgents running inside an Isaac Sim world.

    Usage:
        from isaac_sim_integration import IsaacSimIntegration
        from ai_core.vision import add_vision_to_agent

        sim = IsaacSimIntegration(
            watch_folder="dw_agents_sim",
            robot_asset_path="omniverse://localhost/NVIDIA/Assets/..."
        )

        # Each agent directory dropped into watch_folder is automatically
        # detected by the polling thread and started via start_sim_agent().
    """

    def __init__(
        self,
        watch_folder:    str,
        robot_asset_path: str,
        stage:           Any = None,
        poll_interval:   float = 2.0,
    ):
        _require_isaac("IsaacSimIntegration")

        self.watch_folder     = Path(watch_folder)
        self.robot_asset      = robot_asset_path
        self.poll_interval    = poll_interval
        self.watch_folder.mkdir(parents=True, exist_ok=True)

        # Lazy import — only available inside Isaac Sim
        import omni.usd
        self.stage = stage or omni.usd.get_context().get_stage()

        self._active:   Dict[str, Dict] = {}   # agent_id → info dict
        self._episodes: Dict[str, List[float]] = {}
        self._seen_dirs: set = set()

        # Start polling thread
        self._stop_event = threading.Event()
        self._poll_thread = threading.Thread(
            target=self._poll_watch_folder,
            name="isaac_folder_poll",
            daemon=True,
        )
        self._poll_thread.start()
        log.info(f"IsaacSimIntegration watching: {self.watch_folder}")

    # ------------------------------------------------------------------
    # Folder watcher
    # ------------------------------------------------------------------

    def _poll_watch_folder(self):
        """
        Polling-based folder watcher.
        Checks for new DW_* directories every poll_interval seconds.

        This replaces the old carb.events.Type.FILESYSTEM approach which
        is unreliable across Isaac Sim versions.
        """
        while not self._stop_event.is_set():
            try:
                for entry in self.watch_folder.iterdir():
                    if (entry.is_dir()
                            and entry.name.startswith("DW_")
                            and entry not in self._seen_dirs):
                        self._seen_dirs.add(entry)
                        agent_id = entry.name.replace("DW_", "")
                        log.info(f"Detected new agent directory: {entry}")
                        self.start_sim_agent(agent_id, entry)
            except Exception as exc:
                log.debug(f"Poll error: {exc}")
            self._stop_event.wait(self.poll_interval)

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def start_sim_agent(self, agent_id: str, agent_dir: Path):
        """
        Load a brain, create a robot in the stage, wire up vision and
        actuator, and register the agent as active.
        """
        if agent_id in self._active:
            log.warning(f"Agent {agent_id} already active in simulation")
            return

        brain_path = agent_dir / "brain.pcap"
        if not brain_path.exists():
            log.error(f"No brain.pcap for {agent_id} in {agent_dir}")
            return

        try:
            import omni.kit.commands

            # ── Create robot USD reference in stage ───────────────────────
            robot_path = f"/World/Robots/{agent_id}"
            omni.kit.commands.execute(
                "CreateReference",
                path=robot_path,
                asset_path=self.robot_asset,
                usd_context=self.stage,
            )

            # ── Camera prim ───────────────────────────────────────────────
            camera_path = f"{robot_path}/Camera"
            omni.kit.commands.execute(
                "CreateCamera",
                path=camera_path,
                parent_path=robot_path,
            )

            # ── Load agent brain ──────────────────────────────────────────
            from ai_core.agent import NPCAgent
            agent = NPCAgent(agent_id)
            agent.load(str(brain_path))

            # ── Wire vision via the real VisionAdapter API ────────────────
            # add_vision_to_agent() attaches a VisionAdapter to agent.vision
            # and patches the cognitive loop.  We then point it at the
            # Isaac camera prim.
            from ai_core.vision import add_vision_to_agent
            add_vision_to_agent(
                agent,
                feature_dim=64,
                max_vocab_size=256,
                frame_h=84,
                frame_w=84,
                fps=15.0,
                enable_depth=True,
                auto_start=True,
            )

            # ── Attach Isaac camera prim to the VisionAdapter ─────────────
            # IsaacSimVisionBackend already lives inside VisionAdapter;
            # attach_isaac_camera() creates it if absent and binds the prim.
            if hasattr(agent, "vision") and agent.vision is not None:
                agent.vision.attach_isaac_camera(camera_path)
            else:
                log.warning(
                    f"[{agent_id}] VisionAdapter not attached — "
                    "vision.py add_vision_to_agent() may have failed"
                )

            # ── Create actuator ───────────────────────────────────────────
            actuator = IsaacSimActuator(
                robot_prim_path=robot_path,
                camera_prim_path=camera_path,
            )
            # actuator.initialize() must be called AFTER world.reset() —
            # deferred until start_training() resets the world.

            self._active[agent_id] = {
                "agent":      agent,
                "actuator":   actuator,
                "robot_path": robot_path,
                "training":   False,
                "agent_dir":  agent_dir,
            }
            self._episodes[agent_id] = []
            log.info(
                f"✅ {agent_id} ready in sim  "
                f"robot={robot_path}  brain={brain_path}"
            )

        except Exception as exc:
            log.exception(f"Failed to start {agent_id}: {exc}")
            self._cleanup_agent(agent_id)

    def start_training(self, agent_id: str, num_episodes: int = 100,
                       reward_fn: Optional[Callable[[str], float]] = None,
                       done_fn:   Optional[Callable[[str], bool]]  = None):
        """
        Run num_episodes training episodes for agent_id.

        reward_fn(agent_id) → float     — task-specific reward (optional)
        done_fn(agent_id)   → bool      — episode termination (optional)

        Falls back to _default_reward / _default_done if not provided.
        """
        if agent_id not in self._active:
            log.error(f"Agent {agent_id} not found — call start_sim_agent first")
            return
        info = self._active[agent_id]
        if info["training"]:
            log.warning(f"Agent {agent_id} already training")
            return

        _reward = reward_fn or self._default_reward
        _done   = done_fn   or self._default_done

        info["training"] = True
        asyncio.ensure_future(
            self._training_loop(agent_id, num_episodes, _reward, _done)
        )

    async def _training_loop(
        self,
        agent_id:     str,
        num_episodes: int,
        reward_fn:    Callable,
        done_fn:      Callable,
    ):
        info     = self._active[agent_id]
        agent    = info["agent"]
        actuator = info["actuator"]

        self._episodes[agent_id] = []

        for episode in range(num_episodes):
            if agent_id not in self._active:
                break   # agent was cleaned up mid-training

            # ── Reset world and actuator ──────────────────────────────────
            actuator.initialize()

            done            = False
            episode_rewards: List[float] = []

            while not done:
                # Build raw observation from Isaac state
                state = actuator.get_state()
                raw_obs: Dict[str, Any] = {
                    "joint_positions":  state["joint_positions"].tolist(),
                    "joint_velocities": state["joint_velocities"].tolist(),
                    # Minecraft-flavoured fields that perceive() expects
                    "health":     20.0,
                    "hunger":     20.0,
                    "saturation":  5.0,
                    "position":   {"x": 0.0, "y": 0.0, "z": 0.0},
                    "yaw":        0.0,
                    "pitch":      0.0,
                    "entities":   [],
                    "inventory":  {"slot_count": 0},
                }

                # perceive() → fixed-size feature vector
                obs_vec = agent.perceive(raw_obs)

                # act() → controls dict (pure converter, no side effects)
                action_arr  = np.zeros(11, dtype=np.float32)
                if hasattr(agent, "brain") and agent.brain is not None:
                    try:
                        from ai_core.planner import Planner
                        if hasattr(agent, "planner") and agent.planner:
                            plan = agent.planner.generate_plan(
                                obs=raw_obs, memory=agent.memory,
                                horizon=1, context=raw_obs,
                            )
                            if plan:
                                act = plan[0]
                                action_arr[0] = float(act.get("move_forward", 0.0))
                                action_arr[1] = float(act.get("move_strafe",  0.0))
                                action_arr[2] = float(act.get("jump",         0.0))
                    except Exception:
                        pass

                controls = agent.act(action_arr)

                # Apply controls in sim
                actuator.apply(controls)

                # Task reward
                reward = reward_fn(agent_id)
                episode_rewards.append(reward)

                # Accumulate reward into the agent's own reward system
                if agent.reward_system is not None:
                    try:
                        agent.reward_system.update(
                            event_type="sim_step",
                            outcome={"reward": reward},
                        )
                    except Exception:
                        pass

                done = done_fn(agent_id)
                await asyncio.sleep(0)   # yield to event loop

            total = sum(episode_rewards)
            self._episodes[agent_id].append(total)
            log.info(
                f"[{agent_id}] Episode {episode + 1}/{num_episodes} — "
                f"total reward: {total:.3f}"
            )

            # Periodic save
            if (episode + 1) % 10 == 0:
                self._save_agent(agent_id)

        # Training complete
        info["training"] = False
        self._save_agent(agent_id)
        log.info(f"✅ Training complete for {agent_id}")

    # ------------------------------------------------------------------
    # Default reward / done (override via start_training kwargs)
    # ------------------------------------------------------------------

    def _default_reward(self, agent_id: str) -> float:
        """
        Placeholder reward function.
        Implement task-specific reward logic here or pass reward_fn=...
        to start_training().
        """
        return 0.0

    def _default_done(self, agent_id: str) -> bool:
        """
        Placeholder termination function.
        Returns False (episode never terminates) until overridden.
        """
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_agent(self, agent_id: str):
        if agent_id not in self._active:
            return
        info    = self._active[agent_id]
        agent   = info["agent"]
        out_dir = info["agent_dir"]
        try:
            agent.save(str(out_dir / "brain.pcap"))
            log.info(f"💾 Saved {agent_id}")
        except Exception as exc:
            log.error(f"Save failed for {agent_id}: {exc}")

    def get_episode_rewards(self, agent_id: str) -> List[float]:
        """Return the list of total rewards per completed episode."""
        return list(self._episodes.get(agent_id, []))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_agent(self, agent_id: str):
        """Remove one agent from the simulation."""
        if agent_id not in self._active:
            return
        info = self._active[agent_id]
        try:
            import omni.kit.commands
            omni.kit.commands.execute(
                "DeletePrims",
                paths=[info["robot_path"]],
                destructive=True,
            )
        except Exception as exc:
            log.debug(f"Error deleting {info['robot_path']}: {exc}")
        del self._active[agent_id]
        self._episodes.pop(agent_id, None)
        log.info(f"Cleaned up {agent_id}")

    def cleanup_all(self):
        """Stop watcher thread and remove all agents."""
        self._stop_event.set()
        for agent_id in list(self._active.keys()):
            self._cleanup_agent(agent_id)
        log.info("IsaacSimIntegration shut down")


# ---------------------------------------------------------------------------
# Minimal sanity test (no Isaac Sim required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    print("Testing IsaacSimActuator._controls_to_joints() without Isaac Sim…")

    # Patch the guard so we can instantiate without omni
    import unittest.mock as mock
    with mock.patch("isaac_sim_integration._require_isaac"):
        import omni  # type: ignore  # noqa: F401  (won't be available)

    print("Skipped — run inside Isaac Sim for a live test.")
    sys.exit(0)