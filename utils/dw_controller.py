# utils/dw_controller.py - PRODUCTION-HARDENED VERSION
"""
Controller Runtime for DivineWorld AI Agents
Provides system-level access: camera, microphone, file system
Enables multimodal learning from real-world sensors
Thread-safe, robust, and ready for production use
"""

import cv2
import time
import threading
import numpy as np
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple

from ai_core.agent import NPCAgent
from ai_core.memory import Memory

try:
    import sounddevice as sd
except ImportError:
    sd = None

log = logging.getLogger("dw_controller")
log.setLevel(logging.INFO)


# ------------------- Camera Capture -------------------

class CameraCapture:
    """Threaded camera capture for real-time vision"""

    def __init__(self, camera_index: int = 0, fps: int = 20, resolution: Tuple[int, int] = (640, 480)):
        self.camera_index = camera_index
        self.fps = fps
        self.resolution = resolution
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.capture_thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open camera {self.camera_index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        log.info(f"Camera {self.camera_index} started ({self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps)")

    def _capture_loop(self):
        while self.running and self.cap and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if ret:
                    with self.frame_lock:
                        self.latest_frame = frame
                time.sleep(1.0 / self.fps)
            except Exception as e:
                log.error(f"Camera capture loop error: {e}")
                time.sleep(0.1)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def stop(self):
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        log.info(f"Camera {self.camera_index} stopped")


# ------------------- Microphone Capture -------------------

class MicrophoneCapture:
    """Threaded microphone capture for audio learning"""

    def __init__(self, device_index: Optional[int] = None, sample_rate: int = 16000, channels: int = 1, max_buffer_chunks: int = 10):
        if sd is None:
            raise RuntimeError("sounddevice not installed")
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_buffer: List[np.ndarray] = []
        self.buffer_lock = threading.Lock()
        self.stream = None
        self.running = False
        self.max_buffer_chunks = max_buffer_chunks

    def start(self):
        if self.running:
            return
        self.running = True

        def audio_callback(indata, frames, time_info, status):
            if status:
                log.warning(f"Audio status: {status}")
            with self.buffer_lock:
                if len(self.audio_buffer) >= self.max_buffer_chunks:
                    self.audio_buffer.pop(0)
                self.audio_buffer.append(indata[:, 0].copy())

        try:
            self.stream = sd.InputStream(
                device=self.device_index,
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=audio_callback
            )
            self.stream.start()
            log.info(f"Microphone started ({self.sample_rate}Hz, {self.channels} channel)")
        except Exception as e:
            self.running = False
            log.error(f"Failed to start microphone: {e}")
            raise

    def get_audio_chunk(self) -> Optional[np.ndarray]:
        with self.buffer_lock:
            if not self.audio_buffer:
                return None
            audio = np.concatenate(self.audio_buffer)
            self.audio_buffer.clear()
            return audio

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                log.warning(f"Error stopping microphone: {e}")
        log.info("Microphone stopped")


# ------------------- Controller Runtime -------------------

class ControllerRuntime:
    """Controller runtime for system-level AI access"""

    def __init__(self, agent: NPCAgent, max_camera_checks: int = 6, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.agent = agent
        self.max_camera_checks = max_camera_checks
        self.camera: Optional[CameraCapture] = None
        self.microphone: Optional[MicrophoneCapture] = None
        self.vision_thread: Optional[threading.Thread] = None
        self.audio_thread: Optional[threading.Thread] = None
        self.running = False
        self.stats = {'frames_processed': 0, 'audio_chunks_processed': 0, 'files_processed': 0, 'learning_events': 0}
        self.callback = callback
        self._lock = threading.Lock()  # Thread-safe updates for agent

    # --- Camera / Microphone Detection ---

    def list_cameras(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List available cameras with proper resource cleanup"""
        limit = limit or self.max_camera_checks
        cameras = []
    
        for i in range(limit):
            cap = None
            try:
                cap = cv2.VideoCapture(i)
            
                if not cap.isOpened():
                    continue
            
                # Try to read a frame
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    cameras.append({
                        'index': i,
                        'resolution': (w, h),
                        'name': f'Camera {i}'
                    })
                    log.debug(f"Found camera {i}: {w}x{h}")
        
            except Exception as e:
                log.warning(f"Camera {i} check failed: {e}")
        
            finally:
                # CRITICAL FIX: Always release camera
                if cap is not None:
                    cap.release()
                    # Give OS time to release resource (Windows needs this)
                    time.sleep(0.1)
    
        log.info(f"Detected {len(cameras)} cameras")
        return cameras

    def auto_detect_camera(self, prefer_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        cameras = self.list_cameras()
        if not cameras:
            return None
        if prefer_index is not None:
            for cam in cameras:
                if cam['index'] == prefer_index:
                    return cam
        cameras.sort(key=lambda x: x['resolution'][0]*x['resolution'][1], reverse=True)
        return cameras[0]

    def start_camera(self, camera_index: Optional[int] = None, resolution: Tuple[int, int] = (640, 480), fps: int = 20):
        if self.camera and self.camera.running:
            log.warning("Camera already running")
            return
        if camera_index is None:
            detected = self.auto_detect_camera()
            if not detected:
                raise RuntimeError("No cameras detected")
            camera_index = detected['index']
        self.camera = CameraCapture(camera_index, fps, resolution)
        self.camera.start()

    def list_microphones(self) -> List[Dict[str, Any]]:
        if sd is None:
            return []
        try:
            devices = sd.query_devices()
            microphones = []
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    microphones.append({'index': i, 'name': dev['name'], 'channels': dev['max_input_channels'],
                                        'sample_rate': dev['default_samplerate']})
            return microphones
        except Exception as e:
            log.error(f"Failed to list microphones: {e}")
            return []

    def auto_detect_microphone(self) -> Optional[Dict[str, Any]]:
        mics = self.list_microphones()
        return mics[0] if mics else None

    def start_microphone(self, device_index: Optional[int] = None, sample_rate: int = 16000):
        if sd is None:
            raise RuntimeError("sounddevice not installed")
        if self.microphone and self.microphone.running:
            log.warning("Microphone already running")
            return
        self.microphone = MicrophoneCapture(device_index, sample_rate)
        self.microphone.start()

    # --- Learning ---

    def learn_from_frame(self, frame: np.ndarray):
        if frame is None:
            return
        with self._lock:
            if not hasattr(self.agent, 'perception_buffer'):
                self.agent.perception_buffer = {}
            self.agent.perception_buffer['visual'] = frame
            self.agent.perception_buffer['visual_timestamp'] = time.time()
            h, w = frame.shape[:2]
            brightness = float(np.mean(frame))
            event = {'type': 'visual_input', 'tags': ['controller','vision','multimodal'],
                     'payload': {'resolution': (w,h), 'brightness': brightness, 'timestamp': time.time()}}
            self.agent.memory.remember(event, tags=['vision'])
            novelty = self.agent.memory.novelty_score(f"frame_{w}x{h}_{brightness:.1f}")
            if novelty > 0.5:
                self.agent.emotion.add('surprise', min(0.1, novelty*0.1))
                self.agent.emotion.add('curiosity', min(0.15, novelty*0.15))
            self.stats['frames_processed'] += 1
            self.stats['learning_events'] += 1
        if self.callback:
            self.callback(self.stats)

    def learn_from_audio(self, audio: np.ndarray, sample_rate: int):
        if audio is None or len(audio) == 0:
            return
        with self._lock:
            if not hasattr(self.agent, 'perception_buffer'):
                self.agent.perception_buffer = {}
            self.agent.perception_buffer['audio'] = audio
            self.agent.perception_buffer['audio_timestamp'] = time.time()
            rms = float(np.sqrt(np.mean(audio ** 2)))
            peak = float(np.max(np.abs(audio)))
            event = {'type':'audio_input','tags':['controller','audio','multimodal'],
                     'payload': {'duration': len(audio)/sample_rate,'rms':rms,'peak':peak,'sample_rate':sample_rate,'timestamp':time.time()}}
            self.agent.memory.remember(event, tags=['audio'])
            if rms > 0.1:
                self.agent.emotion.add('surprise', min(0.1, rms))
                self.agent.emotion.add('anticipation', min(0.05, rms*0.5))
            self.stats['audio_chunks_processed'] += 1
            self.stats['learning_events'] += 1
        if self.callback:
            self.callback(self.stats)

    # --- Runtime Control ---

    def start_multimodal_learning(self, vision: bool = True, audio: bool = True):
        if self.running:
            log.warning("Controller already running")
            return
        self.running = True
        if vision and self.camera:
            self.vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self.vision_thread.start()
        if audio and self.microphone:
            self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.audio_thread.start()

    def _vision_loop(self):
        while self.running and self.camera:
            try:
                frame = self.camera.get_frame()
                if frame is not None:
                    self.learn_from_frame(frame)
                time.sleep(0.1)
            except Exception as e:
                log.error(f"Vision processing loop error: {e}")

    def _audio_loop(self):
        while self.running and self.microphone:
            try:
                audio = self.microphone.get_audio_chunk()
                if audio is not None:
                    self.learn_from_audio(audio, self.microphone.sample_rate)
                time.sleep(0.5)
            except Exception as e:
                log.error(f"Audio processing loop error: {e}")

    def stop(self):
        self.running = False
        if self.vision_thread:
            self.vision_thread.join(timeout=2.0)
        if self.audio_thread:
            self.audio_thread.join(timeout=2.0)
        if self.camera:
            self.camera.stop()
        if self.microphone:
            self.microphone.stop()
        log.info("Controller runtime stopped")

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            'camera_active': self.camera is not None and self.camera.running,
            'microphone_active': self.microphone is not None and self.microphone.running,
            'memory_size': len(self.agent.memory.events)
        }

    # --- Context Manager Support ---

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
