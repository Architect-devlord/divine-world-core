# py_backend/utils/dw_controller.py
"""
Controller Runtime for DivineWorld AI Agents.
==============================================
Provides system-level sensor access: camera (OpenCV) and
microphone (sounddevice).  Feeds raw frames/audio directly
into the agent's memory and emotion systems.

Permission model
----------------
All hardware access is gated by the enabled_permissions dict.
Permissions are set externally (e.g. from the /controller/activate
endpoint in main.py) before calling start_multimodal_learning().

    controller.enabled_permissions['camera'] = True
    controller.start_multimodal_learning(vision=True, audio=False)

Emotion integration
-------------------
Uses agent.emotion.emotions[key] = value (the dict the EmotionSystem
exposes directly) — not a hypothetical .add() method that doesn't exist.

Memory integration
------------------
Calls agent.memory.remember(event, tags=[...]) which is the real API
on UnifiedMemoryStore.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ai_core.agent import NPCAgent

try:
    import sounddevice as sd
except ImportError:
    sd = None

log = logging.getLogger("dw_controller")
log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

class CameraCapture:
    """Threaded camera capture."""

    def __init__(self, camera_index: int = 0,
                 fps: int = 20,
                 resolution: Tuple[int, int] = (640, 480)):
        self.camera_index = camera_index
        self.fps          = fps
        self.resolution   = resolution

        self._cap:    Optional[cv2.VideoCapture] = None
        self._frame:  Optional[np.ndarray]       = None
        self._lock    = threading.Lock()
        self.running  = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.camera_index}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info(f"Camera {self.camera_index} started "
                 f"({self.resolution[0]}×{self.resolution[1]} @ {self.fps}fps)")

    def _loop(self):
        interval = 1.0 / self.fps
        while self.running and self._cap and self._cap.isOpened():
            try:
                ok, frame = self._cap.read()
                if ok:
                    with self._lock:
                        self._frame = frame
            except Exception as e:
                log.error(f"Camera loop error: {e}")
            time.sleep(interval)

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        log.info(f"Camera {self.camera_index} stopped")


# ---------------------------------------------------------------------------
# Microphone
# ---------------------------------------------------------------------------

class MicrophoneCapture:
    """Threaded microphone capture via sounddevice."""

    def __init__(self, device_index: Optional[int] = None,
                 sample_rate: int = 16000,
                 channels: int = 1,
                 max_buffer_chunks: int = 10):
        if sd is None:
            raise RuntimeError("sounddevice is not installed")
        self.device_index      = device_index
        self.sample_rate       = sample_rate
        self.channels          = channels
        self.max_buffer_chunks = max_buffer_chunks

        self._buffer: List[np.ndarray] = []
        self._lock   = threading.Lock()
        self._stream = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True

        def _cb(indata, frames, time_info, status):
            if status:
                log.warning(f"Audio status: {status}")
            with self._lock:
                if len(self._buffer) >= self.max_buffer_chunks:
                    self._buffer.pop(0)
                self._buffer.append(indata[:, 0].copy())

        try:
            self._stream = sd.InputStream(
                device=self.device_index,
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=_cb,
            )
            self._stream.start()
            log.info(f"Microphone started ({self.sample_rate}Hz, {self.channels}ch)")
        except Exception as e:
            self.running = False
            raise RuntimeError(f"Failed to start microphone: {e}") from e

    def get_audio_chunk(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._buffer:
                return None
            audio = np.concatenate(self._buffer)
            self._buffer.clear()
            return audio

    def stop(self):
        self.running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.warning(f"Mic stop error: {e}")
        log.info("Microphone stopped")


# ---------------------------------------------------------------------------
# ControllerRuntime
# ---------------------------------------------------------------------------

class ControllerRuntime:
    """
    System-level multimodal sensor runtime for a single NPCAgent.

    Usage
    -----
    runtime = ControllerRuntime(agent)
    runtime.enabled_permissions['camera']     = True
    runtime.enabled_permissions['microphone'] = True
    runtime.start_multimodal_learning(vision=True, audio=True)
    # ... agent learns from sensor data ...
    runtime.stop()

    Or as a context manager:
    with ControllerRuntime(agent) as rt:
        rt.enabled_permissions['camera'] = True
        rt.start_multimodal_learning()
    """

    def __init__(self, agent: NPCAgent,
                 max_camera_checks: int = 6,
                 callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.agent              = agent
        self.max_camera_checks  = max_camera_checks
        self.callback           = callback

        self.camera:    Optional[CameraCapture]    = None
        self.microphone:Optional[MicrophoneCapture]= None

        self._vision_thread: Optional[threading.Thread] = None
        self._audio_thread:  Optional[threading.Thread] = None
        self._lock   = threading.Lock()
        self.running = False

        self.stats: Dict[str, int] = {
            'frames_processed':       0,
            'audio_chunks_processed': 0,
            'files_processed':        0,
            'learning_events':        0,
        }

        # All permissions default to off — must be granted explicitly.
        self.enabled_permissions: Dict[str, bool] = {
            'camera':     False,
            'microphone': False,
            'filesystem': False,
            'network':    False,
        }

    # ------------------------------------------------------------------
    # Hardware detection
    # ------------------------------------------------------------------

    def list_cameras(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Probe camera indices and return those that respond."""
        limit   = limit or self.max_camera_checks
        cameras = []
        for i in range(limit):
            cap = None
            try:
                cap = cv2.VideoCapture(i)
                if not cap.isOpened():
                    continue
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    cameras.append({'index': i, 'resolution': (w, h), 'name': f'Camera {i}'})
            except Exception as e:
                log.warning(f"Camera {i} probe failed: {e}")
            finally:
                if cap is not None:
                    cap.release()
                    time.sleep(0.05)   # let OS release the handle
        log.info(f"Detected {len(cameras)} camera(s)")
        return cameras

    def auto_detect_camera(self, prefer_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        cameras = self.list_cameras()
        if not cameras:
            return None
        if prefer_index is not None:
            for cam in cameras:
                if cam['index'] == prefer_index:
                    return cam
        # Prefer highest resolution
        cameras.sort(key=lambda c: c['resolution'][0] * c['resolution'][1], reverse=True)
        return cameras[0]

    def list_microphones(self) -> List[Dict[str, Any]]:
        if sd is None:
            return []
        try:
            return [
                {'index': i, 'name': d['name'],
                 'channels': d['max_input_channels'],
                 'sample_rate': d['default_samplerate']}
                for i, d in enumerate(sd.query_devices())
                if d['max_input_channels'] > 0
            ]
        except Exception as e:
            log.error(f"Microphone list failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Start / stop hardware
    # ------------------------------------------------------------------

    def start_camera(self, camera_index: Optional[int] = None,
                     resolution: Tuple[int, int] = (640, 480),
                     fps: int = 20) -> bool:
        if not self.enabled_permissions.get('camera'):
            log.warning("❌ Camera permission DENIED")
            return False
        if self.camera and self.camera.running:
            log.warning("Camera already running")
            return False
        if camera_index is None:
            detected = self.auto_detect_camera()
            if not detected:
                raise RuntimeError("No cameras detected")
            camera_index = detected['index']
        self.camera = CameraCapture(camera_index, fps, resolution)
        self.camera.start()
        return True

    def start_microphone(self, device_index: Optional[int] = None,
                         sample_rate: int = 16000) -> bool:
        if not self.enabled_permissions.get('microphone'):
            log.warning("❌ Microphone permission DENIED")
            return False
        if sd is None:
            raise RuntimeError("sounddevice not installed")
        if self.microphone and self.microphone.running:
            log.warning("Microphone already running")
            return False
        self.microphone = MicrophoneCapture(device_index, sample_rate)
        self.microphone.start()
        return True

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def grant_permissions(self, permissions: list):
        """
        Enable a list of named permissions.
        Called by the FastAPI /controller/activate endpoint after the
        user acknowledges the permission dialog in the React frontend.

        Example:
            runtime.grant_permissions(['camera', 'microphone'])
        """
        valid = set(self.enabled_permissions)
        for p in permissions:
            if p in valid:
                self.enabled_permissions[p] = True
                log.info(f"Permission GRANTED: {p}")

    def log_permission_denied(self, resource: str):
        """Log a permission-denied access attempt."""
        log.warning(f"🔒 {resource} access DENIED by permission settings")

    def can_access_filesystem(self) -> bool:
        return self.enabled_permissions.get('filesystem', False)

    def can_access_network(self) -> bool:
        return self.enabled_permissions.get('network', False)

    def can_use_camera(self) -> bool:
        return self.enabled_permissions.get('camera', False)

    def can_use_microphone(self) -> bool:
        return self.enabled_permissions.get('microphone', False)

    # ------------------------------------------------------------------
    # Learning callbacks
    # ------------------------------------------------------------------

    def learn_from_frame(self, frame: np.ndarray):
        """Push a video frame into the agent's memory and emotion systems."""
        if frame is None:
            return
        with self._lock:
            # Stash in perception_buffer for downstream modules (e.g. vision.py)
            if not hasattr(self.agent, 'perception_buffer'):
                self.agent.perception_buffer = {}
            self.agent.perception_buffer['visual']            = frame
            self.agent.perception_buffer['visual_timestamp']  = time.time()

            h, w       = frame.shape[:2]
            brightness = float(np.mean(frame))

            self.agent.memory.remember({
                'type':    'visual_input',
                'tags':    ['controller', 'vision', 'multimodal'],
                'payload': {
                    'resolution': (w, h),
                    'brightness': brightness,
                    'timestamp':  time.time(),
                },
            }, tags=['vision'])

            # Novelty-driven emotion nudge — use direct dict access which
            # is the actual EmotionSystem API (no .add() method exists).
            novelty = brightness / 255.0   # simple proxy; replace with real novelty score if available
            if novelty > 0.5:
                emo = self.agent.emotion.emotions
                emo['surprise']  = min(1.0, emo.get('surprise',  0.0) + min(0.10, novelty * 0.10))
                emo['curiosity'] = min(1.0, emo.get('curiosity', 0.0) + min(0.15, novelty * 0.15))

            self.stats['frames_processed'] += 1
            self.stats['learning_events']  += 1

        if self.callback:
            self.callback(self.stats)

    def learn_from_audio(self, audio: np.ndarray, sample_rate: int):
        """Push an audio chunk into the agent's memory and emotion systems."""
        if audio is None or len(audio) == 0:
            return
        with self._lock:
            if not hasattr(self.agent, 'perception_buffer'):
                self.agent.perception_buffer = {}
            self.agent.perception_buffer['audio']           = audio
            self.agent.perception_buffer['audio_timestamp'] = time.time()

            rms  = float(np.sqrt(np.mean(audio ** 2)))
            peak = float(np.max(np.abs(audio)))

            self.agent.memory.remember({
                'type':    'audio_input',
                'tags':    ['controller', 'audio', 'multimodal'],
                'payload': {
                    'duration':    len(audio) / sample_rate,
                    'rms':         rms,
                    'peak':        peak,
                    'sample_rate': sample_rate,
                    'timestamp':   time.time(),
                },
            }, tags=['audio'])

            if rms > 0.1:
                emo = self.agent.emotion.emotions
                emo['surprise']     = min(1.0, emo.get('surprise',     0.0) + min(0.10, rms))
                emo['anticipation'] = min(1.0, emo.get('anticipation', 0.0) + min(0.05, rms * 0.5))

            self.stats['audio_chunks_processed'] += 1
            self.stats['learning_events']        += 1

        if self.callback:
            self.callback(self.stats)

    # ------------------------------------------------------------------
    # Runtime control
    # ------------------------------------------------------------------

    def start_multimodal_learning(self, vision: bool = True, audio: bool = True):
        if self.running:
            log.warning("Controller already running")
            return

        if vision:
            if self.enabled_permissions.get('camera'):
                try:
                    self.start_camera()
                    log.info("📹 Camera started")
                except Exception as e:
                    log.error(f"Camera init failed: {e}")
                    vision = False
            else:
                log.info("📹 Vision requested but camera permission DENIED")
                vision = False

        if audio:
            if self.enabled_permissions.get('microphone'):
                try:
                    self.start_microphone()
                    log.info("🎤 Microphone started")
                except Exception as e:
                    log.error(f"Microphone init failed: {e}")
                    audio = False
            else:
                log.info("🎤 Audio requested but microphone permission DENIED")
                audio = False

        self.running = True

        if vision and self.camera:
            self._vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
            self._vision_thread.start()

        if audio and self.microphone:
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()

    def _vision_loop(self):
        while self.running and self.camera:
            try:
                frame = self.camera.get_frame()
                if frame is not None:
                    self.learn_from_frame(frame)
            except Exception as e:
                log.error(f"Vision loop error: {e}")
            time.sleep(0.1)

    def _audio_loop(self):
        while self.running and self.microphone:
            try:
                audio = self.microphone.get_audio_chunk()
                if audio is not None:
                    self.learn_from_audio(audio, self.microphone.sample_rate)
            except Exception as e:
                log.error(f"Audio loop error: {e}")
            time.sleep(0.5)

    def stop(self):
        self.running = False
        for t in (self._vision_thread, self._audio_thread):
            if t:
                t.join(timeout=2.0)
        if self.camera:
            self.camera.stop()
        if self.microphone:
            self.microphone.stop()
        log.info("Controller runtime stopped")

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            'camera_active':    self.camera    is not None and self.camera.running,
            'microphone_active':self.microphone is not None and self.microphone.running,
            'memory_size':      len(self.agent.memory.events),
        }

    # Context manager
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()