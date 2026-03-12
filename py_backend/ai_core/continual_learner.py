# ai_core/continual_learner.py
"""
Avalanche Continual Learning Integration
=========================================
Implements lifelong learning using Avalanche library.
Prevents catastrophic forgetting while learning new tasks.

Uses:
- Experience Replay (ER)
- Elastic Weight Consolidation (EWC)
- Learning without Forgetting (LwF)
- Progressive Neural Networks (PNN)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import logging

try:
    from avalanche.benchmarks.utils import AvalancheTensorDataset
    from avalanche.training.supervised.strategy_wrappers import Naive, Replay, EWC, LwF
    from avalanche.models import SimpleMLP
    from avalanche.evaluation.metrics import accuracy_metrics, loss_metrics
    from avalanche.logging import InteractiveLogger
    from avalanche.training.plugins import EvaluationPlugin
    AVALANCHE_AVAILABLE = True
except ImportError:
    AVALANCHE_AVAILABLE = False

log = logging.getLogger("continual_learner")


class PolicyNetwork(nn.Module):
    """
    Policy network compatible with Avalanche.
    Predicts actions from observations.
    """
    
    def __init__(self, obs_dim: int = 50, action_dim: int = 11, hidden_dim: int = 256):
        super().__init__()
        
        self.network = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
            
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            
            nn.Linear(hidden_dim // 2, action_dim),
            nn.Tanh()  # Actions in [-1, 1]
        )
    
    def forward(self, x):
        return self.network(x)


class ValueNetwork(nn.Module):
    """Value function for critic"""
    
    def __init__(self, obs_dim: int = 50, hidden_dim: int = 256):
        super().__init__()
        
        self.network = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            
            nn.Linear(hidden_dim // 2, 1)
        )
    
    def forward(self, x):
        return self.network(x)


class ContinualLearner:
    """
    Avalanche-based continual learning for NPCAgent.
    Manages lifelong learning without catastrophic forgetting.
    """
    
    def __init__(self, agent, strategy: str = 'replay', 
                 hidden_dim: int = 256, memory_size: int = 2000):
        
        if not AVALANCHE_AVAILABLE:
            raise RuntimeError("Avalanche not installed. Install with: pip install avalanche-lib")
        
        self.agent = agent
        self.strategy_name = strategy
        self.hidden_dim = hidden_dim
        self.memory_size = memory_size
        
        # Dimensions
        self.obs_dim = 50
        self.action_dim = 11
        
        # Networks
        self.policy_net = PolicyNetwork(self.obs_dim, self.action_dim, hidden_dim)
        self.value_net = ValueNetwork(self.obs_dim, hidden_dim)
        
        # Avalanche components
        self.strategy = None
        self.eval_plugin = None
        
        # Task tracking
        self.current_task_id = 0
        self.task_history: List[int] = []
        
        # Experience buffer for Avalanche
        self.experience_buffer: List[Tuple] = []
        
        # Statistics
        self.stats = {
            'tasks_learned': 0,
            'total_updates': 0,
            'avg_loss': 0.0,
            'forgetting_measure': 0.0
        }
        
        self._init_avalanche_strategy()
        
        log.info(f"ContinualLearner initialized with {strategy} strategy")
    
    def _init_avalanche_strategy(self):
        """Initialize Avalanche training strategy"""
        
        # Optimizer
        optimizer = torch.optim.Adam([
            {'params': self.policy_net.parameters(), 'lr': 3e-4},
            {'params': self.value_net.parameters(), 'lr': 1e-3}
        ])
        
        # Loss criterion
        criterion = nn.MSELoss()
        
        # Evaluation plugin
        self.eval_plugin = EvaluationPlugin(
            accuracy_metrics(minibatch=True, epoch=True, experience=True, stream=True),
            loss_metrics(minibatch=True, epoch=True, experience=True, stream=True),
            loggers=[InteractiveLogger()]
        )
        
        # Select strategy
        if self.strategy_name == 'naive':
            self.strategy = Naive(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )
            
        elif self.strategy_name == 'replay':
            self.strategy = Replay(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                mem_size=self.memory_size,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )
            
        elif self.strategy_name == 'ewc':
            self.strategy = EWC(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                ewc_lambda=0.4,  # EWC regularization strength
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )
            
        elif self.strategy_name == 'lwf':
            self.strategy = LwF(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                alpha=1.0,  # Distillation weight
                temperature=2.0,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )
        else:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")
        
        log.info(f"Avalanche strategy initialized: {self.strategy_name}")
    
    def collect_experiences(self, min_batch_size: int = 32) -> bool:
        buffer = list(getattr(self.agent.brain, 'continual_buffer', []))
        if len(buffer) < min_batch_size:
            return False
        templates = ['collect','craft','attack','flee','use_item',
                    'explore','eat','sleep','build','trade','interact']
        for exp in buffer:
            context = exp.get('context') or {}
            event   = exp.get('event', {})
            # Build obs vector from context
            obs_list = [
                context.get('health', 20.0) / 20.0,
                context.get('hunger', 20.0) / 20.0,
            ] + [0.0] * (self.obs_dim - 2)
            obs = torch.tensor(obs_list[:self.obs_dim], dtype=torch.float32)
            # Build action vector from event type
            action_vec = [0.0] * self.action_dim
            etype = event.get('type', '')
            if etype in templates:
                action_vec[templates.index(etype) % self.action_dim] = 1.0
            action   = torch.tensor(action_vec, dtype=torch.float32)
            task_id  = exp.get('task', self.current_task_id)
            reward   = float(exp.get('reward', 0.0))
            self.experience_buffer.append((obs, action, reward, obs, False, task_id))
        return len(self.experience_buffer) >= min_batch_size
    
    def learn_from_buffer(self, epochs: int = 1) -> Dict[str, float]:
        """
        Perform continual learning update from collected experiences.
        Returns metrics dict.
        """
        if not self.collect_experiences():
            return {'status': 'insufficient_data'}
        
        try:
            # Convert buffer to Avalanche dataset
            dataset = self._create_avalanche_dataset()
            
            # Train on experience
            results = self.strategy.train(dataset, num_workers=0)
            
            # Update statistics
            self.stats['total_updates'] += 1
            
            # Extract metrics
            metrics = {
                'status': 'success',
                'updates': self.stats['total_updates'],
                'task_id': self.current_task_id,
                'buffer_size': len(self.experience_buffer)
            }
            
            # Clear processed experiences
            self.experience_buffer.clear()
            
            log.info(f"Continual learning update complete: {metrics}")
            
            return metrics
            
        except Exception as e:
            log.error(f"Continual learning failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
    
    def _create_avalanche_dataset(self):
        """Create Avalanche dataset from experience buffer"""
        # Extract observations and actions
        observations = []
        actions = []
        task_labels = []
        
        for obs, action, reward, next_obs, done, task_id in self.experience_buffer:
            observations.append(obs)
            actions.append(action)
            task_labels.append(task_id)
        
        # Stack into tensors
        obs_tensor = torch.stack(observations)
        action_tensor = torch.stack(actions)
        task_tensor = torch.tensor(task_labels, dtype=torch.long)
        
        # Create Avalanche dataset
        dataset = AvalancheTensorDataset(
            obs_tensor,
            action_tensor,
            task_labels=task_tensor
        )
        
        return dataset
    
    def switch_task(self, new_task_id: int):
        """Switch to a new learning task"""
        if new_task_id != self.current_task_id:
            log.info(f"Switching task: {self.current_task_id} → {new_task_id}")
            
            # Store old task
            self.task_history.append(self.current_task_id)
            
            # Update task
            self.current_task_id = new_task_id
            self.agent.brain.current_task = new_task_id
            
            # Update statistics
            self.stats['tasks_learned'] = len(set(self.task_history))
    
    def predict_action(self, observation: torch.Tensor) -> torch.Tensor:
        """Use learned policy to predict action"""
        self.policy_net.eval()
        with torch.no_grad():
            action = self.policy_net(observation)
        return action
    
    def predict_value(self, observation: torch.Tensor) -> torch.Tensor:
        """Use value network to estimate state value"""
        self.value_net.eval()
        with torch.no_grad():
            value = self.value_net(observation)
        return value
    
    def save(self, path: str):
        """Save continual learning state"""
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            'policy_net': self.policy_net.state_dict(),
            'value_net': self.value_net.state_dict(),
            'current_task_id': self.current_task_id,
            'task_history': self.task_history,
            'stats': self.stats,
            'strategy_name': self.strategy_name
        }
        
        torch.save(state, save_path)
        log.info(f"Continual learner saved to {save_path}")
    
    def load(self, path: str):
        """Load continual learning state"""
        save_path = Path(path)
        
        if not save_path.exists():
            log.warning(f"No saved state found at {save_path}")
            return
        
        state = torch.load(save_path, map_location='cpu')
        
        self.policy_net.load_state_dict(state['policy_net'])
        self.value_net.load_state_dict(state['value_net'])
        self.current_task_id = state['current_task_id']
        self.task_history = state['task_history']
        self.stats = state['stats']
        
        log.info(f"Continual learner loaded from {save_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return {
            **self.stats,
            'current_task': self.current_task_id,
            'tasks_seen': len(set(self.task_history)),
            'buffer_size': len(self.experience_buffer),
            'strategy': self.strategy_name
        }


# Convenience function for agent integration
def add_continual_learning(agent, strategy: str = 'replay', **kwargs):
    """
    Add continual learning capabilities to an agent.
    
    Usage:
        from ai_core.continual_learner import add_continual_learning
        add_continual_learning(agent, strategy='replay')
    """
    if not AVALANCHE_AVAILABLE:
        log.warning("Avalanche not available - continual learning disabled")
        return None
    
    learner = ContinualLearner(agent, strategy=strategy, **kwargs)
    agent.continual_learner = learner
    
    log.info(f"Continual learning added to {agent.agent_id}")
    return learner