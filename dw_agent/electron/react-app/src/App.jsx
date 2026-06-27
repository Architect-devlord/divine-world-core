import React, { useState, useEffect, useRef, useLayoutEffect } from "react";
import {
  Globe, Plus, Trash2, Check, X, Box, Upload, Brain, Send,
  Monitor, Terminal, LayoutGrid, Activity, ChevronDown, ChevronUp,
  HardDrive, Cpu, Network,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import MessageBubble      from "./components/MessageBubble.jsx";
import AgentStatus        from "./components/AgentStatus.jsx";
import FileDropZone       from "./components/FileDropZone.jsx";
import ControllerSafety   from "./ControllerSafety.jsx";
import WorldModelVisualizer from "./components/WorldModelVisualizer.jsx";
import MentalMatrixModal  from "./components/MentalMatrixModal.jsx";

// ─── Backend constants ────────────────────────────────────────────────────────
// This bundle is identical for every agent (packager.py copies the same
// build output into every agent's package), so nothing here can be a literal
// per-agent constant. The packaged launcher always serves this frontend from
// backend_port + 1 (see packager.py's _create_launcher), so the page's own
// URL already tells us which backend to talk to.
const BACKEND_PORT = window.location.port ? Number(window.location.port) - 1 : 11400;
const BACKEND_URL  = `http://${window.location.hostname}:${BACKEND_PORT}`;
const WS_URL       = `ws://${window.location.hostname}:${BACKEND_PORT}/ws`;
// AGENT_ID can't be derived from the URL the same way — it's fetched from
// /status on mount (see the useEffect in App()) and threaded through as
// state/props from there. "demo" below is only the value used before that
// first fetch resolves.

// ─── Visitor identity (Chat & Web GRPO plan — extraversion reward fix) ───────
// A stable per-installation id, persisted in localStorage, sent with every
// chat message as speaker_id. This is what lets an agent recognize "the
// same person keeps coming back to talk" and build genuine repeat-visitor
// familiarity (RewardSystem's new familiarity_r term, scaled by the agent's
// own extraversion trait) — previously there was no visitor identity at all,
// so every chat looked identical to the backend and extraversion had
// nothing to read as a reward signal. Falls back to a per-session id if
// localStorage is unavailable (e.g. private browsing); familiarity just
// won't persist across reloads in that case, nothing else breaks.
function getOrCreateVisitorId() {
  try {
    let id = localStorage.getItem("dw_visitor_id");
    if (!id) {
      id = (typeof crypto !== "undefined" && crypto.randomUUID)
        ? crypto.randomUUID()
        : `visitor-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem("dw_visitor_id", id);
    }
    return id;
  } catch {
    return `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}
const VISITOR_ID = getOrCreateVisitorId();

// ─── Simple 3-D Renderer (inline — no separate file needed) ──────────────────
// ─── Web Access Manager ────────────────────────────────────────────────────────
function WebAccessManager({ onWebsitesChange, agentId }) {
  const [websites,  setWebsites]  = useState([]);
  const [newUrl,    setNewUrl]    = useState("");
  const [isAdding,  setIsAdding]  = useState(false);

  // Keep backend in sync whenever the allow-list changes
  useEffect(() => {
    if (websites.length === 0) return;
    fetch(`${BACKEND_URL}/api/agents/${agentId}/web/allow`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ websites }),
    })
      .then(r => r.json())
      .then(d => console.log("✅ Websites synced:", d))
      .catch(e => console.error("Failed to sync websites:", e));
  }, [websites, agentId]);

  const addWebsite = () => {
    if (!newUrl.trim()) return;
    try {
      let raw = newUrl.trim();
      if (!raw.startsWith("http")) raw = "https://" + raw;
      const url       = new URL(raw);
      const domainOnly = url.pathname === "/" && !url.search && !url.hash;
      const entry = {
        id:       Date.now(),
        url:      url.href,
        display:  domainOnly ? url.hostname : url.href,
        type:     domainOnly ? "domain" : "url",
        enabled:  true,
        addedAt:  new Date().toISOString(),
      };
      const next = [...websites, entry];
      setWebsites(next);
      onWebsitesChange(next);
      setNewUrl("");
      setIsAdding(false);
    } catch {
      alert("Invalid URL — enter a valid website address.");
    }
  };

  const toggleWebsite = id => {
    const next = websites.map(w => w.id === id ? { ...w, enabled: !w.enabled } : w);
    setWebsites(next);
    onWebsitesChange(next);
  };

  const removeWebsite = id => {
    const next = websites.filter(w => w.id !== id);
    setWebsites(next);
    onWebsitesChange(next);
  };

  return (
    <div className="space-y-3 glass-card p-4 rounded-xl">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold uppercase tracking-widest flex items-center gap-2 text-indigo-400">
          <Globe className="w-3.5 h-3.5" /> Network Permission Layer
        </h3>
        <button onClick={() => setIsAdding(!isAdding)} className="btn btn-xs btn-primary h-7 rounded-lg">
          <Plus className="w-3 h-3" /> Authorize
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
          <div className="flex gap-2 p-1 bg-slate-950/80 rounded-xl border border-white/10">
            <input
              autoFocus
              type="text"
              value={newUrl}
              onChange={e => setNewUrl(e.target.value)}
              placeholder="e.g. google.com"
              className="input input-sm flex-1 bg-transparent border-none focus:ring-0 text-xs text-white placeholder:text-slate-600 px-3"
              onKeyDown={e => e.key === "Enter" && addWebsite()}
            />
            <button
              onClick={addWebsite}
              className="btn btn-sm bg-indigo-500 hover:bg-indigo-400 border-none h-8 w-8 p-0 min-h-0 rounded-lg shadow-lg shadow-indigo-500/20"
            >
              <Check className="w-4 h-4 text-white" />
            </button>
          </div>
          <p className="text-[9px] text-slate-500 leading-tight">
            The AI will only browse sites within these authorised domains.
          </p>
        </motion.div>
      )}

      <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
        {websites.length === 0 ? (
          <div className="text-center py-6 text-slate-600">
            <p className="text-[10px] uppercase font-bold tracking-tighter opacity-50">Isolated Environment</p>
          </div>
        ) : (
          websites.map(w => (
            <div
              key={w.id}
              className={`flex items-center justify-between p-2 rounded-lg border transition-all ${
                w.enabled ? "bg-slate-800/30 border-slate-700/50" : "bg-slate-900/10 border-transparent opacity-40"
              }`}
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <input
                  type="checkbox"
                  checked={w.enabled}
                  onChange={() => toggleWebsite(w.id)}
                  className="checkbox checkbox-xs checkbox-primary"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-bold truncate text-slate-200">{w.display}</p>
                  <p className="text-[8px] uppercase tracking-widest text-slate-500 font-black">{w.type}</p>
                </div>
              </div>
              <button onClick={() => removeWebsite(w.id)} className="btn btn-xs btn-ghost h-6 w-6 p-0 min-h-0 text-slate-600 hover:text-rose-500">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ─── Activity Bar ─────────────────────────────────────────────────────────────
function ActivityBar({ activities, theme }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center justify-between w-full px-4 py-2 transition-colors border rounded-xl group ${
          theme === "dark"
            ? "bg-slate-900/40 hover:bg-slate-800/60 border-white/5"
            : "bg-slate-200/50 hover:bg-slate-300/50 border-slate-300/50"
        }`}
      >
        <div className="flex items-center gap-3">
          <Activity className={`w-4 h-4 ${activities.length > 0 ? "text-indigo-400 animate-pulse" : "text-slate-500"}`} />
          <span className={`text-[10px] font-black uppercase tracking-[0.2em] ${theme === "dark" ? "text-slate-300" : "text-slate-700"}`}>
            System Activity Log
          </span>
          {activities.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-md bg-indigo-500/20 border border-indigo-500/30 text-[9px] font-bold text-indigo-400">
              {activities.length}
            </span>
          )}
        </div>
        {isOpen
          ? <ChevronDown className="w-3 h-3 text-slate-500" />
          : <ChevronUp   className="w-3 h-3 text-slate-500" />}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden mt-2 space-y-2"
          >
            {activities.length === 0 ? (
              <div className="p-4 text-center glass-card rounded-xl">
                <p className="text-[9px] text-slate-600 uppercase font-bold tracking-widest">No Recent Telemetry</p>
              </div>
            ) : (
              <div className="max-h-32 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                {activities.map((a, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 p-2 border rounded-lg ${
                      theme === "dark" ? "bg-slate-900/40 border-white/5" : "bg-white border-slate-200"
                    }`}
                  >
                    {a.type === "web"        ? <Globe     className="w-3 h-3 text-cyan-400"   /> :
                     a.type === "file"       ? <HardDrive className="w-3 h-3 text-indigo-400" /> :
                     a.type === "controller" ? <Cpu       className="w-3 h-3 text-rose-400"   /> :
                                              <Network   className="w-3 h-3 text-slate-400"  />}
                    <div className="flex-1 min-w-0">
                      <p className={`text-[9px] font-bold truncate uppercase ${theme === "dark" ? "text-slate-300" : "text-slate-700"}`}>{a.title}</p>
                      <p className="text-[8px] text-slate-500 font-mono truncate">{a.time}</p>
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

// ─── Main App ─────────────────────────────────────────────────────────────────
function App() {
  const [connected,       setConnected]       = useState(false);
  const [error,           setError]           = useState(null);
  const [messages,        setMessages]        = useState([]);
  const [thoughts,        setThoughts]        = useState([]);
  const [activities,      setActivities]      = useState([]);
  const [text,            setText]            = useState("");
  const [mode,            setMode]            = useState("chat");
  const [theme,           setTheme]           = useState("dark");
  const [visualizationData, setVisualizationData] = useState({ type: "matrix", label: "Mental Matrix" });
  const [allowedWebsites, setAllowedWebsites] = useState([]);
  const [showWebManager,  setShowWebManager]  = useState(false);
  const [brainActive,     setBrainActive]     = useState(false);
  // WorldModelVisualizer is shown when we receive a world_model_update
  const [worldModelData,  setWorldModelData]  = useState(null);
  const [showMentalMatrix, setShowMentalMatrix] = useState(false);
  // Resolved from /status on mount — see the constants block above for why
  // this can't be a module-level literal. "demo" is just the pre-fetch value.
  const [agentId, setAgentId] = useState("demo");

  useEffect(() => {
    fetch(`${BACKEND_URL}/status`)
      .then(r => r.json())
      .then(data => { if (data && data.agent_id) setAgentId(data.agent_id); })
      .catch(() => { /* keep the "demo" fallback if /status isn't up yet */ });
  }, []);

  useEffect(() => {
    document.body.className = theme === "light" ? "light-theme" : "";
  }, [theme]);

  const wsRef               = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const messagesEndRef      = useRef(null);
  const thoughtsEndRef      = useRef(null);

  const scrollToBottom = ref => {
    if (ref.current) ref.current.scrollIntoView({ behavior: "smooth", block: "end" });
  };

  useLayoutEffect(() => { scrollToBottom(messagesEndRef); }, [messages]);
  useLayoutEffect(() => { scrollToBottom(thoughtsEndRef);  }, [thoughts]);

  // ── WebSocket ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen  = () => { setConnected(true);  setError(null); };
      ws.onclose = () => {
        setConnected(false);
        reconnectTimeoutRef.current = setTimeout(connect, 5000);
      };
      ws.onerror = () => setError("System interface offline");

      ws.onmessage = ev => {
        try {
          const data = JSON.parse(ev.data);
          const now  = new Date().toLocaleTimeString();

          switch (data.type) {
            // ── Chat messages from the agent ──────────────────────────────
            case "chat":
              setMessages(m => [...m, { sender: data.from || "agent", text: data.text }]);
              break;

            // ── Internal thought stream ───────────────────────────────────
            case "agent_thought":
              if (data.internal_thought) setThoughts(t => [...t, data.internal_thought]);
              setBrainActive(true);
              setTimeout(() => setBrainActive(false), 2000);
              break;

            // ── Autonomous speech (cognitive_loop._broadcast_speech) ──────
            // NOTE: _broadcast_speech sends type:"chat" with from:"agent".
            // This case catches explicit agent_speech events if ever emitted.
            case "agent_speech":
              setMessages(m => [...m, { sender: data.agent_id || "agent", text: data.text }]);
              break;

            // ── 3-D mental workspace update ───────────────────────────────
            // cognitive_loop._broadcast_mental_workspace sends this
            case "visualization_update":
              setVisualizationData(data.data);
              break;

            // ── World-model network graph update ─────────────────────────
            // agent.py broadcast_world_model() sends this
            case "world_model_update":
              setWorldModelData(data.data);
              break;

            // ── Activity feed ─────────────────────────────────────────────
            // agent.py broadcast_activity() sends this
            case "activity_update":
              setActivities(prev => [{
                type:  data.activity_type || "default",
                title: data.title || "System Event",
                time:  now,
              }, ...prev].slice(0, 20));
              break;

            default:
              break;
          }
        } catch (e) {
          console.error("[WS] Parse error:", e);
        }
      };
    };

    connect();
    return () => {
      wsRef.current?.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  // ── Send chat message ─────────────────────────────────────────────────────
  const sendMessage = async (customText = null) => {
    const msg = customText !== null ? customText : text;
    if (!msg.trim()) return;

    try {
      setMessages(m => [...m, { sender: "user", text: msg }]);
      if (customText === null) setText("");

      const form = new FormData();
      form.append("message",    msg);
      form.append("agent_id",   agentId);
      form.append("speaker_id", VISITOR_ID);

      const activeUrls = allowedWebsites.filter(w => w.enabled).map(w => w.url);
      if (activeUrls.length > 0) form.append("allowed_websites", JSON.stringify(activeUrls));

      const res = await fetch(`${BACKEND_URL}/chat`, { method: "POST", body: form });
      if (res.ok) {
        const d = await res.json();
        // The agent also broadcasts via WS, but this HTTP response is the direct reply
        // Only add it if the WS hasn't already delivered it (WS is faster normally)
        if (d.response && !d.error) {
          // WS broadcast already handled — skip double-adding to avoid duplicates.
          // If WS is disconnected, fall back:
          if (!connected) setMessages(m => [...m, { sender: "agent", text: d.response }]);
        }
      }
    } catch (err) {
      setError(`Transmission failed: ${err.message}`);
    }
  };

  // ── File upload ───────────────────────────────────────────────────────────
  const onFileSend = async (file, type, sync = false) => {
    try {
      const formData = new FormData();
      formData.append("file",     file);
      formData.append("agent_id", agentId);
      formData.append("filetype", type);
      // sync must be a Form field — agent.py reads it as Form(False), not a query param
      if (sync) formData.append("sync", "true");
      const res = await fetch(`${BACKEND_URL}/api/upload`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);

      setMessages(m => [...m, { sender: "system", text: `DATAFRAME RECEIVED: ${file.name}` }]);
      setActivities(prev => [{
        type:  "file",
        title: `Uploaded: ${file.name}`,
        time:  new Date().toLocaleTimeString(),
      }, ...prev].slice(0, 20));
    } catch {
      setError("Data ingestion failed");
    }
  };

  const toggleTheme  = () => setTheme(t => t === "dark" ? "light" : "dark");
  const dismissError = () => setError(null);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen w-screen overflow-hidden font-sans selection:bg-indigo-500/30">
      {/* Error toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ x: 100, opacity: 0 }}
            animate={{ x: 0,   opacity: 1 }}
            exit={{   x: 100,  opacity: 0 }}
            className="fixed top-4 right-4 z-[9999] flex items-center gap-4 px-6 py-4 rounded-2xl bg-rose-600 shadow-2xl shadow-rose-900/40 text-white border border-rose-400/50 backdrop-blur-xl"
          >
            <div className="p-2 bg-white/20 rounded-xl">
              <Terminal className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-black uppercase tracking-widest opacity-70">System Alert</span>
              <span className="text-sm font-bold">{error}</span>
            </div>
            <button onClick={dismissError} className="ml-4 p-2 hover:bg-white/10 rounded-full transition-colors">
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
          {/* ── Left: Main chat interface ────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col flex-[2] rounded-3xl overflow-hidden glass-card relative"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-transparent pointer-events-none" />

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 relative z-10">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-indigo-500/10 rounded-xl border border-indigo-500/20">
                  <Monitor className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <h1 className={`text-sm font-black uppercase tracking-[0.2em] ${theme === "dark" ? "text-white" : "text-slate-900"}`}>
                    DIVINE WORLD <span className="text-indigo-500">v2.1</span>
                  </h1>
                  <p className="text-[10px] text-slate-500 font-mono tracking-tighter">
                    CORE_INTERFACE_ADDR: {agentId}.local
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <AgentStatus connected={connected} active={brainActive} />
                <button onClick={toggleTheme} className="btn btn-circle btn-ghost btn-sm hover:bg-white/5">
                  {theme === "dark" ? "☀️" : "🌙"}
                </button>
              </div>
            </div>

            {/* Messages */}
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

            {/* Input */}
            <div className={`p-4 backdrop-blur-xl border-t border-white/5 relative z-10 ${theme === "dark" ? "bg-slate-900/50" : "bg-slate-100/50"}`}>
              <FileDropZone onFileSend={onFileSend} />

              <div className="mt-4 flex flex-col gap-3">
                <div className="relative group">
                  <input
                    value={text}
                    onChange={e => setText(e.target.value)}
                    placeholder="Input command or query..."
                    className={`w-full border rounded-2xl py-4 pl-6 pr-14 text-sm focus:outline-none focus:border-indigo-500/50 focus:ring-4 focus:ring-indigo-500/10 transition-all placeholder:text-slate-500 font-medium ${
                      theme === "dark"
                        ? "bg-slate-950/50 border-slate-800 text-slate-100"
                        : "bg-white border-slate-200 text-slate-900"
                    }`}
                    onKeyDown={e => e.key === "Enter" && sendMessage()}
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
                    <button
                      onClick={() => setShowWebManager(!showWebManager)}
                      className={`btn btn-xs h-7 rounded-lg border-none flex items-center gap-2 transition-all ${
                        showWebManager
                          ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                          : "bg-slate-800 hover:bg-slate-700 text-slate-400"
                      }`}
                    >
                      <Globe className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-wider">Web Access</span>
                    </button>
                    <button
                      onClick={() => setMode("controller")}
                      className="btn btn-xs h-7 rounded-lg border-none bg-slate-800 hover:bg-slate-700 text-slate-400 flex items-center gap-2"
                    >
                      <LayoutGrid className="w-3 h-3" />
                      <span className="text-[10px] font-bold uppercase tracking-wider">Controller</span>
                    </button>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/50 px-3 py-1 rounded-full border border-slate-700/50">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Mode: {mode}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* ── Right: Visualisers + Cognitive Stream ────────────────────── */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex flex-col flex-1 gap-3 overflow-hidden"
          >
            {/* Mental workspace */}
            <div className="flex flex-col flex-[1.2] glass-card rounded-3xl overflow-hidden relative">
              <div className={`flex items-center justify-between px-5 py-4 border-b border-white/5 relative z-10 backdrop-blur-md ${theme === "dark" ? "bg-slate-900/40" : "bg-white/40"}`}>
                <div className="flex items-center gap-3">
                  <div className="p-1.5 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
                    <Box className="w-4 h-4 text-indigo-400" />
                  </div>
                  <h2 className={`text-[11px] font-black uppercase tracking-[0.2em] ${theme === "dark" ? "text-white" : "text-slate-900"}`}>
                    Mental Workspace
                  </h2>
                </div>
                <button
                  onClick={() => setShowMentalMatrix(true)}
                  className="btn btn-xs h-7 rounded-lg border-none bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/20 flex items-center gap-2"
                >
                  <Brain className="w-3.5 h-3.5" />
                  <span className="text-[9px] font-bold uppercase tracking-widest">Simulate</span>
                </button>
              </div>

              <div className="flex-1 p-2 relative bg-slate-950/20 flex items-center justify-center">
                {visualizationData?.objects?.length > 0 ? (
                  /* Backend has sent mental workspace data — show a summary */
                  <div className="text-center space-y-2">
                    <div className="text-[11px] font-black uppercase tracking-widest text-indigo-400">
                      {visualizationData.label || 'Mental Workspace'}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      {visualizationData.objects.length} object{visualizationData.objects.length !== 1 ? 's' : ''} in scene
                    </div>
                    <div className="flex flex-wrap gap-1 justify-center max-w-[200px]">
                      {visualizationData.objects.slice(0, 8).map((obj, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[9px] font-bold text-indigo-400 uppercase">
                          {obj.label || obj.type}
                        </span>
                      ))}
                      {visualizationData.objects.length > 8 && (
                        <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[9px] text-slate-500">
                          +{visualizationData.objects.length - 8} more
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => setShowMentalMatrix(true)}
                      className="mt-2 px-4 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-[10px] font-black uppercase tracking-widest text-indigo-400 transition-all"
                    >
                      Open Simulator →
                    </button>
                  </div>
                ) : (
                  /* Idle — no backend data yet */
                  <div className="text-center space-y-3">
                    <div className="w-16 h-16 rounded-2xl bg-indigo-500/5 border border-indigo-500/10 flex items-center justify-center mx-auto">
                      <Brain className="w-7 h-7 text-indigo-500/30" />
                    </div>
                    <div>
                      <div className="text-[11px] font-black uppercase tracking-widest text-slate-600">Mental Workspace</div>
                      <div className="text-[10px] text-slate-700 mt-1">Opens when agent is running</div>
                    </div>
                    <button
                      onClick={() => setShowMentalMatrix(true)}
                      className="px-4 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/30 text-[10px] font-black uppercase tracking-widest text-indigo-400 transition-all"
                    >
                      Open Simulator
                    </button>
                  </div>
                )}
              </div>

              {/* WorldModelVisualizer only rendered when backend has sent data */}
              {worldModelData && (
                <div className="p-2 border-t border-white/5 h-48">
                  <WorldModelVisualizer data={worldModelData} />
                </div>
              )}
            </div>

            {/* Cognitive stream + activity */}
            <div className="flex flex-col flex-1 glass-card rounded-3xl overflow-hidden relative">
              <div className={`flex items-center gap-3 px-5 py-4 border-b border-white/5 relative z-10 backdrop-blur-md ${theme === "dark" ? "bg-slate-900/40" : "bg-white/40"}`}>
                <div className="p-1.5 bg-indigo-500/10 rounded-lg border border-indigo-500/20">
                  <Terminal className="w-4 h-4 text-indigo-400" />
                </div>
                <h2 className={`text-[11px] font-black uppercase tracking-[0.2em] ${theme === "dark" ? "text-white" : "text-slate-900"}`}>
                  Cognitive Stream
                </h2>
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
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500/50 opacity-0 group-hover:opacity-100 transition-opacity" />
                        <span className="text-indigo-400/50 mr-2 opacity-50">[{String(i).padStart(3, "0")}]</span>
                        {t}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  <div ref={thoughtsEndRef} className="h-4 w-full" />
                </div>
              </div>

              <div className={`p-4 border-t border-white/5 ${theme === "dark" ? "bg-slate-900/60" : "bg-slate-100/60"}`}>
                <ActivityBar activities={activities} theme={theme} />

                <AnimatePresence>
                  {showWebManager && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
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

      {/* Mental Matrix full-screen modal */}
      <MentalMatrixModal
        isOpen={showMentalMatrix}
        onClose={() => setShowMentalMatrix(false)}
        agentId={agentId}
      />
    </div>
  );
}

export default App;