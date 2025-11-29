# ------------------------------------------------------------------------------
# rl/demo_recorder.py - Demo recording for imitation learning
# ------------------------------------------------------------------------------
"""
Record human demonstrations for offline learning.
"""
import os
import time
import json
import threading
import base64
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

DATA_DIR = 'data/demos'
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


class DemoRecorder:
    """
    Record demonstrations to JSONL format.
    Supports pixel observations and state vectors.
    """
    def __init__(self, player_name: str, mode: str = 'state'):
        self.player = player_name
        self.mode = mode  # 'pixel' or 'state'
        self.out_file = Path(DATA_DIR) / f'{player_name}_demos.jsonl'
        self.lock = threading.Lock()
        self.recording = False
        self.episode_count = 0
        self.step_count = 0
    
    def start_recording(self):
        """Start recording session"""
        self.recording = True
        self.episode_count += 1
        self.step_count = 0
        print(f"[Recorder] Started episode {self.episode_count}")
    
    def stop_recording(self):
        """Stop recording session"""
        self.recording = False
        print(f"[Recorder] Stopped episode {self.episode_count} "
              f"({self.step_count} steps)")
    
    def record_step(self, frame: Optional[np.ndarray] = None,
                   state: Optional[Dict[str, Any]] = None,
                   action: Optional[Dict[str, Any]] = None):
        """Record single step"""
        if not self.recording:
            return
        
        item = {
            'ts': time.time(),
            'player': self.player,
            'episode': self.episode_count,
            'step': self.step_count,
            'action': action,
            'state': state
        }
        
        # Encode frame if provided
        if self.mode == 'pixel' and frame is not None:
            try:
                import cv2
                ret, buf = cv2.imencode('.jpg', frame, 
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ret:
                    item['frame_jpg_b64'] = base64.b64encode(
                        buf.tobytes()
                    ).decode('ascii')
            except Exception as e:
                print(f"[Recorder] Frame encoding failed: {e}")
        
        # Write to file
        with self.lock:
            with open(self.out_file, 'a') as f:
                f.write(json.dumps(item) + '\n')
        
        self.step_count += 1
    
    def load_demos(self, limit: Optional[int] = None):
        """Load recorded demonstrations"""
        if not self.out_file.exists():
            return []
        
        demos = []
        with open(self.out_file, 'r') as f:
            for i, line in enumerate(f):
                if limit and i >= limit:
                    break
                try:
                    demos.append(json.loads(line))
                except Exception:
                    pass
        
        return demos