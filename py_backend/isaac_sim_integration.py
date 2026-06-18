"""
Isaac Sim 5.0 Integration for DW Agents
=========================================
Updated for Isaac Sim 5.0 (open source, SIGGRAPH 2025).

Key API changes from Isaac Sim 4.x → 5.0
------------------------------------------
  OLD: from omni.isaac.core.articulations import ArticulationController
  NEW: from isaacsim.core.prims import SingleArticulation

  OLD: ArticulationController(prim_path, joint_names=["*"], actuation_mode="position")
  NEW: SingleArticulation(prim_path=prim_path)
       art.initialize()           # after world.reset()

  OLD: art.apply_dof_position_targets(positions, stiffness, damping, force_limits)
  NEW: from isaacsim.core.utils.types import ArticulationAction
       art.apply_action(ArticulationAction(joint_positions=positions))

  OLD: states = art.get_dof_states()        # (N,2) array [pos, vel]
  NEW: pos = art.get_joint_positions()       # (N,) array
       vel = art.get_joint_velocities()      # (N,) array

  OLD: art.num_dof                           # still valid on SingleArticulation
  NEW: art.num_dof                           # unchanged

  OLD: omni.kit.commands.execute("CreateCamera", path=..., parent_path=...)
  NEW: omni.kit.commands.execute("CreatePrimWithDefaultXform",
           prim_type="Camera", prim_path=...)

  OLD: from omni.isaac.core.world import World
  NEW: from isaacsim.core.world import World

  OLD: import omni.isaac.core.utils.prims as prim_utils
  NEW: import isaacsim.core.utils.prims as prim_utils

Known issue (GitHub #320): ArticulationController.apply_action() raises TypeError
when the world backend is "torch" and joint_velocities is None.
Fix: pass only joint_positions OR joint_velocities, never a mixed array with None.

Architecture (unchanged from previous version):
  - IsaacSimActuator: translates NPCAgent controls dict → Isaac joint commands
  - IsaacSimIntegration: manages agents in a world, folder-watcher, training loop
  - No subclassing of internal base classes — uses real public APIs only
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
# Lazy Isaac Sim 5.0 import guards
# ---------------------------------------------------------------------------

def _require_isaac(caller: str):
    """Raise a clear error if Isaac Sim 5.0 is not available."""
    try:
        import isaacsim  # noqa: F401  (top-level package in 5.0)
    except ImportError:
        try:
            import omni  # noqa: F401  (fallback for 4.x environments)
        except ImportError:
            raise RuntimeError(
                f"{caller} requires NVIDIA Isaac Sim 5.0. "
                "Run inside an Isaac Sim Python environment "
                "(GitHub: isaac-sim/IsaacSim)."
            )


def _import_prims_utils():
    """Return the prims utility module, trying 5.0 path first."""
    try:
        import isaacsim.core.utils.prims as m
        return m
    except ImportError:
        import omni.isaac.core.utils.prims as m  # type: ignore
        return m


def _import_articulation(prim_path: str):
    """
    Create a SingleArticulation (5.0) or ArticulationController (4.x fallback).
    Returns an object that supports:
        .initialize(), .apply_action(), .get_joint_positions(),
        .get_joint_velocities(), .num_dof
    """
    try:
        from isaacsim.core.prims import SingleArticulation
        return SingleArticulation(prim_path=prim_path)
    except ImportError:
        pass
    # 4.x fallback shim
    try:
        from omni.isaac.core.articulations import ArticulationController
        art = ArticulationController(
            prim_path=prim_path, joint_names=["*"], actuation_mode="position"
        )
        # Shim get_joint_positions / get_joint_velocities for 4.x API
        if not hasattr(art, "get_joint_positions"):
            def _get_pos(self=art):
                states = self.get_dof_states()
                return np.array(states[:, 0])
            def _get_vel(self=art):
                states = self.get_dof_states()
                return np.array(states[:, 1])
            import types
            art.get_joint_positions  = types.MethodType(lambda s: _get_pos(),  art)
            art.get_joint_velocities = types.MethodType(lambda s: _get_vel(), art)
        return art
    except ImportError:
        raise RuntimeError("Neither isaacsim.core.prims nor omni.isaac.core.articulations found.")


def _import_articulation_action():
    """Return ArticulationAction class from Isaac Sim 5.0 or 4.x."""
    try:
        from isaacsim.core.utils.types import ArticulationAction
        return ArticulationAction
    except ImportError:
        try:
            from omni.isaac.core.utils.types import ArticulationAction  # type: ignore
            return ArticulationAction
        except ImportError:
            return None


# ---------------------------------------------------------------------------
# IsaacSimActuator  (updated for Isaac Sim 5.0)
# ---------------------------------------------------------------------------

class IsaacSimActuator:
    """
    Translates NPCAgent controls dict into Isaac Sim 5.0 joint commands.

    Controls dict (from NPCAgent.act()):
        move_forward  float  [-1, 1]
        move_strafe   float  [-1, 1]
        jump          bool
        yaw_delta     float  degrees/step
        pitch_delta   float  degrees/step
        ...

    Joint mapping: default = two-wheel differential drive.
    Override _controls_to_joints() for your robot's kinematics.

    Usage:
        actuator = IsaacSimActuator("/World/Robots/Agent0", "/World/Robots/Agent0/Camera")
        # After world.reset():
        actuator.initialize()
        # Each step:
        actuator.apply(agent.act(obs))
        state = actuator.get_state()
    """

    def __init__(
        self,
        robot_prim_path:  str,
        camera_prim_path: str,
        stiffness:        float = 1000.0,
        damping:          float = 100.0,
        force_limit:      float = 1000.0,
    ):
        _require_isaac("IsaacSimActuator")

        self.robot_prim_path  = robot_prim_path
        self.camera_prim_path = camera_prim_path
        self.stiffness        = stiffness
        self.damping          = damping
        self.force_limit      = force_limit

        prim_utils = _import_prims_utils()
        self.robot_prim  = prim_utils.get_prim_at_path(robot_prim_path)
        self.camera_prim = prim_utils.get_prim_at_path(camera_prim_path)

        self.articulation: Optional[Any] = None
        self._ArticulationAction          = _import_articulation_action()
        self._initialized                 = False

    def initialize(self):
        """
        Bind the articulation to physics.
        MUST be called after world.reset() — PhysX ArticulationView
        is only available once the simulation has been stepped once.
        Safe to call multiple times (no-op after first call).
        """
        if self._initialized:
            return

        self.articulation = _import_articulation(self.robot_prim_path)

        # Isaac Sim 5.0: SingleArticulation.initialize() connects to the
        # PhysX backend. physics_sim_view=None is fine for single-world use.
        try:
            self.articulation.initialize()
        except TypeError:
            # Some older 4.x builds have a different initialize() signature
            try:
                self.articulation.initialize(physics_sim_view=None)
            except Exception as exc:
                log.warning(f"Articulation initialize() failed: {exc} — continuing")

        # Disable kinematic mode so PhysX drives the robot
        try:
            self.robot_prim.GetAttribute("physics:kinematic").Set(False)
        except Exception as exc:
            log.debug(f"Could not clear physics:kinematic: {exc}")

        self._initialized = True
        log.info(f"IsaacSimActuator initialised: {self.robot_prim_path}  "
                 f"DOFs={getattr(self.articulation, 'num_dof', '?')}")

    def apply(self, controls: Dict[str, Any]):
        """
        Apply one NPCAgent controls dict to the robot for the next physics step.

        Isaac Sim 5.0: apply_action(ArticulationAction(joint_positions=...))
        replaces the removed apply_dof_position_targets().

        FIX (GitHub #320): Only pass joint_positions — do NOT pass joint_velocities
        as None when using the torch backend, as that causes a TypeError inside
        the ArticulationController. Pass only the field you intend to set.
        """
        if not self._initialized or self.articulation is None:
            return

        joint_targets = self._controls_to_joints(controls)

        if self._ArticulationAction is not None:
            try:
                action = self._ArticulationAction(joint_positions=joint_targets)
                self.articulation.apply_action(action)
            except Exception as exc:
                log.debug(f"apply_action failed: {exc}")
        else:
            # Last-resort fallback for very old API
            try:
                self.articulation.set_joint_position_targets(joint_targets)
            except Exception as exc:
                log.debug(f"set_joint_position_targets fallback failed: {exc}")

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
        """
        Return current joint positions and velocities.

        Isaac Sim 5.0: get_joint_positions() / get_joint_velocities()
        replaces get_dof_states() which returned a combined (N,2) array.
        """
        if not self._initialized or self.articulation is None:
            return {"joint_positions": np.zeros(1), "joint_velocities": np.zeros(1)}
        try:
            return {
                "joint_positions":  np.asarray(
                    self.articulation.get_joint_positions()),
                "joint_velocities": np.asarray(
                    self.articulation.get_joint_velocities()),
            }
        except Exception as exc:
            log.debug(f"get_state error: {exc}")
            return {"joint_positions": np.zeros(1), "joint_velocities": np.zeros(1)}

    def _controls_to_joints(self, controls: Dict[str, Any]) -> np.ndarray:
        """
        Map NPCAgent controls to joint position targets.
        Default: two-wheel differential drive approximation.
        Override for your specific robot kinematics.

        For velocity-controlled joints (stiffness=0, damping≠0):
        pass ArticulationAction(joint_velocities=targets) in apply() instead.
        """
        if self.articulation is None:
            return np.zeros(2)
        try:
            n_dof = int(self.articulation.num_dof)
        except Exception:
            n_dof = 2

        targets = np.zeros(n_dof, dtype=np.float32)
        if n_dof >= 2:
            fwd    = float(controls.get("move_forward", 0.0))
            strafe = float(controls.get("move_strafe",  0.0))
            # Differential drive: L = fwd - strafe, R = fwd + strafe
            targets[0] = fwd - strafe
            targets[1] = fwd + strafe
        return targets


# ---------------------------------------------------------------------------
# IsaacSimIntegration
# ---------------------------------------------------------------------------

class IsaacSimIntegration:
    """
    Manages one or more NPCAgents running inside an Isaac Sim 5.0 world.

    Usage:
        sim = IsaacSimIntegration(
            watch_folder="dw_agents_sim",
            robot_asset_path="omniverse://localhost/NVIDIA/Assets/..."
        )
        sim.start_sim_agent("Adam", Path("npc_applications/Adam"))
        sim.start_training("Adam", num_episodes=100)
    """

    def __init__(
        self,
        watch_folder:       str  = "dw_agents_sim",
        robot_asset_path:   str  = "",
        poll_interval_secs: float = 5.0,
    ):
        _require_isaac("IsaacSimIntegration")

        self.watch_folder   = Path(watch_folder)
        self.robot_asset    = robot_asset_path
        self._poll_interval = poll_interval_secs

        self._active:   Dict[str, Dict[str, Any]] = {}
        self._episodes: Dict[str, List[float]]    = {}
        self._seen_dirs: set                       = set()
        self._stop_event                           = threading.Event()

        # Stage reference — obtained lazily in start_sim_agent
        self.stage = None

        # Isaac Sim 5.0: get stage via omni.usd (Omniverse Kit API unchanged)
        try:
            import omni.usd
            self.stage = omni.usd.get_context().get_stage()
        except Exception as exc:
            log.debug(f"Stage not available yet: {exc}")

        # Start folder watcher thread
        self._watcher = threading.Thread(
            target=self._poll_watch_folder, daemon=True, name="DW-IsaacWatcher"
        )
        self._watcher.start()
        log.info(f"IsaacSimIntegration watching: {self.watch_folder}")

    # ------------------------------------------------------------------
    # Folder watcher
    # ------------------------------------------------------------------

    def _poll_watch_folder(self):
        """
        Poll watch_folder for new agent subdirectories (simple, no carb.events).
        Replaces the broken carb.events.Type.FILESYSTEM approach.
        """
        while not self._stop_event.is_set():
            try:
                if self.watch_folder.is_dir():
                    for entry in self.watch_folder.iterdir():
                        if entry.is_dir() and entry not in self._seen_dirs:
                            self._seen_dirs.add(entry)
                            agent_id = entry.name
                            log.info(f"[Watcher] New agent directory: {agent_id}")
                            self.start_sim_agent(agent_id, entry)
            except Exception as exc:
                log.debug(f"[Watcher] Error: {exc}")
            self._stop_event.wait(self._poll_interval)

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def start_sim_agent(self, agent_id: str, agent_dir: Path):
        """Load an NPCAgent into the simulation."""
        if agent_id in self._active:
            log.warning(f"Agent {agent_id} already in sim")
            return

        brain_path = agent_dir / "brain.pcap"
        if not brain_path.exists():
            log.warning(f"No brain found for {agent_id} at {brain_path}")
            return

        try:
            import omni.kit.commands

            if self.stage is None:
                try:
                    import omni.usd
                    self.stage = omni.usd.get_context().get_stage()
                except Exception as exc:
                    log.error(f"Could not get USD stage: {exc}")
                    return

            robot_path = f"/World/Robots/{agent_id}"

            # ── Create robot USD reference ────────────────────────────────
            omni.kit.commands.execute(
                "CreateReference",
                path=robot_path,
                asset_path=self.robot_asset,
                usd_context=self.stage,
            )

            # ── Camera prim ───────────────────────────────────────────────
            # FIX: "CreateCamera" was removed in Isaac Sim 5.0.
            # Use "CreatePrimWithDefaultXform" (Kit 106+) which is stable.
            camera_path = f"{robot_path}/Camera"
            try:
                omni.kit.commands.execute(
                    "CreatePrimWithDefaultXform",
                    prim_type="Camera",
                    prim_path=camera_path,
                )
            except Exception:
                # Fallback for older Kit SDK versions still on the system
                try:
                    omni.kit.commands.execute(
                        "CreatePrim",
                        prim_path=camera_path,
                        prim_type="Camera",
                    )
                except Exception as exc:
                    log.warning(f"Camera creation failed: {exc} — vision may be unavailable")

            # ── Load agent brain ──────────────────────────────────────────
            from ai_core.agent import NPCAgent
            agent = NPCAgent(agent_id)
            agent.load(str(brain_path))

            # ── Wire VisionAdapter ────────────────────────────────────────
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
            if hasattr(agent, "vision") and agent.vision is not None:
                agent.vision.attach_isaac_camera(camera_path)
            else:
                log.warning(f"[{agent_id}] VisionAdapter not attached")

            # ── Create actuator ───────────────────────────────────────────
            actuator = IsaacSimActuator(
                robot_prim_path=robot_path,
                camera_prim_path=camera_path,
            )
            # NOTE: actuator.initialize() is deferred until _training_loop()
            # calls world.reset() — SingleArticulation.initialize() requires
            # a PhysX ArticulationView which only exists after reset.

            self._active[agent_id] = {
                "agent":      agent,
                "actuator":   actuator,
                "robot_path": robot_path,
                "training":   False,
                "agent_dir":  agent_dir,
            }
            self._episodes[agent_id] = []
            log.info(
                f"✅ {agent_id} ready in sim — "
                f"robot={robot_path}  brain={brain_path}"
            )

        except Exception as exc:
            log.exception(f"Failed to start {agent_id}: {exc}")
            self._cleanup_agent(agent_id)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def start_training(
        self,
        agent_id:   str,
        num_episodes: int = 100,
        reward_fn:  Optional[Callable[[str], float]] = None,
        done_fn:    Optional[Callable[[str], bool]]  = None,
    ):
        """
        Run num_episodes training episodes for agent_id.

        reward_fn(agent_id) → float   — task-specific reward (optional)
        done_fn(agent_id)   → bool    — episode termination  (optional)
        Falls back to _default_reward / _default_done if not provided.
        """
        if agent_id not in self._active:
            log.error(f"Agent {agent_id} not found — call start_sim_agent first")
            return
        info = self._active[agent_id]
        if info["training"]:
            log.warning(f"Agent {agent_id} already training")
            return

        info["training"] = True
        asyncio.ensure_future(
            self._training_loop(
                agent_id, num_episodes,
                reward_fn or self._default_reward,
                done_fn   or self._default_done,
            )
        )

    async def _training_loop(
        self,
        agent_id:    str,
        num_episodes: int,
        reward_fn:   Callable,
        done_fn:     Callable,
    ):
        info     = self._active[agent_id]
        agent    = info["agent"]
        actuator = info["actuator"]

        self._episodes[agent_id] = []

        # Isaac Sim 5.0: get the World instance and reset physics before
        # calling actuator.initialize() — SingleArticulation.initialize()
        # requires an active PhysX ArticulationView.
        try:
            try:
                from isaacsim.core.world import World
            except ImportError:
                from omni.isaac.core.world import World  # type: ignore
            world = World.instance()
            if world is not None:
                world.reset()
                log.info(f"[{agent_id}] World reset — initialising actuator")
        except Exception as exc:
            log.warning(f"[{agent_id}] World reset failed: {exc} — continuing without reset")

        actuator.initialize()

        for episode in range(num_episodes):
            if agent_id not in self._active:
                break

            done             = False
            episode_rewards: List[float] = []

            while not done:
                # Collect state
                state   = actuator.get_state()
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
                agent.perceive(raw_obs)

                # Plan and act
                action_arr = np.zeros(11, dtype=np.float32)
                try:
                    if (hasattr(agent, "planner") and agent.planner
                            and hasattr(agent, "memory")):
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
                actuator.apply(controls)

                # Isaac Sim 5.0: write buffered actions to PhysX then step
                # write_data_to_sim() and world.step() are the correct sequence.
                try:
                    try:
                        from isaacsim.core.world import World
                    except ImportError:
                        from omni.isaac.core.world import World  # type: ignore
                    w = World.instance()
                    if w is not None:
                        w.step(render=False)
                except Exception as exc:
                    log.debug(f"world.step() error: {exc}")

                # Reward
                reward = reward_fn(agent_id)
                episode_rewards.append(reward)

                if agent.reward_system is not None:
                    try:
                        agent.reward_system.update(
                            event_type="sim_step",
                            outcome={"reward": reward},
                        )
                    except Exception:
                        pass

                done = done_fn(agent_id)
                await asyncio.sleep(0)

            total = sum(episode_rewards)
            self._episodes[agent_id].append(total)
            log.info(
                f"[{agent_id}] Episode {episode + 1}/{num_episodes} — "
                f"reward: {total:.3f}"
            )

            if (episode + 1) % 10 == 0:
                self._save_agent(agent_id)

        info["training"] = False
        self._save_agent(agent_id)
        log.info(f"✅ Training complete for {agent_id}")

    # ------------------------------------------------------------------
    # Default reward / done hooks (override via start_training kwargs)
    # ------------------------------------------------------------------

    def _default_reward(self, agent_id: str) -> float:
        """Placeholder reward — always 0. Pass reward_fn= to start_training()."""
        return 0.0

    def _default_done(self, agent_id: str) -> bool:
        """Placeholder done — never terminates. Pass done_fn= to start_training()."""
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_agent(self, agent_id: str):
        if agent_id not in self._active:
            return
        info  = self._active[agent_id]
        try:
            info["agent"].save(str(info["agent_dir"] / "brain.pcap"))
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
        info = self._active.pop(agent_id)
        self._episodes.pop(agent_id, None)
        try:
            import omni.kit.commands
            omni.kit.commands.execute(
                "DeletePrims",
                paths=[info["robot_path"]],
                destructive=True,
            )
        except Exception as exc:
            log.debug(f"Error deleting {info['robot_path']}: {exc}")
        log.info(f"Cleaned up {agent_id}")

    def cleanup_all(self):
        """Stop watcher thread and remove all agents from the sim."""
        self._stop_event.set()
        for agent_id in list(self._active.keys()):
            self._cleanup_agent(agent_id)
        log.info("IsaacSimIntegration shut down")


# ---------------------------------------------------------------------------
# Minimal sanity test (no Isaac Sim required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import unittest.mock as mock
    logging.basicConfig(level=logging.DEBUG)

    print("Testing IsaacSimActuator._controls_to_joints() — no Isaac Sim needed…")
    with mock.patch("isaac_sim_integration._require_isaac"), \
         mock.patch("isaac_sim_integration._import_prims_utils") as m_prims, \
         mock.patch("isaac_sim_integration._import_articulation_action", return_value=None):
        m_prims.return_value = mock.MagicMock()
        act = IsaacSimActuator("/World/Robot", "/World/Robot/Camera")

        class _FakeArt:
            num_dof = 4

        act.articulation  = _FakeArt()
        act._initialized  = True

        controls = {"move_forward": 1.0, "move_strafe": 0.3}
        targets  = act._controls_to_joints(controls)
        print(f"  4-DOF targets: {targets}  (expected first 2 ≈ [0.7, 1.3])")
        assert abs(targets[0] - 0.7) < 1e-5, f"L={targets[0]}"
        assert abs(targets[1] - 1.3) < 1e-5, f"R={targets[1]}"

    print("✅ Unit test passed")