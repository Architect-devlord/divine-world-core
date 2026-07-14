# ai_core/vision.py
"""
Plug-and-Play Vision System for Divine World AI Agents
=======================================================

Philosophy
----------
Agents start with zero visual knowledge — no pretrained object labels,
no assumed categories.  Every meaningful visual pattern is discovered
and named through experience.  The agent develops its OWN vocabulary
for what it sees, just as it does for language.

The module auto-detects the execution context and wires the right
capture backend:

  Context           Backend selected
  ────────────────  ────────────────────────────────────────────────
  Minecraft mod     MinecraftVisionBackend  — frame stream over the
                    existing TCP/WebSocket connection from the mod
  Isaac Sim         IsaacSimVisionBackend   — reads camera prim from
                    the live simulation scene
  Physical robot    RobotCameraBackend      — V4L2 / GStreamer /
                    any OpenCV-compatible device index
  Fallback / CI     SyntheticBackend        — deterministic gradient
                    frames so the pipeline always has something to run

Visual learning pipeline
------------------------

  Raw frame  →  FeatureExtractor  →  float32 patch grid
                     │
                     ▼
             OnlineVisualVocabulary   ← agents own cluster-based
             (k-means style, grows     "word" vocabulary for patches
              with experience)
                     │
                     ▼
             VisualMemory             ← stores (frame, features,
                                        agent-assigned token) events
                     │
                     ▼
             VisionAdapter.observe()  → agent.memory + WorldModel

The agent names clusters through language grounding over time.
No COCO labels, no BLIP, no pretrained detector.

Hard dependencies
-----------------
  numpy  (always required)

Soft dependencies (graceful degradation)
-----------------------------------------
  torch            — feature CNN + online k-means on GPU
  cv2              — frame capture and resize
  isaacsim         — Isaac Sim camera prim access

"""

from __future__ import annotations

import logging
import threading
import time
import queue
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("vision")

# ─────────────────────────────────────────────────────────────────────────────
# Soft imports
# ─────────────────────────────────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _TORCH = True
except ImportError:
    torch = None  # type: ignore
    _TORCH = False

try:
    import cv2
    _CV2 = True
except ImportError:
    cv2 = None  # type: ignore
    _CV2 = False

try:
    from isaacsim.core.utils.prims import get_prim_at_path
    _ISAAC = True
except ImportError:
    try:
        from omni.isaac.core.utils.prims import get_prim_at_path  # type: ignore
        _ISAAC = True
    except Exception:
        _ISAAC = False

# ─────────────────────────────────────────────────────────────────────────────
# Frame dataclass — the unit of currency in this module
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VisualFrame:
    """One captured and processed frame."""

    # Raw pixels — always HxWx3 uint8 BGR (OpenCV convention)
    raw: np.ndarray

    # CHW float32 normalised to [0, 1] — ready for neural input
    tensor: Optional[np.ndarray] = None            # (3, H, W)

    # Compact feature vector — output of FeatureExtractor
    features: Optional[np.ndarray] = None          # (feature_dim,)

    # Agent-assigned visual token — the cluster index this frame maps to.
    # This is the agent's OWN identity for the visual pattern.
    visual_token: int = -1

    # Source metadata
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)

    # Depth map — H×W float32 metres (filled by depth backend if available)
    depth: Optional[np.ndarray] = None

    @property
    def height(self) -> int:
        return self.raw.shape[0]

    @property
    def width(self) -> int:
        return self.raw.shape[1]

    def to_memory_event(self, token_name: str = "") -> Dict[str, Any]:
        return {
            "type": "visual_frame",
            "text": token_name or f"visual_token_{self.visual_token}",
            "timestamp": self.timestamp,
            "source": self.source,
            "visual_token": self.visual_token,
            "has_depth": self.depth is not None,
            "frame_shape": list(self.raw.shape),
        }

    def to_proprio_vector(self, dim: int = 32) -> np.ndarray:
        """
        Compact representation of this frame suitable for the WorldModel
        proprio encoder (dim must match WorldModelConfig.proprio_dim).
        """
        v = np.zeros(dim, dtype=np.float32)
        if self.features is not None:
            n = min(dim - 2, len(self.features))
            v[:n] = self.features[:n]
        v[dim - 2] = float(self.visual_token) / 256.0  # normalised cluster id
        if self.depth is not None and self.depth.size > 0:
            v[dim - 1] = float(np.nanmean(self.depth)) / 20.0
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight CNN feature extractor (no pretrained weights needed)
# ─────────────────────────────────────────────────────────────────────────────

class _SimpleCNNExtractor(nn.Module):
    """
    Tiny randomly-initialised CNN.

    The weights start random and are updated by the agent's world-model
    trainer over time — so the features genuinely belong to the agent's
    learned experience, not an ImageNet prior.

    Output: (feature_dim,) float32 vector per frame.
    """

    def __init__(self, feature_dim: int = 64):
        super().__init__()
        self.feature_dim = feature_dim
        self.conv = nn.Sequential(
            nn.Conv2d(3, 16, 5, stride=2, padding=2),   # → 42×42
            nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1),  # → 21×21
            nn.ReLU(),
            nn.Conv2d(32, 32, 3, stride=2, padding=1),  # → 11×11
            nn.ReLU(),
        )
        self.pool = nn.AdaptiveAvgPool2d((4, 4))
        self.fc   = nn.Linear(32 * 4 * 4, feature_dim)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        # x: (B, 3, H, W)
        h = self.conv(x)
        h = self.pool(h)
        h = h.flatten(1)
        return self.fc(h)


class FeatureExtractor:
    """
    Wraps the CNN and handles device placement + batching.
    Falls back to raw pixel statistics when torch is absent.
    """

    def __init__(self, feature_dim: int = 64, device: str = "cpu"):
        self.feature_dim = feature_dim
        self.device = device
        self._net: Optional[_SimpleCNNExtractor] = None

        if _TORCH:
            self._net = _SimpleCNNExtractor(feature_dim).to(device)
            self._net.eval()
            log.info(f"FeatureExtractor: CNN initialised on {device} "
                     f"(random weights — will learn from experience).")
        else:
            log.info("FeatureExtractor: torch absent — using pixel-stat fallback.")

    def extract(self, frame_chw: np.ndarray) -> np.ndarray:
        """
        frame_chw: (3, H, W) float32 in [0,1].
        Returns: (feature_dim,) float32.
        """
        if self._net is not None and _TORCH:
            t = torch.tensor(frame_chw, dtype=torch.float32,
                             device=self.device).unsqueeze(0)
            with torch.no_grad():
                out = self._net(t)
            return out.squeeze(0).cpu().numpy()

        # Fallback — channel means, stds, a few spatial statistics
        h = frame_chw
        stats = [
            h[0].mean(), h[1].mean(), h[2].mean(),
            h[0].std(),  h[1].std(),  h[2].std(),
            np.percentile(h, 10), np.percentile(h, 90),
        ]
        v = np.array(stats, dtype=np.float32)
        # Pad / truncate to feature_dim
        if len(v) < self.feature_dim:
            v = np.pad(v, (0, self.feature_dim - len(v)))
        return v[:self.feature_dim]

    def state_dict(self) -> Optional[Dict]:
        if self._net is not None:
            return self._net.state_dict()
        return None

    def load_state_dict(self, state: Dict):
        if self._net is not None and state is not None:
            self._net.load_state_dict(state)


# ─────────────────────────────────────────────────────────────────────────────
# Online Visual Vocabulary — agent's own cluster-based "word" system
# ─────────────────────────────────────────────────────────────────────────────

class OnlineVisualVocabulary:
    """
    Incrementally builds a vocabulary of visual patterns via online k-means.

    The agent assigns its own integer token to each cluster centre.
    Token 0 is always "unseen / initialising".

    No COCO.  No ImageNet.  The agent discovers categories from what it
    actually encounters — a completely blank slate.

    Over time the agent can attach language labels to tokens via
    assign_name(token, name), driven by the language system noticing
    correlations between visual tokens and heard/read words.
    """

    def __init__(self, max_clusters: int = 256,
                 feature_dim: int = 64,
                 lr: float = 0.05,
                 min_obs_to_split: int = 50):
        self.max_clusters    = max_clusters
        self.feature_dim     = feature_dim
        self.lr              = lr
        self.min_obs_to_split = min_obs_to_split

        # Cluster centres: (n_clusters, feature_dim)
        self._centres: np.ndarray = np.zeros((0, feature_dim), dtype=np.float32)
        # How many observations each cluster has absorbed
        self._counts: np.ndarray = np.zeros(0, dtype=np.int64)
        # Agent-assigned names (token -> name string)
        self._names: Dict[int, str] = {}

        self._total_obs = 0
        self._lock = threading.Lock()

    # ── public ──

    @property
    def n_clusters(self) -> int:
        return len(self._centres)

    def observe(self, feature: np.ndarray) -> int:
        """
        Update vocabulary with a new feature vector.
        Returns the token (cluster index) for this feature.
        """
        with self._lock:
            self._total_obs += 1

            if self.n_clusters == 0:
                # Bootstrap: first observation creates the first cluster
                self._centres = feature[np.newaxis].copy()
                self._counts  = np.array([1], dtype=np.int64)
                return 0

            # Find nearest centre
            dists = np.linalg.norm(self._centres - feature, axis=1)
            nearest = int(np.argmin(dists))
            min_dist = float(dists[nearest])

            # Move centre toward observation (online k-means update)
            self._centres[nearest] += self.lr * (feature - self._centres[nearest])
            self._counts[nearest]  += 1

            # Consider growing vocabulary
            if (self.n_clusters < self.max_clusters and
                    self._counts[nearest] >= self.min_obs_to_split and
                    min_dist > self._mean_intra_dist() * 1.5):
                self._split_cluster(nearest, feature)

            return nearest

    def name_of(self, token: int) -> str:
        """Return the agent-assigned name for this token, or a default."""
        return self._names.get(token, f"visual_{token}")

    def assign_name(self, token: int, name: str):
        """Agent (via language grounding) assigns a word to a visual token."""
        self._names[token] = name
        log.info(f"Visual vocabulary: token {token} named '{name}'")

    def most_similar(self, feature: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        """Return top-k (token, similarity) pairs for a feature."""
        with self._lock:
            if self.n_clusters == 0:
                return []
            dists = np.linalg.norm(self._centres - feature, axis=1)
            idx   = np.argsort(dists)[:k]
            return [(int(i), float(dists[i])) for i in idx]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "n_clusters":      self.n_clusters,
            "total_obs":       self._total_obs,
            "named_tokens":    len(self._names),
            "named":           dict(self._names),
        }

    # ── persistence ──

    def state_dict(self) -> Dict:
        return {
            "centres": self._centres.tolist(),
            "counts":  self._counts.tolist(),
            "names":   self._names,
            "total_obs": self._total_obs,
        }

    def load_state_dict(self, state: Dict):
        with self._lock:
            self._centres   = np.array(state["centres"],  dtype=np.float32)
            self._counts    = np.array(state["counts"],   dtype=np.int64)
            self._names     = {int(k): v for k, v in state.get("names", {}).items()}
            self._total_obs = state.get("total_obs", 0)

    # ── private ──

    def _mean_intra_dist(self) -> float:
        if self.n_clusters < 2:
            return 1.0
        # Sample random pairwise distances — O(1) cost
        idx = np.random.choice(self.n_clusters,
                               size=min(self.n_clusters, 20), replace=False)
        sample = self._centres[idx]
        diffs  = sample[:, np.newaxis] - sample[np.newaxis, :]
        dists  = np.linalg.norm(diffs, axis=-1)
        return float(dists[dists > 0].mean()) if (dists > 0).any() else 1.0

    def _split_cluster(self, token: int, trigger_feature: np.ndarray):
        """
        Split an over-observed cluster by adding a new centre perturbed
        from the trigger feature.
        """
        noise = np.random.randn(self.feature_dim).astype(np.float32) * 0.01
        new_centre = trigger_feature + noise
        self._centres = np.vstack([self._centres, new_centre[np.newaxis]])
        self._counts  = np.append(self._counts, 1)
        log.debug(f"Visual vocab split: new cluster {self.n_clusters - 1} "
                  f"(total={self.n_clusters})")


# ─────────────────────────────────────────────────────────────────────────────
# Capture backends
# ─────────────────────────────────────────────────────────────────────────────

class CaptureBackend(ABC):
    """Abstract base for all frame sources."""

    @abstractmethod
    def read(self) -> Optional[np.ndarray]:
        """Return latest HxWx3 uint8 BGR frame, or None if not ready."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if this backend can provide frames right now."""

    def close(self):
        pass

    def source_name(self) -> str:
        return self.__class__.__name__


class SyntheticBackend(CaptureBackend):
    """
    Deterministic gradient frames — useful for CI / unit tests / headless runs.
    Always available.
    """

    def __init__(self, h: int = 84, w: int = 84):
        self._h = h
        self._w = w
        self._tick = 0

    def is_available(self) -> bool:
        return True

    def read(self) -> np.ndarray:
        self._tick += 1
        t   = self._tick / 30.0
        x   = np.linspace(0, 1, self._w)
        y   = np.linspace(0, 1, self._h)
        xv, yv = np.meshgrid(x, y)
        r   = (128 + 127 * np.sin(xv * 6 + t)).astype(np.uint8)
        g   = (128 + 127 * np.sin(yv * 6 + t + 2)).astype(np.uint8)
        b   = (128 + 127 * np.cos((xv + yv) * 4 + t)).astype(np.uint8)
        return np.stack([b, g, r], axis=-1)

    def source_name(self) -> str:
        return "synthetic"


class RobotCameraBackend(CaptureBackend):
    """
    Physical camera via OpenCV — works for webcams, USB cameras,
    GStreamer pipelines, RTSP streams, or any device index.

    Auto-detects available devices if `source` is None.
    """

    def __init__(self, source: Any = None,
                 target_h: int = 84, target_w: int = 84):
        self._target_h = target_h
        self._target_w = target_w
        self._cap      = None
        self._source   = source
        self._available = False

        if not _CV2:
            log.warning("RobotCameraBackend: OpenCV not available.")
            return

        src = source if source is not None else self._auto_detect()
        if src is None:
            return

        self._cap = cv2.VideoCapture(src)
        if self._cap.isOpened():
            self._available = True
            log.info(f"RobotCameraBackend: opened source={src!r}")
        else:
            log.warning(f"RobotCameraBackend: could not open source={src!r}")

    @staticmethod
    def _auto_detect() -> Optional[int]:
        """Try device indices 0-3."""
        if not _CV2:
            return None
        for idx in range(4):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cap.release()
                log.info(f"RobotCameraBackend: auto-detected camera at index {idx}")
                return idx
        return None

    def is_available(self) -> bool:
        return self._available and self._cap is not None and self._cap.isOpened()

    def read(self) -> Optional[np.ndarray]:
        if not self.is_available():
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        if _CV2:
            frame = cv2.resize(frame, (self._target_w, self._target_h))
        return frame

    def close(self):
        if self._cap:
            self._cap.release()

    def source_name(self) -> str:
        return f"robot_camera({self._source})"


class MinecraftVisionBackend(CaptureBackend):
    """
    Receives frames pushed by the Minecraft mod over the existing
    TCP / WebSocket connection.

    The mod sends raw JPEG-compressed frames in the PerceptionFrame
    protocol defined in communication_protocol.py.  This backend
    simply exposes the latest decoded frame so VisionAdapter can poll it.

    Frames are injected externally via push_frame() — called by
    the communication protocol handler when a vision packet arrives.
    """

    def __init__(self, target_h: int = 84, target_w: int = 84):
        self._target_h  = target_h
        self._target_w  = target_w
        self._latest: Optional[np.ndarray] = None
        self._lock      = threading.Lock()
        self._received  = 0

    def push_frame(self, frame_bgr: np.ndarray):
        """
        Called by the communication protocol handler every time a new
        visual frame arrives from the Minecraft client.
        """
        if _CV2 and frame_bgr.shape[:2] != (self._target_h, self._target_w):
            frame_bgr = cv2.resize(frame_bgr, (self._target_w, self._target_h))
        with self._lock:
            self._latest   = frame_bgr
            self._received += 1

    def is_available(self) -> bool:
        return self._latest is not None

    def read(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest.copy() if self._latest is not None else None

    def source_name(self) -> str:
        return "minecraft"


class IsaacSimVisionBackend(CaptureBackend):
    """
    Reads frames from an Isaac Sim camera prim.

    After world.reset() call attach_camera(camera_prim) to bind the prim.
    """

    def __init__(self, target_h: int = 84, target_w: int = 84):
        self._target_h   = target_h
        self._target_w   = target_w
        self._camera     = None
        self._available  = False

    def attach_camera(self, camera_prim):
        """Bind an Isaac Sim camera prim. Call after world.reset()."""
        self._camera    = camera_prim
        self._available = True
        log.info(f"IsaacSimVisionBackend: camera prim attached.")

    def is_available(self) -> bool:
        return _ISAAC and self._available and self._camera is not None

    def read(self) -> Optional[np.ndarray]:
        if not self.is_available():
            return None
        try:
            rgba = self._camera.get_rgba()          # (H, W, 4) uint8
            if rgba is None:
                return None
            rgb  = rgba[:, :, :3]
            if _CV2:
                bgr  = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                frame = cv2.resize(bgr, (self._target_w, self._target_h))
            else:
                frame = rgb[:self._target_h, :self._target_w]
            return frame
        except Exception as e:
            log.debug(f"IsaacSimVisionBackend.read error: {e}")
            return None

    def source_name(self) -> str:
        return "isaac_sim"


# ─────────────────────────────────────────────────────────────────────────────
# Context auto-detector
# ─────────────────────────────────────────────────────────────────────────────

class ContextDetector:
    """
    Determines which backend(s) are appropriate for the current runtime
    environment.  Returns an ordered list of (backend_instance, priority)
    tuples — the VisionAdapter tries them in priority order.
    """

    @staticmethod
    def detect(
        frame_h: int = 84,
        frame_w: int = 84,
        force_source: Any = None,
    ) -> List[CaptureBackend]:
        """
        Returns backends in preference order:
          1. Explicitly provided source (robot cam / file / RTSP)
          2. Minecraft backend (if agent is in Minecraft mode)
          3. Isaac Sim backend (if running inside Isaac Sim)
          4. Physical camera auto-detect
          5. Synthetic fallback (always last)
        """
        backends: List[CaptureBackend] = []

        # 1. Explicit source overrides everything
        if force_source is not None:
            b = RobotCameraBackend(source=force_source,
                                   target_h=frame_h, target_w=frame_w)
            if b.is_available():
                backends.append(b)
                return backends  # explicit source → use it exclusively

        # 2. Minecraft (backend is always created; becomes available when mod connects)
        mc = MinecraftVisionBackend(target_h=frame_h, target_w=frame_w)
        backends.append(mc)          # always include — agent in MC will push frames

        # 3. Isaac Sim
        if _ISAAC:
            backends.append(IsaacSimVisionBackend(target_h=frame_h, target_w=frame_w))

        # 4. Physical camera
        if _CV2:
            robot_cam = RobotCameraBackend(source=None,
                                           target_h=frame_h, target_w=frame_w)
            if robot_cam.is_available():
                backends.append(robot_cam)

        # 5. Synthetic fallback — always last
        backends.append(SyntheticBackend(h=frame_h, w=frame_w))
        return backends


# ─────────────────────────────────────────────────────────────────────────────
# Simple depth estimator (self-contained, no pretrained weights)
# ─────────────────────────────────────────────────────────────────────────────

class SelfTrainedDepthEstimator:
    """
    Monocular relative-depth estimator that learns from experience.

    Starts with a gradient-magnitude heuristic (edges → closer).
    As the world model accumulates data, the agent can swap in a
    trained depth head — but we never rely on a pretrained network.
    """

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]

        if _CV2:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        else:
            gray = frame_bgr.mean(axis=2).astype(np.float32)

        gx = np.gradient(gray, axis=1)
        gy = np.gradient(gray, axis=0)
        mag = np.sqrt(gx ** 2 + gy ** 2)
        # High gradient → foreground edge → closer
        depth = 10.0 * (1.0 - mag / (mag.max() + 1e-8))
        return depth.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Vision Adapter — main public interface
# ─────────────────────────────────────────────────────────────────────────────

class VisionAdapter:
    """
    Plug-and-play vision system for DW agents.

    Drop-in replacement for the old stub VisionAdapter.  All old call sites
    (agent.observe, agent.perceive visual path) continue to work unchanged.

    New capabilities
    ─────────────────
    - Auto-detects context (Minecraft / Isaac Sim / robot camera / synthetic)
    - Maintains an online visual vocabulary (agent's own token space)
    - Produces VisualFrame objects with features + visual tokens
    - Background capture thread for non-blocking frame delivery
    - Full save/load for brain persistence

    Usage
    ─────
    ::

        # In NPCAgent.__init__ — replaces the old one-liner
        self.vision = VisionAdapter(agent=self)

        # In Minecraft mode — communication protocol calls:
        agent.vision.push_minecraft_frame(frame_bgr)

        # In Isaac Sim — after world.reset():
        agent.vision.attach_isaac_camera(camera_prim)

        # In a robot with a USB camera — auto-detected at init.

        # Anywhere — get the latest processed frame:
        vf = agent.vision.latest_frame
        token_name = agent.vision.vocab.name_of(vf.visual_token)

    """

    def __init__(
        self,
        agent=None,
        feature_dim:     int  = 64,
        max_vocab_size:  int  = 256,
        frame_h:         int  = 84,
        frame_w:         int  = 84,
        fps:             float = 15.0,
        device:          str  = "cpu",
        force_source:    Any  = None,
        enable_depth:    bool = True,
        capture_func:    Optional[Callable[[], np.ndarray]] = None,
    ):
        self.agent        = agent
        self.feature_dim  = feature_dim
        self.frame_h      = frame_h
        self.frame_w      = frame_w
        self.fps          = fps
        self.device       = device
        self.enable_depth = enable_depth

        # Legacy capture_func support
        self._capture_func = capture_func

        # Sub-systems
        self.extractor = FeatureExtractor(feature_dim=feature_dim, device=device)
        self.vocab     = OnlineVisualVocabulary(
            max_clusters=max_vocab_size,
            feature_dim=feature_dim,
        )
        self._depth_estimator = SelfTrainedDepthEstimator() if enable_depth else None

        # Backends — ordered by preference
        self._backends: List[CaptureBackend] = ContextDetector.detect(
            frame_h=frame_h,
            frame_w=frame_w,
            force_source=force_source,
        )

        # Expose Minecraft backend for the protocol handler
        self.minecraft_backend: Optional[MinecraftVisionBackend] = next(
            (b for b in self._backends if isinstance(b, MinecraftVisionBackend)),
            None,
        )
        # Expose Isaac Sim backend for simulator integration
        self.isaac_backend: Optional[IsaacSimVisionBackend] = next(
            (b for b in self._backends if isinstance(b, IsaacSimVisionBackend)),
            None,
        )

        # State
        self.latest_frame: Optional[VisualFrame] = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=4)
        self._processed  = 0
        self._running    = False
        self._thread: Optional[threading.Thread] = None

        log.info(
            f"VisionAdapter: backends={[b.source_name() for b in self._backends]}, "
            f"device={device}, feature_dim={feature_dim}, vocab_max={max_vocab_size}"
        )

    # ─────────────────────────────────────────────────────────────────────
    # Context-specific integration points
    # ─────────────────────────────────────────────────────────────────────

    def push_minecraft_frame(self, frame_bgr: np.ndarray):
        """
        Called by the communication protocol handler each time a vision
        packet arrives from the Minecraft mod.
        """
        if self.minecraft_backend is not None:
            self.minecraft_backend.push_frame(frame_bgr)

    def attach_isaac_camera(self, camera_prim):
        """
        Call once after world.reset() in Isaac Sim simulations.
        """
        if self.isaac_backend is not None:
            self.isaac_backend.attach_camera(camera_prim)
        else:
            new_backend = IsaacSimVisionBackend(
                target_h=self.frame_h, target_w=self.frame_w
            )
            new_backend.attach_camera(camera_prim)
            self._backends.insert(0, new_backend)
            self.isaac_backend = new_backend

    # ─────────────────────────────────────────────────────────────────────
    # Legacy API — kept for drop-in compatibility
    # ─────────────────────────────────────────────────────────────────────

    def get_frame(self) -> np.ndarray:
        """Legacy: return raw HxWx3 uint8 BGR frame."""
        vf = self._capture_and_process()
        return vf.raw if vf is not None else np.zeros(
            (self.frame_h, self.frame_w, 3), dtype=np.uint8
        )

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Legacy: normalise and transpose to CHW float32.
        Also runs the full pipeline so visual vocab updates happen.
        """
        vf = self._process_raw(frame, source="external")
        return vf.tensor if vf.tensor is not None else (
            frame.astype(np.float32) / 255.0
        ).transpose(2, 0, 1)

    # ─────────────────────────────────────────────────────────────────────
    # Primary observe() — called from agent.observe()
    # ─────────────────────────────────────────────────────────────────────

    def observe(self, frame: Optional[np.ndarray] = None,
                info: Optional[Dict[str, Any]] = None) -> "VisualFrame":
        """
        Process one frame (or capture a new one) and return a VisualFrame.

        - Updates the online visual vocabulary
        - Stores the event in agent memory (if agent is attached)
        - Forwards the proprio vector to the WorldModel buffer
        """
        info = info or {}

        if frame is not None:
            vf = self._process_raw(frame, source=info.get("source", "external"))
        else:
            vf = self._capture_and_process()

        if vf is None:
            return VisualFrame(
                raw=np.zeros((self.frame_h, self.frame_w, 3), dtype=np.uint8),
                source="empty",
            )

        self.latest_frame = vf
        self._processed  += 1

        # ── Store in agent memory ──
        agent = self.agent
        if agent is not None and hasattr(agent, "memory"):
            token_name = self.vocab.name_of(vf.visual_token)
            event      = vf.to_memory_event(token_name)
            event.update({k: v for k, v in info.items()
                          if k not in event})
            try:
                agent.memory.remember(event, tags=["vision", "visual", "perception"])
            except Exception as e:
                log.debug(f"VisionAdapter: memory store error: {e}")

        # ── Forward to WorldModel buffer ──
        if agent is not None and hasattr(agent, "world_model_buffer"):
            buf = agent.world_model_buffer
            if buf is not None:
                try:
                    # vision tensor expected as (C, H, W) float32
                    vis = vf.tensor  # already CHW
                    proprio = vf.to_proprio_vector(dim=32)
                    last_action = getattr(agent, "last_action", None)
                    if last_action is not None:
                        # FIX: last_action is 18-dim for god agents (act_god()
                        # stores the full policy output before its own [:13]
                        # slice) - truncate to the world model's actual
                        # action_dim, same reasoning as world_model.py's
                        # _build_observation_from_context fix (dims 13-17 are
                        # a discrete ability trigger, not continuous movement).
                        wm = getattr(agent, "world_model", None)
                        adim = wm.config.action_dim if wm is not None else 13
                        action = np.asarray(last_action, dtype=np.float32)[:adim]
                    else:
                        # FIX: was 11 — must match TransformerPolicy.BASE_DIM=13
                        action = np.zeros(13, dtype=np.float32)
                    buf.add_step(
                        vision=vis,
                        proprio=proprio,
                        action=action,
                        reward=0.0,
                        termination=False,
                    )
                except Exception as e:
                    log.debug(f"VisionAdapter: world model buffer error: {e}")

        # ── Generate agent thought ──
        if agent is not None and hasattr(agent, "thoughts"):
            token_name = self.vocab.name_of(vf.visual_token)
            thought = (f"I see visual pattern '{token_name}' "
                       f"(token {vf.visual_token}, "
                       f"vocab size {self.vocab.n_clusters})")
            agent.thoughts.append({"timestamp": vf.timestamp, "thought": thought})
            if len(agent.thoughts) > 100:
                agent.thoughts = agent.thoughts[-100:]

        return vf

    # ─────────────────────────────────────────────────────────────────────
    # Background capture loop
    # ─────────────────────────────────────────────────────────────────────

    def start(self):
        """Start background capture + processing thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._capture_loop, daemon=True, name="vision-capture"
        )
        self._thread.start()
        log.info("VisionAdapter: background capture started.")

    def stop(self):
        """Stop background capture thread."""
        self._running = False
        for b in self._backends:
            b.close()

    def drain_frames(self) -> List[VisualFrame]:
        """Drain buffered VisualFrames (non-blocking)."""
        frames = []
        while True:
            try:
                frames.append(self._frame_queue.get_nowait())
            except queue.Empty:
                break
        return frames

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _active_backend(self) -> Optional[CaptureBackend]:
        """Return the first available backend."""
        # Legacy capture_func takes highest priority
        if self._capture_func is not None:
            return None  # handled separately in _capture_and_process

        for b in self._backends:
            if b.is_available():
                return b
        return None

    def _capture_and_process(self) -> Optional["VisualFrame"]:
        """Capture a frame from the best available source and process it."""
        # Legacy capture_func
        if self._capture_func is not None:
            raw = self._capture_func()
            if raw is not None:
                return self._process_raw(raw, source="capture_func")

        backend = self._active_backend()
        if backend is None:
            return None

        raw = backend.read()
        if raw is None:
            return None

        return self._process_raw(raw, source=backend.source_name())

    def _process_raw(self, raw: np.ndarray, source: str = "unknown") -> "VisualFrame":
        """Full processing pipeline for one raw BGR frame."""
        # 1. Normalise to CHW float32
        if raw.ndim == 2:
            raw = np.stack([raw, raw, raw], axis=-1)  # grayscale → BGR

        chw = raw.astype(np.float32) / 255.0
        if chw.shape[0] == 3 and len(chw.shape) == 3 and chw.shape[1] != 3:
            # Already CHW
            tensor = chw
        else:
            # HWC → CHW
            tensor = np.transpose(chw, (2, 0, 1))

        vf = VisualFrame(raw=raw, tensor=tensor, source=source)

        # 2. Feature extraction
        vf.features = self.extractor.extract(tensor)

        # 3. Visual vocabulary update → token assignment
        vf.visual_token = self.vocab.observe(vf.features)

        # 4. Optional depth
        if self.enable_depth and self._depth_estimator is not None:
            vf.depth = self._depth_estimator.estimate(raw)

        return vf

    def _capture_loop(self):
        interval = 1.0 / max(self.fps, 1.0)
        while self._running:
            t0 = time.time()
            try:
                vf = self.observe()
                if vf is not None:
                    if self._frame_queue.full():
                        try:
                            self._frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._frame_queue.put(vf)
            except Exception as e:
                log.error(f"VisionAdapter capture loop error: {e}")
            elapsed = time.time() - t0
            time.sleep(max(0.0, interval - elapsed))

    # ─────────────────────────────────────────────────────────────────────
    # Vocabulary / language grounding integration
    # ─────────────────────────────────────────────────────────────────────

    def ground_token(self, token: int, word: str):
        """
        The language system calls this when it discovers a correlation
        between a visual token and a word (e.g. agent hears "tree" while
        visual_token 7 is active → token 7 named 'tree').
        """
        self.vocab.assign_name(token, word)
        log.info(f"Vision grounding: token {token} ↔ '{word}'")

    def get_current_token_name(self) -> str:
        """Human-readable name of the visual token in the current frame."""
        if self.latest_frame is None:
            return "nothing"
        return self.vocab.name_of(self.latest_frame.visual_token)

    # ─────────────────────────────────────────────────────────────────────
    # Stats, save, load
    # ─────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        active = self._active_backend()
        return {
            "processed_frames":   self._processed,
            "active_backend":     active.source_name() if active else "none",
            "all_backends":       [b.source_name() for b in self._backends],
            "vocab_stats":        self.vocab.get_stats(),
            "latest_token":       (self.latest_frame.visual_token
                                   if self.latest_frame else -1),
            "latest_token_name":  self.get_current_token_name(),
            "running":            self._running,
        }

    def state_dict(self) -> Dict[str, Any]:
        """Serialise for brain capsule persistence."""
        return {
            "vocab":     self.vocab.state_dict(),
            "extractor": self.extractor.state_dict(),
        }

    def load_state_dict(self, state: Dict[str, Any]):
        """Restore from brain capsule."""
        if "vocab" in state:
            self.vocab.load_state_dict(state["vocab"])
        if "extractor" in state and state["extractor"] is not None:
            self.extractor.load_state_dict(state["extractor"])
        log.info("VisionAdapter: state restored.")


# ─────────────────────────────────────────────────────────────────────────────
# Integration helper — called once per agent
# ─────────────────────────────────────────────────────────────────────────────

def add_vision_to_agent(
    agent,
    force_source: Any       = None,
    feature_dim: int        = 64,
    max_vocab_size: int     = 256,
    frame_h: int            = 84,
    frame_w: int            = 84,
    fps: float              = 15.0,
    enable_depth: bool      = True,
    auto_start: bool        = True,
    device: Optional[str]   = None,
) -> VisionAdapter:
    """
    Attach a VisionAdapter to `agent` and wire it into the existing
    observe() / cognitive_loop / world_model pipeline.

    Call once in NPCAgent.__init__ (or after it) instead of the old
    one-liner `self.vision_adapter = VisionAdapter()`.

    Parameters
    ----------
    agent           : NPCAgent instance
    force_source    : Override auto-detection with an explicit camera
                      index, file path, or RTSP URL.
    feature_dim     : Dimensionality of the learned feature vector.
    max_vocab_size  : Max number of visual tokens (clusters).
    frame_h, frame_w: Canonical frame size passed to the WorldModel.
    fps             : Background capture target frame rate.
    enable_depth    : Run the gradient-based depth estimator.
    auto_start      : Start background capture thread immediately.
    device          : Torch device string. Auto-detected if None.

    Returns
    -------
    VisionAdapter attached as agent.vision
    """
    if device is None:
        device = "cuda" if (_TORCH and torch.cuda.is_available()) else "cpu"

    vision = VisionAdapter(
        agent=agent,
        feature_dim=feature_dim,
        max_vocab_size=max_vocab_size,
        frame_h=frame_h,
        frame_w=frame_w,
        fps=fps,
        device=device,
        force_source=force_source,
        enable_depth=enable_depth,
    )

    agent.vision = vision

    # Also expose as vision_adapter for legacy call sites in agent.py
    agent.vision_adapter = vision

    # Override agent.observe() to route through full vision pipeline
    _patch_agent_observe(agent)

    # Wire Minecraft frame injection into the communication protocol
    _wire_minecraft_protocol(agent)

    # Patch cognitive loop to consume vision results
    _patch_cognitive_loop(agent)

    if auto_start:
        vision.start()

    log.info(
        f"[{agent.agent_id}] VisionAdapter attached "
        f"(device={device}, vocab_max={max_vocab_size}, fps={fps})."
    )
    return vision


def _patch_agent_observe(agent):
    """Replace agent.observe() with the full vision pipeline."""
    original_observe = agent.observe

    def vision_observe(image: np.ndarray,
                       info: Optional[Dict[str, Any]] = None) -> np.ndarray:
        info = info or {}
        vision: VisionAdapter = agent.vision

        # Run through VisionAdapter
        vf = vision.observe(frame=image, info=info)

        # Keep legacy contract: return CHW float32 preprocessed array
        if vf.tensor is not None:
            return vf.tensor
        return image.astype(np.float32).transpose(2, 0, 1) / 255.0

    agent.observe = vision_observe
    log.info(f"[{agent.agent_id}] agent.observe() patched for VisionAdapter.")


def _wire_minecraft_protocol(agent):
    """
    Register a hook so the communication protocol calls
    agent.vision.push_minecraft_frame() whenever a vision packet arrives.
    """
    try:
        import ai_core.communication_protocol as proto
        original_handler = getattr(proto, "_on_visual_frame", None)

        def on_visual_frame(agent_id: str, frame_bgr: np.ndarray):
            if agent_id == agent.agent_id and hasattr(agent, "vision"):
                agent.vision.push_minecraft_frame(frame_bgr)
            if original_handler:
                original_handler(agent_id, frame_bgr)

        proto._on_visual_frame = on_visual_frame
        log.info(f"[{agent.agent_id}] Minecraft vision frame hook registered.")
    except Exception as e:
        log.debug(f"Minecraft vision wire-up skipped: {e}")


def _patch_cognitive_loop(agent):
    """
    Augment CognitiveLoop._perceive() to include the latest visual token
    and visual novelty in the perception dict.
    """
    if not hasattr(agent, "cognitive_loop") or agent.cognitive_loop is None:
        return

    original_perceive = agent.cognitive_loop._perceive

    def vision_perceive():
        perception = original_perceive()

        vision: Optional[VisionAdapter] = getattr(agent, "vision", None)
        if vision is None:
            return perception

        # Drain buffered frames
        frames = vision.drain_frames()
        if not frames:
            lf = vision.latest_frame
            if lf:
                frames = [lf]

        if frames:
            latest = frames[-1]
            token_name = vision.vocab.name_of(latest.visual_token)

            # Visual novelty: how often has this token been seen?
            token_count = vision.vocab._counts[latest.visual_token] \
                if latest.visual_token < len(vision.vocab._counts) else 1
            visual_novelty = 1.0 / (1.0 + float(token_count) / 10.0)

            perception["novelty"] = max(
                perception.get("novelty", 0.0), visual_novelty
            )
            perception["visual_token"]      = latest.visual_token
            perception["visual_token_name"] = token_name
            perception["has_depth"]         = latest.depth is not None

        return perception

    agent.cognitive_loop._perceive = vision_perceive
    log.info(f"[{agent.agent_id}] CognitiveLoop patched for vision tokens.")