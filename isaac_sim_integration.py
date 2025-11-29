# -----------------------------------------------------------------------------
# isaac_sim_integration.py - Complete ISAAC SIM COMPATIBILITY
# -----------------------------------------------------------------------------

import logging
from pathlib import Path
from typing import List, Dict, Optional, Callable
import numpy as np
import carb
import omni

from ai_core.agent import NPCAgent
from ai_core.actuators import ActuatorAdapterBase
from ai_core.vision import VisionSystem

log = logging.getLogger("isaac_sim")

class IsaacSimActuator(ActuatorAdapterBase):
    """Actuator for controlling agents in Isaac Sim"""
    
    def __init__(self, 
                 robot_prim_path: str,
                 articulation_controller,
                 camera_prim_path: str,
                 camera_controller):
        self.robot_prim = omni.isaac.core.utils.prims.get_prim_at_path(robot_prim_path)
        self.articulation = articulation_controller
        self.camera_prim = omni.isaac.core.utils.prims.get_prim_at_path(camera_prim_path)
        self.camera_controller = camera_controller
        
        # Cache joint info
        self.joint_positions = np.zeros(self.articulation.num_dof)
        self.joint_velocities = np.zeros(self.articulation.num_dof)
        
        self.initialized = False
        
    def initialize(self):
        """Called when agent starts"""
        if not self.initialized:
            # Reset robot state
            self.articulation.reset_dof_states()
            
            # Enable physics simulation
            self.robot_prim.GetAttribute("physics:kinematic").Set(False)
            self.initialized = True
    
    def step(self, action: Dict):
        """Execute one simulation step"""
        if not self.initialized:
            return
            
        # Get target joint positions
        target_positions = action.get('joint_positions')
        if target_positions is not None:
            self.joint_positions[:] = target_positions
            
        # Apply PD control
        self.articulation.apply_dof_position_targets(
            positions=self.joint_positions,
            stiffness=1000.0,
            damping=100.0,
            force_limits=1000.0
        )
        
        # Update camera if requested
        camera_angles = action.get('camera_angles')
        if camera_angles is not None:
            yaw, pitch = camera_angles
            
            # Apply camera rotation
            xform = self.camera_prim.GetAttribute("xformOp:rotateXYZ")
            xform.Set((pitch, yaw, 0.0))
    
    def get_state(self) -> Dict:
        """Get current robot state"""
        if not self.initialized:
            return {}
            
        # Get current joint states
        dof_states = self.articulation.get_dof_states()
        self.joint_positions = dof_states[:, 0]
        self.joint_velocities = dof_states[:, 1]
        
        return {
            'joint_positions': self.joint_positions.copy(),
            'joint_velocities': self.joint_velocities.copy()
        }


class IsaacSimVision(VisionSystem):
    """Vision processing for Isaac Sim"""
    
    def __init__(self, camera_prim_path: str):
        super().__init__()
        
        from omni.isaac.synthetic_utils import SyntheticDataHelper
        self.sd_helper = SyntheticDataHelper()
        
        self.camera = omni.isaac.core.utils.prims.get_prim_at_path(camera_prim_path)
        self.camera_viewport = omni.kit.viewport.get_viewport_interface()
        
    def get_camera_image(self) -> Optional[np.ndarray]:
        """Get RGB image from simulation camera"""
        groundtruth = self.sd_helper.get_groundtruth(
            ["rgb"], 
            self.camera, 
            verify_sensor_init=True,
            wait_for_sensor_data=True
        )
        
        if groundtruth["rgb"] is not None:
            return groundtruth["rgb"].astype(np.uint8)
        return None
    
    def get_depth_image(self) -> Optional[np.ndarray]:
        """Get depth image from simulation camera"""
        groundtruth = self.sd_helper.get_groundtruth(
            ["depth"], 
            self.camera,
            verify_sensor_init=True,
            wait_for_sensor_data=True
        )
        
        if groundtruth["depth"] is not None:
            # Convert to meters
            return groundtruth["depth"].astype(np.float32)
        return None


class IsaacSimIntegration:
    """
    Complete Isaac Sim integration for AI agents.
    Handles:
    - Detecting agents moved to sim folder
    - Loading and initializing agents in simulation
    - Running training episodes
    - Collecting experience data
    """
    
    def __init__(self, 
                 isaac_sim_folder: str,
                 robot_asset_path: str,
                 stage = None):
        self.isaac_folder = Path(isaac_sim_folder)
        self.robot_asset = robot_asset_path
        self.stage = stage or omni.usd.get_context().get_stage()
        
        self.active_sim_agents: Dict[str, Dict] = {}
        self.training_episodes: Dict[str, List] = {}
        
        # Create agents folder if needed
        self.isaac_folder.mkdir(parents=True, exist_ok=True)
        
        # Start folder watcher
        self._setup_folder_watcher()
        
        log.info(f"Isaac Sim integration initialized")
        log.info(f"Watching folder: {self.isaac_folder}")
    
    def _setup_folder_watcher(self):
        """Watch for new agents in sim folder"""
        import carb.events
        
        self._subscription = None
        
        def on_folder_event(event):
            if event.type == carb.events.Type.FILESYSTEM and event.payload.action == "created":
                path = Path(event.payload.path)
                if path.parent == self.isaac_folder and path.name.startswith("DW_Agent_"):
                    agent_id = path.name.replace("DW_Agent_", "")
                    self.start_sim_agent(agent_id, path)
        
        self._subscription = omni.kit.app.get_app().get_message_bus_event_stream().create_subscription_to_pop_by_type(
            carb.events.Type.FILESYSTEM, 
            on_folder_event
        )
    
    def start_sim_agent(self, agent_id: str, agent_dir: Path):
        """
        Start agent in Isaac Sim environment.
        Creates robot, sensors, and initializes training.
        """
        if agent_id in self.active_sim_agents:
            log.warning(f"Agent {agent_id} already active in simulation")
            return
            
        try:
            # Load agent brain
            brain_path = agent_dir / "brain.pcap"
            if not brain_path.exists():
                log.error(f"No brain file found for {agent_id}")
                return
                
            # Create robot in stage
            robot_path = f"/World/Robots/{agent_id}"
            omni.kit.commands.execute('CreateReference',
                path=robot_path,
                asset_path=self.robot_asset,
                usd_context=self.stage
            )
            
            # Add camera
            camera_path = f"{robot_path}/Camera"
            omni.kit.commands.execute('CreateCamera',
                path=camera_path,
                parent_path=robot_path
            )
            
            # Get articulation controller
            from omni.isaac.core.articulations import ArticulationController
            art_controller = ArticulationController(
                prim_path=robot_path,
                joint_names=["*"],
                actuation_mode="position"
            )
            
            # Create actuator & vision
            actuator = IsaacSimActuator(
                robot_prim_path=robot_path,
                articulation_controller=art_controller,
                camera_prim_path=camera_path,
                camera_controller=None  # TODO: implement camera controller
            )
            
            vision = IsaacSimVision(camera_prim_path=camera_path)
            
            # Initialize agent
            agent = NPCAgent(agent_id)
            agent.load(str(brain_path))
            agent.set_actuator(actuator)
            agent.set_vision(vision)
            
            # Store agent info
            self.active_sim_agents[agent_id] = {
                'agent': agent,
                'actuator': actuator,
                'vision': vision,
                'robot_path': robot_path,
                'training': False
            }
            
            # Initialize training episodes
            self.training_episodes[agent_id] = []
            
            log.info(f"Started {agent_id} in Isaac Sim")
            log.info(f"Robot path: {robot_path}")
            
        except Exception as e:
            log.error(f"Failed to start {agent_id} in sim: {e}")
            self.cleanup_agent(agent_id)
    
    def start_training(self, agent_id: str, num_episodes: int = 100):
        """Start training episodes for agent"""
        if agent_id not in self.active_sim_agents:
            log.error(f"Agent {agent_id} not found in simulation")
            return
            
        agent_info = self.active_sim_agents[agent_id]
        if agent_info['training']:
            log.warning(f"Agent {agent_id} already training")
            return
            
        agent_info['training'] = True
        agent = agent_info['agent']
        actuator = agent_info['actuator']
        
        # Reset episode counter
        self.training_episodes[agent_id] = []
        
        async def training_loop():
            episode = 0
            while episode < num_episodes:
                # Reset environment
                actuator.initialize()
                
                # Run episode
                done = False
                episode_rewards = []
                
                while not done:
                    # Get agent observation
                    obs = self._get_observation(agent_id)
                    
                    # Agent selects action
                    action = agent.get_action(obs)
                    
                    # Execute in sim
                    actuator.step(action)
                    
                    # Calculate reward
                    reward = self._calculate_reward(agent_id)
                    episode_rewards.append(reward)
                    
                    # Check termination
                    done = self._check_episode_done(agent_id)
                    
                    # Store transition
                    agent.store_transition(obs, action, reward, done)
                
                # Episode complete
                total_reward = sum(episode_rewards)
                self.training_episodes[agent_id].append(total_reward)
                
                log.info(f"Episode {episode} complete for {agent_id}")
                log.info(f"Total reward: {total_reward:.2f}")
                
                # Update agent
                agent.update()
                episode += 1
                
                # Save periodically
                if episode % 10 == 0:
                    agent.save()
            
            # Training complete
            agent_info['training'] = False
            log.info(f"Training complete for {agent_id}")
            
        # Start training loop
        import asyncio
        asyncio.ensure_future(training_loop())
    
    def _get_observation(self, agent_id: str) -> Dict:
        """Get current observation for agent"""
        agent_info = self.active_sim_agents[agent_id]
        
        # Get vision
        vision = agent_info['vision']
        rgb = vision.get_camera_image()
        depth = vision.get_depth_image()
        
        # Get robot state
        actuator = agent_info['actuator'] 
        robot_state = actuator.get_state()
        
        return {
            'rgb': rgb,
            'depth': depth,
            'joint_positions': robot_state['joint_positions'],
            'joint_velocities': robot_state['joint_velocities']
        }
    
    def _calculate_reward(self, agent_id: str) -> float:
        """Calculate reward for current state"""
        # TODO: Implement task-specific reward function
        return 0.0
    
    def _check_episode_done(self, agent_id: str) -> bool:
        """Check if episode should terminate"""
        # TODO: Implement termination conditions
        return False
    
    def cleanup_agent(self, agent_id: str):
        """Remove agent from simulation"""
        if agent_id in self.active_sim_agents:
            try:
                # Delete robot from stage
                robot_path = self.active_sim_agents[agent_id]['robot_path']
                omni.kit.commands.execute('DeletePrims',
                    paths=[robot_path],
                    destructive=True
                )
            except Exception as e:
                log.error(f"Error cleaning up {agent_id}: {e}")
            
            # Remove from active agents
            del self.active_sim_agents[agent_id]
            if agent_id in self.training_episodes:
                del self.training_episodes[agent_id]
    
    def cleanup_all(self):
        """Clean up all agents"""
        for agent_id in list(self.active_sim_agents.keys()):
            self.cleanup_agent(agent_id)
            
        if self._subscription:
            self._subscription = None


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create integration
    sim = IsaacSimIntegration(
        isaac_sim_folder="dw_agents_sim",
        robot_asset_path="omniverse://localhost/NVIDIA/Assets/Isaac/2023.1/Isaac/Robots/Carter/carter_v1.usd"
    )
    
    try:
        # Keep running
        while True:
            sim.detect_agent_in_sim_folder()
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sim.cleanup_all()
