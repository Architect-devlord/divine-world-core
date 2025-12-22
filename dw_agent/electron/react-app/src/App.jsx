import React, { useState, useEffect, useRef } from "react";
import { Globe, Plus, Trash2, Check, X, Box, Upload } from "lucide-react";
import MessageBubble from "./components/MessageBubble.jsx";
import AgentStatus from "./components/AgentStatus.jsx";
import FileDropZone from "./components/FileDropZone.jsx";
import ControllerSafety from "./ControllerSafety.jsx";

const BACKEND_URL = "http://127.0.0.1:11400";
const WS_URL = "ws://127.0.0.1:11400/ws/agent";
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
    
    ctx.fillStyle = '#1e293b';
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
      
      ctx.strokeStyle = '#1e40af';
      ctx.lineWidth = 2;
      
      edges.forEach(([start, end]) => {
        const p1 = rotatedCorners[start];
        const p2 = rotatedCorners[end];
        ctx.beginPath();
        ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
        ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
        ctx.stroke();
      });
      
      ctx.fillStyle = 'rgba(30, 64, 175, 0.8)';
      rotatedCorners.forEach(p => {
        ctx.beginPath();
        ctx.arc(centerX + p.x * zoom, centerY + p.y * zoom, 4, 0, Math.PI * 2);
        ctx.fill();
      });
      
      if (showMesh) {
        const gridDivisions = 4;
        const step = (size * 2) / gridDivisions;
        
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 1;
        
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
        // Sort objects by z-depth for proper rendering order
        const sortedObjects = [...data.objects].sort((a, b) => {
          const posA = a.position || [0, 0, 0];
          const posB = b.position || [0, 0, 0];
          const rotA = rotatePoint3D(posA[0] * size / 16, posA[1] * size / 16, posA[2] * size / 16, rotation.x, rotation.y);
          const rotB = rotatePoint3D(posB[0] * size / 16, posB[1] * size / 16, posB[2] * size / 16, rotation.x, rotation.y);
          return rotA.z - rotB.z; // Render back to front
        });
        
        sortedObjects.forEach(obj => {
          const pos = obj.position || [0, 0, 0];
          const objType = obj.type || 'unknown';
          const label = obj.label || objType;
          
          // Scale position to fit within the cube
          const x = pos[0] * size / 16;
          const y = pos[1] * size / 16;
          const z = pos[2] * size / 16;
          
          const rotated = rotatePoint3D(x, y, z, rotation.x, rotation.y);
          
          // Calculate depth-based opacity for 3D effect
          const depthFactor = (rotated.z + size) / (size * 2);
          const opacity = 0.4 + depthFactor * 0.6;
          
          // Render different object types with distinct visuals
          if (objType === 'block' || objType === 'cube') {
            const blockSize = 10 * zoom;
            ctx.fillStyle = `rgba(30, 64, 175, ${opacity})`;
            ctx.strokeStyle = `rgba(59, 130, 246, ${opacity})`;
            ctx.lineWidth = 2;
            ctx.fillRect(
              centerX + rotated.x * zoom - blockSize/2,
              centerY + rotated.y * zoom - blockSize/2,
              blockSize, blockSize
            );
            ctx.strokeRect(
              centerX + rotated.x * zoom - blockSize/2,
              centerY + rotated.y * zoom - blockSize/2,
              blockSize, blockSize
            );
          } else if (objType === 'entity' || objType === 'agent') {
            const radius = 8 * zoom;
            ctx.fillStyle = `rgba(239, 68, 68, ${opacity})`;
            ctx.strokeStyle = `rgba(248, 113, 113, ${opacity})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(centerX + rotated.x * zoom, centerY + rotated.y * zoom, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          } else if (objType === 'goal' || objType === 'target') {
            const radius = 6 * zoom;
            ctx.fillStyle = `rgba(234, 179, 8, ${opacity})`;
            ctx.strokeStyle = `rgba(250, 204, 21, ${opacity})`;
            ctx.lineWidth = 2;
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
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(centerX + rotated.x * zoom, centerY + rotated.y * zoom, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          }
          
          // Draw label with background for better visibility
          ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
          ctx.font = '11px monospace';
          const textWidth = ctx.measureText(label).width;
          ctx.fillRect(
            centerX + rotated.x * zoom + 12,
            centerY + rotated.y * zoom - 8,
            textWidth + 4,
            14
          );
          ctx.fillStyle = `rgba(148, 163, 184, ${opacity})`;
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
      
      ctx.strokeStyle = 'rgba(34, 197, 94, 0.3)';
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
      
      ctx.fillStyle = '#22c55e';
      rotatedPoints.forEach(point => {
        ctx.beginPath();
        ctx.arc(centerX + point.x, centerY + point.y, 5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px monospace';
    ctx.fillText(data.label || 'AI Mental Workspace', 10, 20);
    
    if (data.objects && data.objects.length > 0) {
      ctx.fillText(`Objects: ${data.objects.length}`, 10, 35);
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
  
  const handleMouseUp = () => {
    setIsDragging(false);
  };
  
  const resetRotation = () => {
    setRotation({ x: 20, y: 30 });
  };
  
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
    <div className="flex flex-col gap-3 h-full w-full overflow-auto">
      <div className="flex items-center justify-between gap-2 flex-shrink-0">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showMesh}
              onChange={(e) => setShowMesh(e.target.checked)}
              className="checkbox checkbox-sm"
            />
            <span className="text-xs font-medium">Show Mesh</span>
          </label>
        </div>
        <div className="text-xs text-gray-500">
          X: {rotation.x.toFixed(0)}° Y: {rotation.y.toFixed(0)}° | Zoom: {zoom.toFixed(2)}x
        </div>
        <button onClick={resetRotation} className="btn btn-xs btn-ghost" title="Reset rotation">
          ↺ Reset
        </button>
      </div>
      <div 
        ref={containerRef}
        className="flex-1 bg-slate-900 rounded-lg overflow-hidden relative border border-slate-700"
        style={{ minHeight: '300px', minWidth: '300px', width: '100%', height: '100%' }}
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
      >
        <canvas 
          ref={canvasRef}
          width={containerSize.width}
          height={containerSize.height}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          title="Drag to rotate"
        />
      </div>
      <div className="text-xs text-gray-500 text-center flex-shrink-0">
        Drag to rotate • Scroll to zoom
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
      const url = new URL(newUrl.startsWith('http') ? newUrl : `https://${newUrl}`);
      const website = {
        id: Date.now(),
        url: url.href,
        domain: url.hostname,
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
    const updated = websites.map(w => 
      w.id === id ? { ...w, enabled: !w.enabled } : w
    );
    setWebsites(updated);
    onWebsitesChange(updated);
  };
  
  const removeWebsite = (id) => {
    const updated = websites.filter(w => w.id !== id);
    setWebsites(updated);
    onWebsitesChange(updated);
  };
  
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Globe className="w-4 h-4" />
          Web Access Control
        </h3>
        <button onClick={() => setIsAdding(!isAdding)} className="btn btn-xs btn-primary">
          <Plus className="w-3 h-3" />
          Add Site
        </button>
      </div>
      
      {isAdding && (
        <div className="flex gap-2 p-3 bg-slate-800 rounded-lg">
          <input
            type="text"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="Enter website URL (e.g., wikipedia.org)"
            className="input input-sm flex-1 bg-slate-900"
            onKeyPress={(e) => e.key === 'Enter' && addWebsite()}
          />
          <button onClick={addWebsite} className="btn btn-sm btn-success">
            <Check className="w-4 h-4" />
          </button>
          <button onClick={() => setIsAdding(false)} className="btn btn-sm btn-ghost">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {websites.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Globe className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No websites added yet</p>
            <p className="text-xs">Add websites to give AI access</p>
          </div>
        ) : (
          websites.map(website => (
            <div
              key={website.id}
              className={`flex items-center justify-between p-3 rounded-lg transition-all ${
                website.enabled 
                  ? 'bg-slate-800 border border-slate-700' 
                  : 'bg-slate-900 border border-slate-800 opacity-50'
              }`}
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <input
                  type="checkbox"
                  checked={website.enabled}
                  onChange={() => toggleWebsite(website.id)}
                  className="checkbox checkbox-sm checkbox-primary"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{website.domain}</p>
                  <p className="text-xs text-gray-500 truncate">{website.url}</p>
                </div>
              </div>
              <button onClick={() => removeWebsite(website.id)} className="btn btn-xs btn-ghost text-error">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
      </div>
      
      {websites.length > 0 && (
        <div className="text-xs text-gray-500 pt-2 border-t border-slate-800">
          {websites.filter(w => w.enabled).length} of {websites.length} sites enabled
        </div>
      )}
    </div>
  );
}

// Main App
function App() {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("chat");
  const [theme, setTheme] = useState("dark");
  const [visualizationData, setVisualizationData] = useState({ type: 'matrix', label: 'Mental Matrix' });
  const [allowedWebsites, setAllowedWebsites] = useState([]);
  const [showWebManager, setShowWebManager] = useState(false);
  const [brainActive, setBrainActive] = useState(false);
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  useEffect(() => {
    connectWebSocket();
    
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = () => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    
    // Binary protocol constants
    const MAGIC = 0x44574149; // 'DWAI'
    const FRAME_CHAT = 0x03;

    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log("[WS] Connected - sending handshake");
      // Send JSON handshake for protocol negotiation
      ws.send(JSON.stringify({
        agent_id: AGENT_ID,
        protocol: "binary",
        version: "2.1.0"
      }));
      console.log("[WS] Handshake sent, waiting for acknowledgment");
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = () => setError("WebSocket error");

    ws.onmessage = (ev) => {
      try {
        console.log('[WS] Received message. Type:', typeof ev.data, 'Size:', typeof ev.data === 'string' ? ev.data.length : ev.data.byteLength);
        
        // Handle JSON messages (fallback and responses)
        if (typeof ev.data === 'string') {
          console.log('[WS] Parsing JSON:', ev.data.substring(0, 150));
          const data = JSON.parse(ev.data);
          console.log('[WS] Parsed JSON type:', data.type);
          
          switch (data.type) {
            case "connected":
              setConnected(true);
              setError(null);
              console.log("[WS] ✅ Protocol negotiation successful:", data);
              console.log("[WS] ✅ WebSocket handler now registered for agent:", AGENT_ID);
              break;
              
            case "chat":
              setMessages((m) => [...m, { 
                sender: data.from || "agent", 
                text: data.text 
              }]);
              break;
              
            case "agent_thought":
              if (data.internal_thought) {
                setThoughts((t) => [...t, `💭 ${data.internal_thought}`]);
              }
              
              if (Array.isArray(data.chain)) {
                setThoughts((t) => [...t, ...data.chain]);
              } else if (data.text) {
                setThoughts((t) => [...t, data.text]);
              }
              
              setBrainActive(true);
              setTimeout(() => setBrainActive(false), 2000);
              
              if (data.visualization) {
                setVisualizationData(data.visualization);
              } else if (data.mental_workspace) {
                setVisualizationData({
                  type: 'world_model',
                  label: 'Mental Simulation',
                  objects: data.mental_workspace.objects || []
                });
              } else {
                setVisualizationData({ 
                  type: 'thought_flow', 
                  label: 'Thought Process' 
                });
              }
              break;
              
            case "internal_thought":
              if (data.thought) {
                setThoughts((t) => [...t, `💭 ${data.thought}`]);
              }
              break;

            case "agent_speech":
              // Agent emitted speech (TTS or spontaneous)
              console.log('[WS] 🗣️ agent_speech received:', data);
              console.log('[WS] 🗣️ Adding message from:', data.agent_id || 'agent', 'Text:', data.text);
              setMessages((m) => {
                const newMessages = [...m, { sender: data.agent_id || 'agent', text: data.text }];
                console.log('[WS] 🗣️ Messages array updated. Total messages:', newMessages.length);
                return newMessages;
              });
              break;
              
            case "visualization_update":
              setVisualizationData(data.data);
              break;
          }
        }
        // Handle binary frames for DWAI protocol
        else if (ev.data instanceof ArrayBuffer) {
          console.log('[WS] Received binary frame, size:', ev.data.byteLength);
          try {
            const buffer = ev.data;
            const view = new DataView(buffer);
            let offset = 0;
            const MAGIC = 0x44574149; // 'DWAI'
            const magic = view.getUint32(offset, false); offset += 4;
            console.log('[WS] Binary frame magic: 0x' + magic.toString(16));
            if (magic !== MAGIC) {
              console.warn('[WS] Unknown binary magic: 0x' + magic.toString(16));
              return;
            }

            const frameType = view.getUint32(offset, false); offset += 4;
            console.log('[WS] Binary frame type:', frameType, '(0x' + frameType.toString(16) + ')');

            // CHAT frame
            if (frameType === FRAME_CHAT) {
              console.log('[WS] 💬 Parsing binary CHAT frame');
              const agentIdLen = view.getUint32(offset, false); offset += 4;
              const agentIdBytes = new Uint8Array(buffer, offset, agentIdLen);
              const agentId = new TextDecoder().decode(agentIdBytes);
              offset += agentIdLen;

              // timestamp (double)
              const timestamp = view.getFloat64(offset, false); offset += 8;

              const msgLen = view.getUint32(offset, false); offset += 4;
              const msgBytes = new Uint8Array(buffer, offset, msgLen);
              const messageText = new TextDecoder().decode(msgBytes);

              console.log('[WS] 💬 Binary CHAT decoded. From:', agentId, 'Text:', messageText);
              // Append incoming agent message
              setMessages((m) => {
                const newMessages = [...m, { sender: agentId || 'agent', text: messageText, ts: timestamp }];
                console.log('[WS] 💬 Messages updated. Total:', newMessages.length);
                return newMessages;
              });
            } else {
              // Unknown frame types can be handled here (PERCEPTION/ACTION)
              console.debug('[WS] Received non-chat binary frame:', frameType);
            }
          } catch (be) {
            console.error('Failed to parse binary frame:', be);
          }
        }
      } catch (e) {
        console.error("Parse error:", e, "Data:", ev.data);
      }
    };
    
    // Export helper to send binary chat messages
    ws.sendBinaryChat = (message) => {
      try {
        const agentIdBytes = new TextEncoder().encode(AGENT_ID);
        const messageBytes = new TextEncoder().encode(message);
        const timestamp = Date.now() / 1000;
        
        // Calculate buffer size
        const bufferSize = 4 + 4 + 4 + agentIdBytes.length + 8 + 4 + messageBytes.length;
        const buffer = new ArrayBuffer(bufferSize);
        const view = new DataView(buffer);
        
        let offset = 0;
        
        // Magic
        view.setUint32(offset, MAGIC, false);
        offset += 4;
        
        // Frame type (CHAT)
        view.setUint32(offset, FRAME_CHAT, false);
        offset += 4;
        
        // Agent ID length
        view.setUint32(offset, agentIdBytes.length, false);
        offset += 4;
        
        // Agent ID
        for (let i = 0; i < agentIdBytes.length; i++) {
          view.setUint8(offset, agentIdBytes[i]);
          offset++;
        }
        
        // Timestamp (double)
        view.setFloat64(offset, timestamp, false);
        offset += 8;
        
        // Message length
        view.setUint32(offset, messageBytes.length, false);
        offset += 4;
        
        // Message
        for (let i = 0; i < messageBytes.length; i++) {
          view.setUint8(offset, messageBytes[i]);
          offset++;
        }
        
        ws.send(buffer);
      } catch (err) {
        console.error("Binary send error, falling back to JSON:", err);
        // Fallback to JSON
        ws.send(JSON.stringify({
          type: "chat",
          message: message
        }));
      }
    };
  };

  const sendMessage = async () => {
    if (!text.trim()) return;
    
    try {
      setMessages((m) => [...m, { sender: "user", text }]);
      
      // Try to send via binary protocol (websocket)
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && wsRef.current.sendBinaryChat) {
        console.log("[WS] Sending binary chat message");
        wsRef.current.sendBinaryChat(text);
      } else {
        // Fallback to REST API for chat
        console.log("[REST] Sending via API/chat");
        const form = new FormData();
        form.append("message", text);
        form.append("agent_id", AGENT_ID);
        
        if (allowedWebsites.filter(w => w.enabled).length > 0) {
          form.append("allowed_websites", JSON.stringify(
            allowedWebsites.filter(w => w.enabled).map(w => w.url)
          ));
        }
        
        await fetch(`${BACKEND_URL}/api/chat`, {
          method: 'POST',
          body: form
        });
      }
      
      setText("");
    } catch (err) {
      setError(`Failed to send: ${err.message}`);
    }
  };

  const onFileSend = async (file, type, sync = false) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("agent_id", AGENT_ID);
      formData.append("filetype", type);
      
      const url = `${BACKEND_URL}/api/upload${sync ? '?sync=true' : ''}`;
      const response = await fetch(url, {
        method: "POST",
        body: formData
      });
      
      if (!response.ok) throw new Error(`Upload failed: ${response.statusText}`);
      
      const result = await response.json();
      
      setMessages(m => [...m, { 
        sender: "system", 
        text: sync ? `✅ File received and processed: ${file.name}` : `✅ File received: ${file.name} (${(file.size / 1024).toFixed(1)}KB). AI will process it.` 
      }]);
      
      console.log("File upload success:", result);
    } catch (err) {
      setError(`File upload failed: ${err.message}`);
      console.error("Upload error:", err);
    }
  };

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  const dismissError = () => setError(null);

  return (
    <>
      {/* Show ControllerSafety component when in controller mode */}
      {mode === "controller" ? (
        <ControllerSafety onModeChange={() => setMode("chat")} />
      ) : (
        /* Chat mode layout */
        <div className={`flex h-screen transition-colors ${
            theme === "dark" ? "bg-slate-950 text-gray-100" : "bg-slate-50 text-slate-900"
          }`}>
          {error && (
            <div className="fixed top-6 left-1/2 transform -translate-x-1/2 z-50 alert alert-error shadow-lg max-w-md">
              <span>{error}</span>
              <button onClick={dismissError}>✕</button>
            </div>
          )}

          <div className={`flex flex-col flex-[2] border-r ${
            theme === "dark" ? "border-slate-800 bg-slate-900/40" : "border-amber-100 bg-amber-50/30"
          }`}>
        <div className={`navbar border-b ${
          theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-amber-100 bg-amber-50/50"
        }`}>
          <div className="flex-1 flex items-center gap-3">
            <h1 className="text-2xl font-semibold px-4">
              DW Agent - {AGENT_ID}
            </h1>
            <AgentStatus connected={connected} active={brainActive} />
          </div>
          <button onClick={toggleTheme} className="btn btn-sm btn-ghost">
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>

        <div className="flex-1 p-6 overflow-y-auto space-y-3">
          {messages.map((msg, i) => (
            <MessageBubble key={i} sender={msg.sender} text={msg.text} />
          ))}
        </div>

        <FileDropZone onFileSend={onFileSend} />

        <div className={`p-5 border-t ${
          theme === "dark" ? "border-slate-800" : "border-amber-100"
        }`}>
          <div className="flex gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type a message..."
              className="input input-bordered flex-1"
              onKeyPress={(e) => e.key === "Enter" && sendMessage()}
            />
            <button onClick={sendMessage} className="btn btn-primary">
              Send
            </button>
          </div>

          <div className="flex items-center mt-4 gap-3">
            <button onClick={() => setShowWebManager(!showWebManager)} className="btn btn-sm btn-outline gap-2">
              <Globe className="w-4 h-4" />
              Web Access
            </button>
            <button onClick={() => setMode(mode === "chat" ? "controller" : "chat")}
              className="badge badge-lg cursor-pointer hover:scale-110 transition-transform"
              title="Click to switch mode">
              🧠 {mode}
            </button>
          </div>
        </div>
      </div>

      <div className={`flex flex-col flex-1 ${
        theme === "dark" ? "bg-slate-900/40" : "bg-amber-50/30"
      }`}>
        <div className={`navbar border-b ${
          theme === "dark" ? "border-slate-800" : "border-amber-100 bg-amber-50/50"
        }`}>
          <h2 className="text-xl font-semibold px-4 flex items-center gap-2">
            <Box className="w-5 h-5" />
            Agent Thoughts
          </h2>
        </div>
        
        <div className="p-4 border-b border-slate-800 flex-1 flex flex-col min-h-0 max-h-[55%]">
          <Simple3DRenderer data={visualizationData} />
        </div>
        
        {showWebManager && (
          <div className="p-4 border-b border-slate-800">
            <WebAccessManager onWebsitesChange={setAllowedWebsites} />
          </div>
        )}
        
        <div className="flex-1 p-6 overflow-y-auto space-y-3">
          {thoughts.map((t, i) => (
            <div key={i} className={`alert ${
              theme === "dark" ? "bg-slate-800" : "bg-amber-100/60 border border-amber-200"
            }`}>
              <span>{t}</span>
            </div>
          ))}
        </div>
      </div>
        </div>
      )}
    </>
  );
}

export default App;

/**
 *  Depth-based rendering - Objects are sorted and rendered back-to-front with depth-based opacity for a true 3D effect
 Multiple object types:

block/cube - Blue squares with borders
entity/agent - Red circles (for the agent itself or other entities)
goal/target - Yellow triangles
Default - Green circles for unknown objects

 Better visual depth - Objects further away appear more transparent, closer ones are more opaque
 Enhanced labels - Object labels now have dark backgrounds for better readability
 */