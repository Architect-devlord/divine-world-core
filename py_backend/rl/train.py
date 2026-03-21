# ------------------------------------------------------------------------------
# rl/train.py - Training script
# ------------------------------------------------------------------------------
"""
Training script using Stable-Baselines3 PPO with custom policy.
"""
import os
import argparse
from pathlib import Path
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback

# FIX P-01: bare 'from env import' / 'from policy import' fail when the script
# is run as 'python rl/train.py' from the project root because rl/ is not on
# sys.path.  Insert rl/'s own directory so the relative siblings resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).parent))         # adds rl/ → env, policy visible
_sys.path.insert(0, str(_Path(__file__).parent.parent))  # adds project root → ai_core visible

from ai_core import NPCAgent
from env import DivineWorldEnv
from policy import TransformerPolicy


def make_env(agent_id: str, rank: int = 0):
    """Create environment factory"""
    def _init():
        agent = NPCAgent(f'{agent_id}_{rank}')
        env = DivineWorldEnv(agent, render_mode=None)
        return env
    return _init


def train_agent(
    agent_id: str = 'train_agent',
    total_timesteps: int = 500_000,
    n_envs: int = 4,
    save_path: str = './models/dw_agent',
    tensorboard_log: str = './tb_logs',
    eval_freq: int = 10_000
):
    """
    Train agent using PPO with custom transformer policy.
    """
    print(f"[Train] Starting training for {agent_id}")
    print(f"  Total timesteps: {total_timesteps}")
    print(f"  Parallel envs: {n_envs}")
    
    # Create save directory
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Create vectorized environments
    if n_envs > 1:
        env = SubprocVecEnv([make_env(agent_id, i) for i in range(n_envs)])
    else:
        env = DummyVecEnv([make_env(agent_id, 0)])
    
    # Create eval environment
    eval_env = DummyVecEnv([make_env(f'{agent_id}_eval', 0)])
    
    # Callbacks
    checkpoint_callback = CheckpointCallback(
        save_freq=10_000,
        save_path=os.path.dirname(save_path),
        name_prefix='checkpoint'
    )
    
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.dirname(save_path),
        log_path=os.path.dirname(save_path),
        eval_freq=eval_freq,
        deterministic=True,
        render=False
    )
    
    # Create PPO model with custom policy
    model = PPO(
        policy=TransformerPolicy,
        env=env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        verbose=1,
        tensorboard_log=tensorboard_log,
        policy_kwargs={
            'd_model': 128,
            'nhead': 4,
            'num_layers': 2
        }
    )
    
    print("[Train] Model created, starting training...")
    
    # Train
    model.learn(
        total_timesteps=total_timesteps,
        callback=[checkpoint_callback, eval_callback],
        progress_bar=True
    )
    
    # Save final model
    model.save(save_path)
    print(f"[Train] Model saved to {save_path}")
    
    # Cleanup
    env.close()
    eval_env.close()
    
    return model


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train Divine World Agent')
    parser.add_argument('--agent-id', type=str, default='dw_agent',
                       help='Agent identifier')
    parser.add_argument('--timesteps', type=int, default=500_000,
                       help='Total training timesteps')
    parser.add_argument('--n-envs', type=int, default=4,
                       help='Number of parallel environments')
    parser.add_argument('--save-path', type=str, default='./models/dw_agent',
                       help='Model save path')
    parser.add_argument('--tensorboard-log', type=str, default='./tb_logs',
                       help='Tensorboard log directory')
    
    args = parser.parse_args()
    
    train_agent(
        agent_id=args.agent_id,
        total_timesteps=args.timesteps,
        n_envs=args.n_envs,
        save_path=args.save_path,
        tensorboard_log=args.tensorboard_log
    )