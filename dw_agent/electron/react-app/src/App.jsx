import React, { useState, useEffect, useRef } from "react";
import { Globe, Plus, Trash2, Check, X, Box, Upload } from "lucide-react";
import MessageBubble from "./components/MessageBubble.jsx";
import AgentStatus from "./components/AgentStatus.jsx";
import FileDropZone from "./components/FileDropZone.jsx";

const BACKEND_URL = "http://127.0.0.1:11400";
const WS_URL = "ws://127.0.0.1:11400/ws";
const AGENT_ID = "demo";

// Simple 3D Visualization Component using Canvas
function Simple3DRenderer({ data }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [showMesh, setShowMesh] = useState(true);
  const [rotation, setRotation] = useState({ x: 0, y: 0, z: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [containerSize, setContainerSize] = useState({ width: 400, height: 300 });
  const [isResizing, setIsResizing] = useState(false);
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const [zoom, setZoom] = useState(1);
  
  // Handle container resize
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
  
  // Handle manual resize via drag
  const handleResizeStart = (e) => {
    e.preventDefault();
    setIsResizing(true);
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: containerSize.width,
      height: containerSize.height
    });
  };
  
  useEffect(() => {
    if (!isResizing) return;
    
    const handleResizeMove = (e) => {
      const deltaX = e.clientX - resizeStart.x;
      const deltaY = e.clientY - resizeStart.y;
      
      setContainerSize({
        width: Math.max(200, resizeStart.width + deltaX),
        height: Math.max(200, resizeStart.height + deltaY)
      });
    };
    
    const handleResizeEnd = () => {
      setIsResizing(false);
    };
    
    document.addEventListener('mousemove', handleResizeMove);
    document.addEventListener('mouseup', handleResizeEnd);
    
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
    };
  }, [isResizing, resizeStart]);
  
  useEffect(() => {
    if (!canvasRef.current || !data) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    // Clear canvas with solid dark background
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Helper function to apply 3D rotation
    const rotatePoint3D = (x, y, z, rx, ry, rz) => {
      // Normalize rotation to prevent inversion
      rx = ((rx % 360) + 360) % 360;
      ry = ((ry % 360) + 360) % 360;
      rz = ((rz % 360) + 360) % 360;
      
      // Convert degrees to radians
      rx = (rx * Math.PI) / 180;
      ry = (ry * Math.PI) / 180;
      rz = (rz * Math.PI) / 180;
      
      // Rotation around X axis
      let y1 = y * Math.cos(rx) - z * Math.sin(rx);
      let z1 = y * Math.sin(rx) + z * Math.cos(rx);
      
      // Rotation around Y axis
      let x2 = x * Math.cos(ry) + z1 * Math.sin(ry);
      let z2 = -x * Math.sin(ry) + z1 * Math.cos(ry);
      
      // Rotation around Z axis
      let x3 = x2 * Math.cos(rz) - y1 * Math.sin(rz);
      let y3 = x2 * Math.sin(rz) + y1 * Math.cos(rz);
      
      return { x: x3, y: y3, z: z2 };
    };
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    
    // Draw visualization based on type
    if (data.type === 'matrix') {
      const size = Math.min(canvas.width, canvas.height) * 0.3;
      
      // Define cube corners
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
      
      // Apply rotation to all corners
      const rotatedCorners = corners.map(c => rotatePoint3D(c.x, c.y, c.z, rotation.x, rotation.y, rotation.z));
      
      // Draw cube edges
      const edges = [
        [0, 1], [1, 2], [2, 3], [3, 0], // front face
        [4, 5], [5, 6], [6, 7], [7, 4], // back face
        [0, 4], [1, 5], [2, 6], [3, 7]  // connecting edges
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
      
      // Draw corner spheres
      ctx.fillStyle = 'rgba(30, 64, 175, 0.8)';
      rotatedCorners.forEach(p => {
        ctx.beginPath();
        ctx.arc(centerX + p.x * zoom, centerY + p.y * zoom, 4, 0, Math.PI * 2);
        ctx.fill();
      });
      
      // Draw 3D matrix mesh inside the cube if mesh is enabled
      if (showMesh) {
        const gridPoints = [];
        const gridDivisions = 4;
        const step = (size * 2) / gridDivisions;
        
        // Draw grid lines along X axis
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 1;
        
        for (let y = -size; y <= size; y += step) {
          for (let z = -size; z <= size; z += step) {
            for (let x = -size; x < size; x += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y, rotation.z);
              const p2 = rotatePoint3D(x + step, y, z, rotation.x, rotation.y, rotation.z);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }
        
        // Draw grid lines along Y axis
        for (let x = -size; x <= size; x += step) {
          for (let z = -size; z <= size; z += step) {
            for (let y = -size; y < size; y += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y, rotation.z);
              const p2 = rotatePoint3D(x, y + step, z, rotation.x, rotation.y, rotation.z);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }
        
        // Draw grid lines along Z axis
        for (let x = -size; x <= size; x += step) {
          for (let y = -size; y <= size; y += step) {
            for (let z = -size; z < size; z += step) {
              const p1 = rotatePoint3D(x, y, z, rotation.x, rotation.y, rotation.z);
              const p2 = rotatePoint3D(x, y, z + step, rotation.x, rotation.y, rotation.z);
              ctx.beginPath();
              ctx.moveTo(centerX + p1.x * zoom, centerY + p1.y * zoom);
              ctx.lineTo(centerX + p2.x * zoom, centerY + p2.y * zoom);
              ctx.stroke();
            }
          }
        }
      }
      
    } else if (data.type === 'thought_flow') {
      const radius = Math.min(canvas.width, canvas.height) * 0.25;
      const points = [];
      
      // Create 3D points in a sphere
      for (let i = 0; i < 8; i++) {
        const angle1 = (i / 8) * Math.PI * 2;
        const angle2 = Math.PI / 4;
        
        points.push({
          x: radius * Math.cos(angle1) * Math.sin(angle2),
          y: radius * Math.sin(angle1) * Math.sin(angle2),
          z: radius * Math.cos(angle2)
        });
      }
      
      // Apply rotation
      const rotatedPoints = points.map(p => rotatePoint3D(p.x, p.y, p.z, rotation.x, rotation.y, rotation.z));
      
      // Draw connections
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
      
      // Draw spheres
      ctx.fillStyle = '#22c55e';
      rotatedPoints.forEach(point => {
        ctx.beginPath();
        ctx.arc(centerX + point.x, centerY + point.y, 5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px monospace';
    ctx.fillText(data.label || 'AI Mental State', 10, 20);
    
  }, [data, showMesh, rotation, containerSize, zoom]);
  
  const handleMouseDown = (e) => {
    // Don't start dragging if clicking on resize handle
    if (e.target === containerRef.current?.querySelector('[data-resize-handle]')) {
      return;
    }
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };
  
  const handleMouseMove = (e) => {
    if (!isDragging) return;
    
    const deltaX = e.clientX - dragStart.x;
    const deltaY = e.clientY - dragStart.y;
    
    // Direct mouse following - invert Y so up/down works naturally
    setRotation(prev => ({
      x: prev.x - deltaY,
      y: prev.y + deltaX,
      z: prev.z
    }));
    
    setDragStart({ x: e.clientX, y: e.clientY });
  };
  
  const handleMouseUp = () => {
    setIsDragging(false);
  };
  
  const resetRotation = () => {
    setRotation({ x: 0, y: 0, z: 0 });
  };
  
  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prev => Math.max(0.5, Math.min(3, prev * delta)));
  };
  
  useEffect(() => {
    // Add global mouse move and up listeners for dragging outside the component
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
    <div 
      className="flex flex-col gap-3 h-full w-full overflow-auto"
      style={{ 
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        minWidth: 0
      }}
    >
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
          X: {rotation.x.toFixed(0)}° Y: {rotation.y.toFixed(0)}° Z: {rotation.z.toFixed(0)}° | Zoom: {zoom.toFixed(2)}x
        </div>
        <button
          onClick={resetRotation}
          className="btn btn-xs btn-ghost"
          title="Reset rotation"
        >
          ↺ Reset
        </button>
      </div>
      <div 
        ref={containerRef}
        className="flex-1 bg-slate-900 rounded-lg overflow-hidden relative border border-slate-700"
        style={{
          minHeight: '300px',
          minWidth: '300px',
          width: '100%',
          height: '100%'
        }}
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
      >
        <canvas 
          ref={canvasRef}
          width={containerSize.width}
          height={containerSize.height}
          className="w-full h-full cursor-grab active:cursor-grabbing"
          title="Drag to rotate • Shift+Drag for Z-axis"
        />
        <div
          data-resize-handle="true"
          onMouseDown={handleResizeStart}
          className="absolute bottom-0 right-0 w-4 h-4 bg-blue-500 cursor-se-resize hover:bg-blue-400 rounded-tl"
          title="Drag to resize"
        />
      </div>
      <div className="text-xs text-gray-500 text-center flex-shrink-0">
        Drag to rotate • Scroll to zoom • Resize handle at bottom-right
      </div>
    </div>
  );
}

// Web Access Manager Component
function WebAccessManager({ onWebsitesChange }) {
  const [websites, setWebsites] = useState([]);
  const [newUrl, setNewUrl] = useState("");
  const [isAdding, setIsAdding] = useState(false);
  
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
        <button
          onClick={() => setIsAdding(!isAdding)}
          className="btn btn-xs btn-primary"
        >
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
              <button
                onClick={() => removeWebsite(website.id)}
                className="btn btn-xs btn-ghost text-error"
              >
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

    ws.onopen = () => {
      console.log("[WS] Connected");
      ws.send(JSON.stringify({
        type: "register",
        agent: AGENT_ID
      }));
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = () => setError("WebSocket error");

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        
        switch (data.type) {
          case "registered":
            setConnected(true);
            setError(null);
            break;
            
          case "chat":
            setMessages((m) => [...m, { 
              sender: data.from || "agent", 
              text: data.text 
            }]);
            break;
            
          case "agent_thought":
            if (Array.isArray(data.chain)) {
              setThoughts((t) => [...t, ...data.chain]);
            } else if (data.text) {
              setThoughts((t) => [...t, data.text]);
            }
            
            // Mark brain as active when thoughts are being processed
            setBrainActive(true);
            setTimeout(() => setBrainActive(false), 2000);
            
            if (data.visualization) {
              setVisualizationData(data.visualization);
            } else {
              setVisualizationData({ 
                type: 'thought_flow', 
                label: 'Thought Process' 
              });
            }
            break;
            
          case "visualization_update":
            setVisualizationData(data.data);
            break;
        }
      } catch (e) {
        console.error("Parse error:", e);
      }
    };
  };

  const sendMessage = async () => {
    if (!text.trim()) return;
    
    try {
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
      
      setMessages((m) => [...m, { sender: "user", text }]);
      setText("");
    } catch (err) {
      setError(`Failed to send: ${err.message}`);
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    const type = file.type.split("/")[0];
    // Handle file upload to backend
    console.log("File uploaded:", file.name, type);
    // TODO: Send file to backend
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
      
      // Show success message
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
    <div
      className={`flex h-screen transition-colors ${
        theme === "dark" ? "bg-slate-950 text-gray-100" : "bg-slate-50 text-slate-900"
      }`}
    >
      {error && (
        <div className="fixed top-6 left-1/2 transform -translate-x-1/2 z-50 alert alert-error shadow-lg max-w-md">
          <span>{error}</span>
          <button onClick={dismissError}>✕</button>
        </div>
      )}

      {/* Chat Column */}
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

          <button
            onClick={toggleTheme}
            className="btn btn-sm btn-ghost"
          >
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
            <button
              onClick={sendMessage}
              className="btn btn-primary"
            >
              Send
            </button>
          </div>

          <div className="flex items-center mt-4 gap-3">
            <label className="btn btn-sm btn-outline gap-2 cursor-pointer">
              <Upload className="w-4 h-4" />
              Upload File
              <input
                type="file"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
            <button
              onClick={() => setShowWebManager(!showWebManager)}
              className="btn btn-sm btn-outline gap-2"
            >
              <Globe className="w-4 h-4" />
              Web Access
            </button>
            <button
              onClick={() => setMode(mode === "chat" ? "controller" : "chat")}
              className="badge badge-lg cursor-pointer hover:scale-110 transition-transform"
              title="Click to switch mode"
            >
              🧠 {mode}
            </button>
          </div>
        </div>
      </div>

      {/* Thoughts Column */}
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
        
        {/* 3D Visualization */}
        <div className="p-4 border-b border-slate-800 flex-1 flex flex-col min-h-0 max-h-[55%]">
          <Simple3DRenderer data={visualizationData} />
        </div>
        
        {/* Web Manager */}
        {showWebManager && (
          <div className="p-4 border-b border-slate-800">
            <WebAccessManager onWebsitesChange={setAllowedWebsites} />
          </div>
        )}
        
        {/* Thoughts */}
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
  );
}

export default App;