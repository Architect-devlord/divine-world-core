# ai_core/replay_buffer.py
import random
import numpy as np
from collections import deque

class ReplayBuffer:
    """
    Rolling buffer of experience tuples (obs, action, reward, next_obs, done).
    Used for online updates.
    """
    def __init__(self, capacity: int = 5000):
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)

    def add(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs, action, reward, next_obs, done))

    def sample(self, batch_size: int = 32):
        batch = random.sample(self.buffer, min(len(self.buffer), batch_size))
        obs, actions, rewards, next_obs, dones = zip(*batch)
        return np.array(obs), np.array(actions), np.array(rewards), np.array(next_obs), np.array(dones)

    def __len__(self):
        return len(self.buffer)
