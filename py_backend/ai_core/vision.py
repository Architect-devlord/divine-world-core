# ------------------------------------------------------------------------------
# ai_core/vision.py - Vision adapter (no deps)
# ------------------------------------------------------------------------------
import numpy as np
from typing import Optional, Callable

class VisionAdapter:
    """
    Vision input adapter supporting multiple capture sources.
    """
    def __init__(self, capture_func: Optional[Callable[[], np.ndarray]] = None):
        self.capture_func = capture_func
    
    def get_frame(self) -> np.ndarray:
        """Get current frame (HxWx3 uint8)"""
        if self.capture_func:
            return self.capture_func()
        # Dummy frame for testing
        return np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8)
    
    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Preprocess frame for neural network"""
        # Normalize to [0, 1]
        frame = frame.astype(np.float32) / 255.0
        # Transpose to CHW format for PyTorch
        frame = np.transpose(frame, (2, 0, 1))
        return frame