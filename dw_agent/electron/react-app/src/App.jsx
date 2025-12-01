// electron/react-app/src/App.jsx - FIXED WITH WEBSOCKET REGISTRATION
import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import "./App.css";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:11400";
const WS_URL = BACKEND_URL.replace("http", "ws") + "/ws";
const AGENT_ID = import.meta.env.VITE_AGENT_ID || "demo";

function App() {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState("chat");
  const [theme, setTheme] = useState("dark"); // light | dark
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // --- Setup WebSocket with Registration ---
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
      console.log("[WS] Connected to backend");
      
      // SEND REGISTRATION - CRITICAL FIX
      ws.send(JSON.stringify({
        type: "register",
        agent: AGENT_ID
      }));
    };

    ws.onclose = () => {
      setConnected(false);
      setError("Disconnected from server");
      console.log("[WS] Disconnected, attempting reconnect in 5s...");
      
      // Auto-reconnect
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket();
      }, 5000);
    };

    ws.onerror = (err) => {
      setError("WebSocket error");
      console.error("[WS] Error:", err);
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        console.log("[WS] Received:", data);
        
        // Handle different message types
        switch (data.type) {
          case "registered":
            setConnected(true);
            setError(null);
            console.log(`[WS] Registered as ${data.agent}`);
            break;
            
          case "chat":
            setMessages((m) => [...m, { 
              sender: data.from || "agent", 
              text: data.text 
            }]);
            break;
            
          case "status":
            setMessages((m) => [...m, { 
              sender: "status", 
              text: JSON.stringify(data.obs || {}) 
            }]);
            break;
            
          case "uploaded":
            setMessages((m) => [...m, { 
              sender: "system", 
              text: `📁 Uploaded ${data.filename}` 
            }]);
            break;
            
          case "agent_thought":
            if (Array.isArray(data.chain)) {
              setThoughts((t) => [...t, ...data.chain]);
            } else if (data.text) {
              setThoughts((t) => [...t, data.text]);
            }
            break;
            
          case "mode_changed":
            setMode(data.mode);
            setMessages((m) => [...m, {
              sender: "system",
              text: `🔄 Mode changed to: ${data.mode}`
            }]);
            break;
            
          case "ping":
            // Respond to ping
            ws.send(JSON.stringify({ type: "pong" }));
            break;
            
          default:
            console.log("[WS] Unknown message type:", data.type);
        }
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };
  };

  // --- Send chat ---
  const sendMessage = async () => {
    if (!text.trim()) return;
    
    try {
      const form = new FormData();
      form.append("message", text);
      form.append("agent_id", AGENT_ID);
      
      await axios.post(`${BACKEND_URL}/api/chat`, form);
      
      // Add to local UI immediately
      setMessages((m) => [...m, { sender: "user", text }]);
      setText("");
    } catch (err) {
      console.error("Chat error:", err);
      setError(`Failed to send message: ${err.message}`);
    }
  };

  // --- File Upload ---
  const handleFileUpload = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("agent_id", AGENT_ID);
      
      await axios.post(`${BACKEND_URL}/api/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      
      setMessages((m) => [...m, {
        sender: "system",
        text: `📤 Uploaded: ${f.name}`
      }]);
    } catch (err) {
      console.error("Upload error:", err);
      setError(`Upload failed: ${err.message}`);
    }
  };

  // --- Drag & Drop ---
  const onDrop = async (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (!f) return;
    
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("agent_id", AGENT_ID);
      
      await axios.post(`${BACKEND_URL}/api/upload`, fd);
      
      setMessages((m) => [...m, {
        sender: "system",
        text: `📥 Dropped: ${f.name}`
      }]);
    } catch (err) {
      console.error("Drop upload error:", err);
      setError(`Drop upload failed: ${err.message}`);
    }
  };

  const toggleMode = async () => {
    const newMode = mode === "chat" ? "controller" : "chat";
    
    // Send command via WebSocket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ 
        type: "command", 
        cmd: "mode" 
      }));
    }
    
    // If switching TO controller mode, show safety warning
    if (newMode === "controller") {
      const confirmed = window.confirm(
        "⚠️ Controller Mode grants system access (camera, mic, files).\n\n" +
        "Only proceed if you trust this AI agent.\n\n" +
        "Continue?"
      );
      
      if (!confirmed) {
        return;
      }
      
      try {
        const response = await axios.post(`${BACKEND_URL}/api/controller/activate`, {
          agent_id: AGENT_ID,
          permissions: ["camera", "microphone", "file_system"],
          acknowledged: true
        });
        
        if (response.data.success) {
          setMode("controller");
          setMessages((m) => [...m, {
            sender: "system",
            text: "🎮 Controller mode activated"
          }]);
        }
      } catch (err) {
        console.error("Controller activation error:", err);
        setError(`Failed to activate controller: ${err.message}`);
      }
    } else {
      // Switching back to chat mode
      try {
        await axios.post(`${BACKEND_URL}/api/controller/deactivate`, {
          agent_id: AGENT_ID
        });
        
        setMode("chat");
        setMessages((m) => [...m, {
          sender: "system",
          text: "💬 Chat mode activated"
        }]);
      } catch (err) {
        console.error("Controller deactivation error:", err);
      }
    }
  };

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  
  const dismissError = () => setError(null);

  return (
    <div
      className={`flex h-screen transition-colors duration-500 ${
        theme === "dark" ? "bg-slate-950 text-gray-100" : "bg-cream-50 text-slate-900"
      } font-inter`}
      onDrop={onDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      {/* Error Toast */}
      {error && (
        <div className="fixed top-6 left-1/2 transform -translate-x-1/2 max-w-md z-50 animate-fade-in flex justify-between items-center alert alert-error shadow-lg">
          <div className="flex items-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="stroke-current shrink-0 h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span className="font-medium">{error}</span>
          </div>
          <button
            onClick={dismissError}
            className="ml-4 hover:text-white hover:scale-110 transition-transform duration-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* Chat Column */}
      <div
        className={`flex flex-col flex-[2] border-r transition-colors duration-500 backdrop-blur-lg ${
          theme === "dark" ? "border-slate-800 bg-slate-900/40" : "border-slate-200 bg-cream-100/50"
        }`}
      >
        {/* Navbar */}
        <div
          className={`navbar border-b transition-colors duration-500 backdrop-blur-xl shadow-md ${
            theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-slate-200 bg-cream-100/70"
          }`}
        >
          <div className="flex-1 flex items-center gap-2">
            <h1 className="text-2xl font-semibold px-4 bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-300">
              DW Agent - {AGENT_ID}
            </h1>
            <div
              className={`h-3 w-3 rounded-full ${
                connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
              } shadow-sm transition-all duration-300`}
            ></div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleMode}
              className={`btn btn-sm border-slate-700 hover:scale-105 transition-all duration-300 ${
                mode === "chat" ? "btn-outline btn-primary" : "btn-outline btn-accent"
              }`}
            >
              {mode === "chat" ? "🎮 Switch to Controller" : "💬 Switch to Chat"} Mode
            </button>
            <button
              onClick={toggleTheme}
              className="btn btn-sm btn-ghost hover:bg-gray-300 hover:scale-105 transition-transform duration-300"
            >
              {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
            </button>
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 p-6 overflow-y-auto space-y-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`chat transition-transform duration-300 hover:scale-[1.02] ${
                msg.sender === "user" ? "chat-end" : "chat-start"
              }`}
            >
              <div
                className={`chat-bubble shadow-md transition-all duration-200 ${
                  msg.sender === "user"
                    ? "bg-indigo-600/70"
                    : msg.sender === "agent"
                    ? "bg-cyan-700/60"
                    : "bg-slate-700/60"
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}
        </div>

        {/* Input Area */}
        <div
          className={`p-5 border-t transition-colors duration-500 backdrop-blur-lg ${
            theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-slate-200 bg-cream-100/60"
          }`}
        >
          <div className="join w-full shadow-md">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type a message..."
              className={`input input-bordered join-item w-full transition-colors duration-300 ${
                theme === "dark"
                  ? "bg-slate-800/60 border-slate-700 text-gray-200 placeholder-gray-500 focus:border-indigo-400"
                  : "bg-white/60 border-slate-300 text-slate-900 placeholder-slate-500 focus:border-indigo-400"
              }`}
              onKeyPress={(e) => e.key === "Enter" && sendMessage()}
            />
            <button
              onClick={sendMessage}
              className="btn join-item btn-primary bg-indigo-600 border-0 hover:bg-indigo-500 hover:scale-105 transition-all"
            >
              Send
            </button>
          </div>

          <div className="flex items-center mt-4 gap-3">
            <input
              type="file"
              onChange={handleFileUpload}
              className={`file-input file-input-bordered file-input-sm w-full max-w-xs transition-colors duration-300 ${
                theme === "dark"
                  ? "bg-slate-800/60 border-slate-700 text-gray-200 hover:border-indigo-400"
                  : "bg-white/60 border-slate-300 text-slate-900 hover:border-indigo-400"
              }`}
            />
            <div
              className={`badge badge-lg shadow-sm font-medium px-3 py-2 transition-colors duration-300 ${
                mode === "chat" ? "badge-primary" : "badge-accent"
              }`}
            >
              🧠 Brain: {mode}
            </div>
          </div>
        </div>
      </div>

      {/* Thoughts Column */}
      <div
        className={`flex flex-col flex-1 transition-colors duration-500 backdrop-blur-lg ${
          theme === "dark" ? "bg-slate-900/40" : "bg-cream-50/40"
        }`}
      >
        <div
          className={`navbar border-b transition-colors duration-500 backdrop-blur-xl shadow-md ${
            theme === "dark" ? "border-slate-800 bg-slate-900/60" : "border-slate-200 bg-cream-100/70"
          }`}
        >
          <h2 className="text-xl font-semibold px-4 bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-indigo-400">
            Agent Thoughts
          </h2>
        </div>
        <div className="flex-1 p-6 overflow-y-auto space-y-3">
          {thoughts.map((t, i) => (
            <div
              key={i}
              className={`alert shadow-md transition-transform duration-200 hover:scale-[1.02] ${
                theme === "dark" ? "bg-slate-800/60 border border-slate-700" : "bg-white/60 border border-slate-300"
              }`}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="stroke-info shrink-0 w-5 h-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                ></path>
              </svg>
              <span>{t}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default App;