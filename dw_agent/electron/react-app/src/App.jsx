import React, { useState, useEffect, useRef, useLayoutEffect } from "react";
import { Globe, Plus, Trash2, Check, X, Box, Upload, Brain, Send, Monitor, Terminal, LayoutGrid, Activity, ChevronDown, ChevronUp, HardDrive, Cpu, Network } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import MessageBubble from "./components/MessageBubble.jsx";
import AgentStatus from "./components/AgentStatus.jsx";
import FileDropZone from "./components/FileDropZone.jsx";
import ControllerSafety from "./ControllerSafety.jsx";
import WorldModelVisualizer from "./components/WorldModelVisualizer.jsx";
import MentalMatrixModal from "./components/MentalMatrixModal.jsx";

const BACKEND_URL = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws";
const AGENT_ID = "demo";

// Simple 3D Visualization Component
function Simple3DRenderer({ data }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [showMesh, setShowMesh] = useState(true);
  const [rotation, setRotation] = useState({ x: 20, y: 30 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [containerSize, setContainerSize] = useState({ width: 400, height: 300 });
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        setContainerSize({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
      handleResize();
    }

    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    if (!canvasRef.current || !data) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    // Modern Dark Background with subtle gradient feel
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const rotatePoint3D = (x, y, z, rx, ry) => {
      rx = (rx * Math.PI) / 180;
      ry = (ry * Math.PI) / 180;

      let y1 = y * Math.cos(rx) - z * Math.sin(rx);
      let z1 = y * Math.sin(rx) + z * Math.cos(rx);

      let x2 = x * Math.cos(ry) + z1 * Math.sin(ry);
      let z2 = -x * Math.sin(ry) + z1 * Math.cos(ry);

      return { x: x2, y: y1, z: z2 };
    };

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    if (data.type === 'matrix' || data.type === 'world_model') {
      const size = Math.min(canvas.width, canvas.height) * 0.3;

      const corners = [
        { x: -size, y: -size, z: -size },
        { x: size, y: -size, z: -size },
        { x: size, y: size, z: -size },
        { x: -size, y: size, z: -size },
        { x: -size, y: -size, z: size },
        { x: size, y: -size, z: size },
        { x: size, y: size, z: size },
        { x: -size, y: size, z: size }
      ];

      const rotatedCorners = corners.map(c => rotatePoint3D(c.x, c.y, c.z, rotation.x, rotation.y));

      const edges = [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7]
      ];

      ctx.strokeStyle = 'rgba(99, 102, 241, 0.6)'; // Indigo 500
      ctx.lineWidth = 1.5;

      edges.forEach(([start, end]) => {
        const p1 = rotatedCorners[start];
        const p2 = rotatedCorners[end];
        ctx.beginPath();
        ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
        ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
        ctx.stroke();
      });

      ctx.fillStyle = '#6366f1'; // Indigo 500
      rotatedCorners.forEach(p => {
        ctx.beginPath();
        ctx.arc(centerX + p.x * zoom, centerY + p.y * zoom, 3, 0, Math.PI * 2);
        ctx.fill();
      });

      if (showMesh) {
        const gridDivisions = 4;
        const step = (size * 2) / gridDivisions;

        ctx.strokeStyle = 'rgba(6, 182, 212, 0.2)'; // Cyan 500
        ctx.lineWidth = 0.5;

        for (let y = -size; y <= size; y += step) {
          for (let z = -size; z <= size; z += step) {
            for (let x = -size; x < size; x += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y);
              const p2 = rotatePoint3D(x + step, y, z, rotation.x, rotation.y);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }

        for (let x = -size; x <= size; x += step) {
          for (let z = -size; z <= size; z += step) {
            for (let y = -size; y < size; y += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y);
              const p2 = rotatePoint3D(x, y + step, z, rotation.x, rotation.y);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }

        for (let x = -size; x <= size; x += step) {
          for (let y = -size; y <= size; y += step) {
            for (let z = -size; z < size; z += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y);
              const p2 = rotatePoint3D(x, y, z + step, rotation.x, rotation.y);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }
      }

      // Render objects in the mental workspace
      if (data.objects && data.objects.length > 0) {
        const sortedObjects = [...data.objects].sort((a, b) => {
          const posA = a.position || [0, 0, 0];
          const posB = b.position || [0, 0, 0];
          const rotA = rotatePoint3D(posA[0] * size / 16, posA[1] * size / 16, posA[2] * size / 16, rotation.x, rotation.y);
          const rotB = rotatePoint3D(posB[0] * size / 16, posB[1] * size / 16, posB[2] * size / 16, rotation.x, rotation.y);
          return rotA.z - rotB.z;
        });

        sortedObjects.forEach(obj => {
          const pos = obj.position || [0, 0, 0];
          const objType = obj.type || 'unknown';
          const label = obj.label || objType;
          const x = pos[0] * size / 16;
          const y = pos[1] * size / 16;
          const z = pos[2] * size / 16;
          const rotated = rotatePoint3D(x, y, z, rotation.x, rotation.y);
          const depthFactor = (rotated.z + size) / (size * 2);
          const opacity = 0.5 + depthFactor * 0.5;

          if (objType === 'block' || objType === 'cube') {
            const blockSize = 10 * zoom;
            ctx.fillStyle = `rgba(99, 102, 241, ${opacity})`;
            ctx.strokeStyle = `rgba(129, 140, 248, ${opacity})`;
            ctx.lineWidth = 1;
            ctx.fillRect(centerX + rotated.x * zoom - blockSize/2, centerY + rotated.y * zoom - blockSize/2, blockSize, blockSize);
            ctx.strokeRect(centerX + rotated.x * zoom - blockSize/2, centerY + rotated.y * zoom - blockSize/2, blockSize, blockSize);
          } else if (objType === 'entity' || objType === 'agent') {
            const radius = 8 * zoom;
            ctx.fillStyle = `rgba(244, 63, 94, ${opacity})`;
            ctx.strokeStyle = `rgba(251, 113, 133, ${opacity})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(centerX + rotated.x * zoom, centerY + rotated.y * zoom, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          } else if (objType === 'goal' || objType === 'target') {
            const radius = 6 * zoom;
            ctx.fillStyle = `rgba(234, 179, 8, ${opacity})`;
            ctx.strokeStyle = `rgba(250, 204, 21, ${opacity})`;
            ctx.beginPath();
            ctx.moveTo(centerX + rotated.x * zoom, centerY + rotated.y * zoom - radius);
            ctx.lineTo(centerX + rotated.x * zoom + radius, centerY + rotated.y * zoom + radius);
            ctx.lineTo(centerX + rotated.x * zoom - radius, centerY + rotated.y * zoom + radius);
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
          } else {
            const radius = 5 * zoom;
            ctx.fillStyle = `rgba(34, 197, 94, ${opacity})`;
            ctx.strokeStyle = `rgba(74, 222, 128, ${opacity})`;
            ctx.beginPath();
            ctx.arc(centerX + rotated.x * zoom, centerY + rotated.y * zoom, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          }

          ctx.fillStyle = 'rgba(2, 6, 23, 0.7)';
          ctx.font = 'bold 10px Inter, sans-serif';
          const textWidth = ctx.measureText(label).width;
          ctx.fillRect(centerX + rotated.x * zoom + 12, centerY + rotated.y * zoom - 8, textWidth + 4, 14);
          ctx.fillStyle = `rgba(248, 250, 252, ${opacity})`;
          ctx.fillText(label, centerX + rotated.x * zoom + 14, centerY + rotated.y * zoom + 3);
        });
      }

    } else if (data.type === 'thought_flow') {
      const radius = Math.min(canvas.width, canvas.height) * 0.25;
      const points = [];
      for (let i = 0; i < 8; i++) {
        const angle1 = (i / 8) * Math.PI * 2;
        const angle2 = Math.PI / 4;
        points.push({
          x: radius * Math.cos(angle1) * Math.sin(angle2),
          y: radius * Math.sin(angle1) * Math.sin(angle2),
          z: radius * Math.cos(angle2)
        });
      }
      const rotatedPoints = points.map(p => rotatePoint3D(p.x, p.y, p.z, rotation.x, rotation.y));
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.4)';
      ctx.lineWidth = 1;
      rotatedPoints.forEach((point, i) => {
        rotatedPoints.forEach((other, j) => {
          if (i < j && Math.random() > 0.6) {
            ctx.beginPath();
            ctx.moveTo(centerX + point.x, centerY + point.y);
            ctx.lineTo(centerX + other.x, centerY + other.y);
            ctx.stroke();
          }
        });
      });
      ctx.fillStyle = '#06b6d4';
      rotatedPoints.forEach(point => {
        ctx.beginPath();
        ctx.arc(centerX + point.x, centerY + point.y, 4, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
    ctx.font = 'bold 10px Inter, sans-serif';
    ctx.fillText(data.label?.toUpperCase() || 'AI MENTAL WORKSPACE', 15, 25);
    if (data.objects && data.objects.length > 0) {
      ctx.fillText(`ENTITIES: ${data.objects.length}`, 15, 40);
    }

  }, [data, showMesh, rotation, containerSize, zoom]);

  const handleMouseDown = (e) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e) => {
    if (!isDragging) return;
    const deltaX = e.clientX - dragStart.x;
    const deltaY = e.clientY - dragStart.y;
    setRotation(prev => ({
      x: prev.x - deltaY * 0.5,
      y: prev.y + deltaX * 0.5
    }));
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => setIsDragging(false);
  const resetRotation = () => setRotation({ x: 20, y: 30 });
  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prev => Math.max(0.5, Math.min(3, prev * delta)));
  };

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, dragStart]);

  return (
    <div className="flex flex-col gap-2 h-full w-full overflow-hidden">
      <div className="flex items-center justify-between gap-2 flex-shrink-0 px-1">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              checked={showMesh}
              onChange={(e) => setShowMesh(e.target.checked)}
              className="checkbox checkbox-xs checkbox-primary"
            />
            <span className="text-[10px] font-bold uppercase tracking-tight text-slate-400 group-hover:text-indigo-400 transition-colors">Mesh</span>
          </label>
        </div>
        <div className="text-[10px] font-mono text-slate-500 bg-slate-800/50 px-2 py-0.5 rounded border border-slate-700/50">
          Z:{zoom.toFixed(1)} R:{rotation.x.toFixed(0)},{rotation.y.toFixed(0)}
        </div>
        <button onClick={resetRotation} className="btn btn-[10px] h-6 min-h-6 btn-ghost px-2 text-slate-500 hover:text-indigo-400">
          ↺ Reset
        </button>
      </div>
      <div
        ref={containerRef}
        className="flex-1 bg-slate-950 rounded-xl overflow-hidden relative border border-slate-800/50 shadow-inner group"
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
      >
        <canvas
          ref={canvasRef}
          width={containerSize.width}
          height={containerSize.height}
          className="w-full h-full cursor-grab active:cursor-grabbing transition-opacity duration-300"
          title="Drag to rotate"
        />
        <div className="absolute inset-0 pointer-events-none border border-white/5 rounded-xl"></div>
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-slate-900/80 backdrop-blur-sm px-3 py-1 rounded-full text-[9px] text-slate-400 border border-slate-700/50 pointer-events-none uppercase tracking-widest font-bold">
          Orbit Drag • Scroll Zoom
        </div>
      </div>
    </div>
  );
}

// Web Access Manager
function WebAccessManager({ onWebsitesChange }) {
  const [websites, setWebsites] = useState([]);
  const [newUrl, setNewUrl] = useState("");
  const [isAdding, setIsAdding] = useState(false);

  useEffect(() => {
    if (websites.length > 0) {
      fetch(`${BACKEND_URL}/api/agents/${AGENT_ID}/web/allow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ websites })
      })
        .then(res => res.json())
        .then(data => console.log('✅ Websites synced to AI:', data))
        .catch(err => console.error('Failed to sync websites:', err));
    }
  }, [websites]);

  const addWebsite = () => {
    if (!newUrl.trim()) return;
    try {
      let urlString = newUrl.trim();
      if (!urlString.startsWith('http')) {
        urlString = 'https://' + urlString;
      }
      const url = new URL(urlString);

      // If the path is just '/', it's likely a domain authorization
      const isDomainOnly = url.pathname === '/' && !url.search && !url.hash;

      const website = {
        id: Date.now(),
        url: url.href,
        display: isDomainOnly ? url.hostname : url.href,
        type: isDomainOnly ? 'domain' : 'url',
        enabled: true,
        addedAt: new Date().toISOString()
      };
      const updated = [...websites, website];
      setWebsites(updated);
      onWebsitesChange(updated);
      setNewUrl("");
      setIsAdding(false);
    } catch (e) {
      alert("Invalid URL. Please enter a valid website address.");
    }
  };

  const toggleWebsite = (id) => {
    const updated = websites.map(w => w.id === id ? { ...w, enabled: !w.enabled } : w);
    setWebsites(updated);
    onWebsitesChange(updated);
  };

  const removeWebsite = (id) => {
    const updated = websites.filter(w => w.id !== id);
    setWebsites(updated);
    onWebsitesChange(updated);
  };

  return (
    <div className="space-y-3 glass-card p-4 rounded-xl">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold uppercase tracking-widest flex items-center gap-2 text-indigo-400">
          <Globe className="w-3.5 h-3.5" />
          Network Permission Layer
        </h3>
        <button onClick={() => setIsAdding(!isAdding)} className="btn btn-xs btn-primary h-7 rounded-lg">
          <Plus className="w-3 h-3" />
          Authorize
        </button>
      </div>

      {isAdding && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-4 bg-indigo-600/10 rounded-2xl border-2 border-dashed border-indigo-500/50 space-y-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-widest text-indigo-400">Add New Domain</span>
            <button onClick={() => setIsAdding(false)} className="text-slate-500 hover:text-white transition-colors">
              <X className="w-3 h-3" />
            </button>
          </div>
          <div className="flex gap-2 p-1 bg-slate-950/80 rounded-xl border border-white/10 ring-4 ring-indigo-500/5">
            <input
              autoFocus
              type="text"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="e.g. google.com"
              className="input input-sm flex-1 bg-transparent border-none focus:ring-0 text-xs text-white placeholder:text-slate-600 px-3"
              onKeyPress={(e) => e.key === 'Enter' && addWebsite()}
            />
            <button
              onClick={addWebsite}
              className="btn btn-sm bg-indigo-500 hover:bg-indigo-400 border-none h-8 w-8 p-0 min-h-0 rounded-lg shadow-lg shadow-indigo-500/20 transition-all active:scale-95"
            >
              <Check className="w-4 h-4 text-white" />
            </button>
          </div>
          <p className="text-[9px] text-slate-500 leading-tight">
            The AI will only be able to browse sites within these authorized domains.
          </p>
        </motion.div>
      )}

      <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
        {websites.length === 0 ? (
          <div className="text-center py-6 text-slate-600">
            <p className="text-[10px] uppercase font-bold tracking-tighter opacity-50">Isolated Environment</p>
          </div>
        ) : (
          websites.map(website => (
            <div
              key={website.id}
              className={`flex items-center justify-between p-2 rounded-lg border transition-all ${
                website.enabled
                  ? 'bg-slate-800/30 border-slate-700/50'
                  : 'bg-slate-900/10 border-transparent opacity-40'
              }`}
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <input
                  type="checkbox"
                  checked={website.enabled}
                  onChange={() => toggleWebsite(website.id)}
                  className="checkbox checkbox-xs checkbox-primary"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-bold truncate text-slate-200">{website.display}</p>
                  <p className="text-[8px] uppercase tracking-widest text-slate-500 font-black">{website.type}</p>
                </div>
              </div>
              <button onClick={() => removeWebsite(website.id)} className="btn btn-xs btn-ghost h-6 w-6 p-0 min-h-0 text-slate-600 hover:text-rose-500">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Activity Bar Component
function ActivityBar({ activities, theme }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center justify-between w-full px-4 py-2 transition-colors border rounded-xl group ${
          theme === 'dark'
          ? 'bg-slate-900/40 hover:bg-slate-800/60 border-white/5'
          : 'bg-slate-200/50 hover:bg-slate-300/50 border-slate-300/50'
        }`}
      >
        <div className="flex items-center gap-3">
          <Activity className={`w-4 h-4 ${activities.length > 0 ? 'text-indigo-400 animate-pulse' : 'text-slate-500'}`} />
          <span className={`text-[10px] font-black uppercase tracking-[0.2em] ${theme === 'dark' ? 'text-slate-300' : 'text-slate-700'}`}>System Activity Log</span>
          {activities.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-md bg-indigo-500/20 border border-indigo-500/30 text-[9px] font-bold text-indigo-400">
              {activities.length}
            </span>
          )}
        </div>
        {isOpen ? <ChevronDown className="w-3 h-3 text-slate-500" /> : <ChevronUp className="w-3 h-3 text-slate-500" />}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden mt-2 space-y-2"
          >
            {activities.length === 0 ? (
              <div className="p-4 text-center glass-card rounded-xl">
                <p className="text-[9px] text-slate-600 uppercase font-bold tracking-widest">No Recent Telemetry</p>
              </div>
            ) : (
              <div className="max-h-32 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                {activities.map((activity, i) => (
                  <div key={i} className={`flex items-center gap-3 p-2 border rounded-lg ${
                    theme === 'dark' ? 'bg-slate-900/40 border-white/5' : 'bg-white border-slate-200'
                  }`}>
                    {activity.type === 'web' ? <Globe className="w-3 h-3 text-cyan-400" /> :
                     activity.type === 'file' ? <HardDrive className="w-3 h-3 text-indigo-400" /> :
                     activity.type === 'controller' ? <Cpu className="w-3 h-3 text-rose-400" /> :
                     <Network className="w-3 h-3 text-slate-400" />}
                    <div className="flex-1 min-w-0">
                      <p className={`text-[9px] font-bold truncate uppercase ${theme === 'dark' ? 'text-slate-300' : 'text-slate-700'}`}>{activity.title}</p>
                      <p className="text-[8px] text-slate-500 font-mono truncate">{activity.time}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Main App
function App() {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [activities, setActivities] = useState([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("chat");
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    document.body.className = theme === "light" ? "light-theme" : "";
  }, [theme]);
  const [visualizationData, setVisualizationData] = useState({ type: 'matrix', label: 'Mental Matrix' });
  const [allowedWebsites, setAllowedWebsites] = useState([]);
  const [showWebManager, setShowWebManager] = useState(false);
  const [brainActive, setBrainActive] = useState(false);
  const [worldModelData, setWorldModelData] = useState(null);
  const [showMentalMatrix, setShowMentalMatrix] = useState(false);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const messagesEndRef = useRef(null);
  const thoughtsEndRef = useRef(null);

  const scrollToBottom = (ref) => {
    if (ref.current) {
      ref.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  };

  useLayoutEffect(() => {
    scrollToBottom(messagesEndRef);
  }, [messages]);

  useLayoutEffect(() => {
    scrollToBottom(thoughtsEndRef);
  }, [thoughts]);

// WebSocket connection
useEffect(() => {
  const connectWebSocket = () => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
      setError("System interface offline");
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        const now = new Date().toLocaleTimeString();

        switch (data.type) {
          case "chat":
            setMessages((m) => [...m, { sender: data.from || "agent", text: data.text }]);
            break;
          case "agent_thought":
            if (data.internal_thought) {
              setThoughts((t) => [...t, data.internal_thought]);
            }
            setBrainActive(true);
            setTimeout(() => setBrainActive(false), 2000);
            break;
          case "agent_speech":
            setMessages((m) => [...m, { sender: data.agent_id || 'agent', text: data.text }]);
            break;
          case "visualization_update":
            setVisualizationData(data.data);
            break;
          case "world_model_update":
            setWorldModelData(data.data);
            break;
          case "activity_update":
            setActivities(prev => [{
              type: data.activity_type || 'default',
              title: data.title || 'System Event',
              time: now
            }, ...prev].slice(0, 20));
            break;
        }
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };
  };

  connectWebSocket();
  return () => {
    if (wsRef.current) wsRef.current.close();
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
  };
}, []);

  const sendMessage = async (customText = null) => {
    const messageToSend = customText !== null ? customText : text;
    if (!messageToSend.trim()) return;

    try {
      setMessages((m) => [...m, { sender: "user", text: messageToSend }]);
      if (customText === null) setText("");

      const form = new FormData();
      form.append("message", messageToSend);
      form.append("agent_id", AGENT_ID);
      if (allowedWebsites.filter(w => w.enabled).length > 0) {
        form.append("allowed_websites", JSON.stringify(
          allowedWebsites.filter(w => w.enabled).map(w => w.url)
        ));
      }

      const response = await fetch(`${BACKEND_URL}/chat`, { method: 'POST', body: form });
      if (response.ok) {
        const data = await response.json();
        setMessages((m) => [...m, { sender: "agent", text: data.response }]);
      }
    } catch (err) {
      setError(`Transmission failed: ${err.message}`);
    }
  };

  const onFileSend = async (file, type, sync = false) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("agent_id", AGENT_ID);
      formData.append("filetype", type);
      const url = `${BACKEND_URL}/api/upload${sync ? '?sync=true' : ''}`;
      const response = await fetch(url, { method: "POST", body: formData });
      if (!response.ok) throw new Error(`Upload failed`);
      setMessages(m => [...m, { sender: "system", text: `DATAFRAME RECEIVED: ${file.name}` }]);

      setActivities(prev => [{
        type: 'file',
        title: `Uploaded: ${file.name}`,
        time: new Date().toLocaleTimeString()
      }, ...prev].slice(0, 20));

    } catch (err) {
      setError(`Data ingestion failed`);
    }
  };

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  const dismissError = () => setError(null);

  return (
    <div className={`h-screen w-screen overflow-hidden font-sans selection:bg-indigo-500/30`}>
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ x: 100, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 100, opacity: 0 }}
            className="fixed top-4 right-4 z-[9999] flex items-center gap-4 px-6 py-4 rounded-2xl bg-rose-600 shadow-2xl shadow-rose-900/40 text-white border border-rose-400/50 backdrop-blur-xl"
          >
            <div className="p-2 bg-white/20 rounded-xl">
              <Terminal className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-black uppercase tracking-widest opacity-70">System Alert</span>
              <span className="text-sm font-bold">{error}</span>
            </div>
            <button
              onClick={dismissError}
              className="ml-4 p-2 hover:bg-white/10 rounded-full transition-colors"
              aria-label="Close alert"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {mode === "controller" ? (
        <ControllerSafety
          onModeChange={() => setMode("chat")}
          messages={messages}
          sendMessage={sendMessage}
          inputText={text}
          setInputText={setText}
        />
      ) : (
        <div className="flex h-full w-full p-3 gap-3">
          {/* Main Interface (Left Side) */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col flex-[2] rounded-3xl overflow-hidden glass-card relative"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent pointer-events-none"></div>

            {/* Top Bar */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 relative z-10">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-indigo-500/10 rounded-xl border border-indigo-500/20">
                  <Monitor className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <h1 className={`text-sm font-black uppercase tracking-[0.2em] ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>
                    DIVINE WORLD <span className="text-indigo-500">v2.1</span>
                  </h1>
                  <p className="text-[10px] text-slate-500 font-mono tracking-tighter">CORE_INTERFACE_ADDR: {AGENT_ID}.local</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <AgentStatus connected={connected} active={brainActive} />
                <button onClick={toggleTheme} className="btn btn-circle btn-ghost btn-sm hover:bg-white/5">
                  {theme === "dark" ? "☀️" : "🌙"}
                </button>
              </div>
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2 custom-scrollbar">
              <div className="flex flex-col gap-2 min-h-full">
                <AnimatePresence initial={false}>
                  {messages.map((msg, i) => (
                    <MessageBubble key={i} sender={msg.sender} text={msg.text} />
                  ))}
                </AnimatePresence>
                <div ref={messagesEndRef} className="h-4 w-full" />
              </div>
            </div>

            {/* Input Area */}
            <div className={`p-4 backdrop-blur-xl border-t border-white/5 relative z-10 ${theme === 'dark' ? 'bg-slate-900/50' : 'bg-slate-100/50'}`}>
              <FileDropZone onFileSend={onFileSend} />

              <div className="mt-4 flex flex-col gap-3">
                <div className="relative group">
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Input command or query..."
                    className={`w-full border rounded-2xl py-4 pl-6 pr-14 text-sm focus:outline-none focus:border-indigo-500/50 focus:ring-4 focus:ring-indigo-500/10 transition-all placeholder:text-slate-500 font-medium ${theme === 'dark' ? 'bg-slate-950/50 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'}`}
                    onKeyPress={(e) => e.key === "Enter" && sendMessage()}
                  />
                  <button
                    onClick={() => sendMessage()}
                    className="absolute right-2 top-2 bottom-2 aspect-square flex items-center justify-center bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-all shadow-lg shadow-indigo-500/20 active:scale-90"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex items-center justify-between px-1">
                  <div className="flex gap-2">
                    <button onClick={() => setShowWebManager(!showWebManager)} className={`btn btn-xs h-7 rounded-lg border-none flex items-center gap-2 transition-all ${showWebManager ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' : 'bg-slate-800 hover:bg-slate-700 text-slate-400'}`}>
                      <Globe className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-wider">Web Access</span>
                    </button>
                    <button onClick={() => setMode("controller")} className="btn btn-xs h-7 rounded-lg border-none bg-slate-800 hover:bg-slate-700 text-slate-400 flex items-center gap-2">
                      <LayoutGrid className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-wider">Controller</span>
                    </button>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/50 px-3 py-1 rounded-full border border-slate-700/50">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></div>
                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Mode: {mode}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Right Panel (Analytics & Mental Workspace) */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col flex-1 gap-3 overflow-hidden"
          >
            {/* Visualizer Panel */}
            <div className="flex flex-col flex-[1.2] glass-card rounded-3xl overflow-hidden relative">
              <div className={`flex items-center justify-between px-5 py-4 border-b border-white/5 relative z-10 backdrop-blur-md ${theme === 'dark' ? 'bg-slate-900/40' : 'bg-white/40'}`}>
                <div className="flex items-center gap-3">
                  <div className="p-1.5 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
                    <Box className="w-4 h-4 text-indigo-400" />
                  </div>
                  <h2 className={`text-[11px] font-black uppercase tracking-[0.2em] ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>Mental Workspace</h2>
                </div>
                <button
                  onClick={() => setShowMentalMatrix(true)}
                  className="btn btn-xs h-7 rounded-lg border-none bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/20 flex items-center gap-2"
                >
                  <Brain className="w-3.5 h-3.5" />
                  <span className="text-[9px] font-bold uppercase tracking-widest">Simulate</span>
                </button>
              </div>

              <div className="flex-1 p-2 relative bg-slate-950/20">
                <Simple3DRenderer data={visualizationData} />
              </div>

              {worldModelData && (
                <div className="p-2 border-t border-white/5 h-48">
                  <WorldModelVisualizer data={worldModelData} />
                </div>
              )}
            </div>

            {/* Thoughts & Activity Panel */}
            <div className="flex flex-col flex-1 glass-card rounded-3xl overflow-hidden relative">
              <div className={`flex items-center gap-3 px-5 py-4 border-b border-white/5 relative z-10 backdrop-blur-md ${theme === 'dark' ? 'bg-slate-900/40' : 'bg-white/40'}`}>
                <div className="p-1.5 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
                  <Terminal className="w-4 h-4 text-indigo-400" />
                </div>
                <h2 className={`text-[11px] font-black uppercase tracking-[0.2em] ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>Cognitive Stream</h2>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono custom-scrollbar">
                <div className="min-h-full">
                  <AnimatePresence initial={false}>
                    {thoughts.map((t, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: 10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="p-3 rounded-xl bg-slate-800/30 border border-slate-700/30 text-[11px] leading-relaxed text-slate-300 relative overflow-hidden group hover:bg-slate-800/50 transition-all"
                      >
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500/50 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <span className="text-indigo-400/50 mr-2 opacity-50">[{i.toString().padStart(3, '0')}]</span>
                        {t}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  <div ref={thoughtsEndRef} className="h-4 w-full" />
                </div>
              </div>

              <div className={`p-4 border-t border-white/5 ${theme === 'dark' ? 'bg-slate-900/60' : 'bg-slate-100/60'}`}>
                <ActivityBar activities={activities} theme={theme} />

                <AnimatePresence>
                  {showWebManager && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="mt-4 pt-4 border-t border-white/5"
                    >
                      <WebAccessManager onWebsitesChange={setAllowedWebsites} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Mental Matrix Modal */}
      <MentalMatrixModal
        isOpen={showMentalMatrix}
        onClose={() => setShowMentalMatrix(false)}
        agentId={AGENT_ID}
      />
    </div>
  );
}

export default App;
