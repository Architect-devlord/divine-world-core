import React, { useState, useEffect, useRef } from 'react';
import { Camera, Mic, Folder, Wifi, AlertTriangle, Shield, Check, Loader, X, MessageSquare, Send, ChevronRight, ChevronLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import MessageBubble from './components/MessageBubble';

/**
 * Safety dialog for Controller Mode activation.
 * Displays permissions and warnings before enabling system access.
 * Detects available devices (cameras, microphones).
 */
export default function ControllerSafety({ onModeChange, messages, sendMessage, inputText, setInputText, agentId, backendUrl }) {
  const [showDialog, setShowDialog] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [acknowledgedRisks, setAcknowledgedRisks] = useState(false);
  const [controllerActive, setControllerActive] = useState(false);
  const [devices, setDevices] = useState({ cameras: [], microphones: [] });
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [selectedDevices, setSelectedDevices] = useState({ camera: 0, microphone: 0 });
  const [isChatOpen, setIsChatOpen] = useState(true);

  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (isChatOpen && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isChatOpen]);

  // Permission toggles
  const [permissions, setPermissions] = useState({
    camera: true,
    microphone: true,
    filesystem: true,
    network: true
  });

  const BACKEND_URL = backendUrl;
  // FIX: was hardcoded "http://127.0.0.1:11400" - silently talked to the
  // wrong backend for any agent not on port 11400. App.jsx already derives
  // the real value from its own URL; use that instead of guessing here.

  const permissionsList = [
    {
      icon: Camera,
      name: 'Camera Access',
      description: 'AI will capture and process visual input from webcam',
      risk: 'medium',
      key: 'camera'
    },
    {
      icon: Mic,
      name: 'Microphone Access',
      description: 'AI will listen to and process audio from microphone',
      risk: 'medium',
      key: 'microphone'
    },
    {
      icon: Folder,
      name: 'File System Access',
      description: 'AI can read and write files on your computer',
      risk: 'high',
      key: 'filesystem'
    },
    {
      icon: Wifi,
      name: 'Network Access',
      description: 'AI can make network requests and connections',
      risk: 'high',
      key: 'network'
    }
  ];

  // Detect available devices when dialog opens
  useEffect(() => {
    if (showDialog && devices.cameras.length === 0) {
      detectDevices();
    }
  }, [showDialog]);

  const detectDevices = async () => {
    setDevicesLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/controller/detect-devices?agent_id=${agentId}`);
      const data = await response.json();

      if (data.status === "success") {
        setDevices(data.devices);
      }
    } catch (err) {
      console.error("Device detection error:", err);
    } finally {
      setDevicesLoading(false);
    }
  };

  const handleActivate = async () => {
    if (!agreedToTerms || !acknowledgedRisks) return;

    try {
      const enabledPermissions = permissionsList
        .filter(p => permissions[p.key])
        .map(p => p.name);

      if (enabledPermissions.length === 0) return;

      const response = await fetch(`${BACKEND_URL}/api/controller/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: agentId,
          permissions: enabledPermissions,
          permissionSettings: permissions,
          devices: selectedDevices,
          timestamp: Date.now(),
          acknowledged: true
        })
      });

      const data = await response.json();
      if (data.status === "success") {
        setControllerActive(true);
        setShowDialog(false);
      }
    } catch (err) {
      console.error('Failed to activate controller:', err);
    }
  };

  const handleDeactivate = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/controller/deactivate?agent_id=${agentId}`, { method: 'POST' });
      setControllerActive(false);
    } catch (err) {
      console.error("Failed to deactivate:", err);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden transition-colors duration-300" style={{ backgroundColor: 'var(--app-bg)', color: 'var(--app-text)' }}>
      {/* Collapsible Chat Sidebar */}
      <motion.div
        animate={{ width: isChatOpen ? 350 : 0 }}
        transition={{ type: "spring", damping: 20, stiffness: 100 }}
        className="relative border-r border-white/5 flex flex-col overflow-hidden glass-card"
      >
        <div className="p-4 border-b border-white/5 flex items-center justify-between min-w-[350px]">
          <h2 className="text-xs font-black uppercase tracking-widest text-indigo-400">System Comms</h2>
          <button onClick={() => setIsChatOpen(false)} className="p-1 hover:bg-white/5 rounded">
            <ChevronLeft size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar min-w-[350px]">
          <AnimatePresence initial={false}>
            {messages?.map((msg, i) => (
              <MessageBubble key={i} sender={msg.sender} text={msg.text} />
            ))}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 border-t border-white/5 min-w-[350px]" style={{ backgroundColor: 'var(--input-bg)' }}>
          <div className="relative">
            <input
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Send command..."
              className="w-full border rounded-xl py-2 pl-4 pr-10 text-xs focus:outline-none focus:border-indigo-500/50 transition-colors"
              style={{ backgroundColor: 'var(--app-bg)', borderColor: 'var(--card-border)', color: 'var(--app-text)' }}
              onKeyPress={(e) => e.key === "Enter" && sendMessage()}
            />
            <button
              onClick={() => sendMessage()}
              className="absolute right-2 top-1.5 p-1 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white transition-all"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </motion.div>

      {/* Open Sidebar Button (when collapsed) */}
      {!isChatOpen && (
        <motion.button
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          onClick={() => setIsChatOpen(true)}
          className="absolute left-4 top-1/2 -translate-y-1/2 z-10 w-8 h-12 bg-slate-900/80 border border-white/5 rounded-r-xl flex items-center justify-center hover:bg-indigo-600 transition-colors shadow-xl"
        >
          <ChevronRight size={16} />
        </motion.button>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-8 relative">
        {/* Back Button and Status Badge */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <button
              onClick={() => onModeChange && onModeChange()}
              className="btn btn-sm btn-ghost hover:bg-slate-800 border-white/5 text-[10px] font-bold uppercase tracking-widest h-8 px-4 rounded-xl glass-card"
            >
              ← Back to Chat
            </button>
            <div className={`p-2 rounded-xl border ${controllerActive ? 'bg-red-500/10 border-red-500/20' : 'bg-slate-900 border-white/5'}`}>
              <Shield className={`w-5 h-5 ${controllerActive ? 'text-red-500' : 'text-gray-500'}`} />
            </div>
            <div>
              <h1 className={`text-sm font-black uppercase tracking-[0.2em] transition-colors`}>Controller Mode <span className="text-rose-500">v1.2</span></h1>
              <p className="text-[10px] text-gray-500 font-mono tracking-tighter">
                {controllerActive ? (
                  <span className="text-emerald-500">🟢 STATUS: ACTIVE // {Object.values(permissions).filter(v => v).length} PERMS ENGAGED</span>
                ) : (
                  <span>⚫ STATUS: INACTIVE // WAITING_FOR_AUTH</span>
                )}
              </p>
            </div>
          </div>

          {controllerActive ? (
            <button
              onClick={handleDeactivate}
              className="btn btn-error btn-sm h-10 px-6 rounded-xl gap-2 font-bold uppercase tracking-widest text-[10px]"
            >
              <AlertTriangle className="w-4 h-4" />
              Kill Instance
            </button>
          ) : (
            <button
              onClick={() => setShowDialog(true)}
              className="btn btn-primary btn-sm h-10 px-6 rounded-xl gap-2 font-bold uppercase tracking-widest text-[10px] shadow-lg shadow-indigo-500/20"
            >
              <Shield className="w-4 h-4" />
              Authorize Access
            </button>
          )}
        </div>

        {/* Active Controller Status */}
        {controllerActive && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="alert border-rose-500/50 bg-rose-500/10 glass-dark text-rose-200 shadow-2xl mb-8 rounded-2xl"
          >
            <AlertTriangle className="w-5 h-5" />
            <div className="flex-1">
              <h3 className="font-black text-xs uppercase tracking-widest">Enhanced System Access Engaged</h3>
              <p className="text-[10px] opacity-80 uppercase tracking-tighter">AI has full peripheral and filesystem control. Monitoring mandatory.</p>
            </div>
          </motion.div>
        )}

        {/* Permissions Overview with Toggles */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-8">
          {permissionsList.map((perm, idx) => {
            const Icon = perm.icon;
            const isEnabled = permissions[perm.key];
            return (
              <div
                key={idx}
                className={`glass-card p-6 rounded-[2rem] transition-all border ${
                  isEnabled
                    ? (perm.risk === 'high' ? 'border-red-500/20 shadow-lg shadow-red-500/5' : 'border-yellow-500/20 shadow-lg shadow-yellow-500/5')
                    : 'border-slate-800 opacity-40 grayscale'
                }`}
              >
                <div className="flex items-start gap-5">
                  <div className={`p-4 rounded-2xl ${
                    isEnabled
                      ? (perm.risk === 'high' ? 'bg-red-500/10 text-red-500' : 'bg-yellow-500/10 text-yellow-500')
                      : 'bg-slate-800 text-slate-500'
                  }`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-center mb-2">
                      <h3 className="font-black text-xs uppercase tracking-widest">{perm.name}</h3>
                      <input
                        type="checkbox"
                        checked={isEnabled}
                        onChange={(e) => setPermissions({
                          ...permissions,
                          [perm.key]: e.target.checked
                        })}
                        className="checkbox checkbox-sm checkbox-primary"
                        disabled={controllerActive}
                      />
                    </div>
                    <p className="text-[10px] text-gray-400 uppercase tracking-tighter leading-relaxed mb-4">{perm.description}</p>
                    <div className={`inline-flex px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${
                      isEnabled
                        ? (perm.risk === 'high' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400')
                        : 'bg-slate-800 text-slate-600'
                    }`}>
                      {isEnabled ? `${perm.risk} Risk Level` : 'Auth Pending'}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Activation Dialog */}
        <AnimatePresence>
          {showDialog && (
            <div className="fixed inset-0 flex items-center justify-center z-[100] p-4">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 bg-slate-950/80 backdrop-blur-md"
                onClick={() => setShowDialog(false)}
              />
              <motion.div
                initial={{ scale: 0.9, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.9, opacity: 0, y: 20 }}
                className="bg-slate-900 border border-rose-500/30 rounded-[2.5rem] shadow-2xl shadow-rose-500/10 w-full max-w-2xl relative overflow-hidden"
              >
                <div className="p-10">
                  <div className="flex items-center gap-6 mb-8 pb-8 border-b border-white/5">
                    <div className="p-4 bg-rose-500/10 rounded-2xl border border-rose-500/20 animate-pulse">
                      <AlertTriangle className="w-8 h-8 text-rose-500" />
                    </div>
                    <div>
                      <h2 className="text-2xl font-black uppercase tracking-widest text-rose-500">System Handover</h2>
                      <p className="text-xs text-slate-400 font-mono tracking-tighter mt-1">PROTOCOL: DW_CONTROLLER_V1.2 // AUTH_REQUIRED</p>
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className="bg-slate-950/50 p-6 rounded-2xl border border-white/5">
                      <h4 className="font-black text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-4">Device Mapping</h4>

                      {devicesLoading ? (
                        <div className="flex items-center gap-3 text-indigo-400 text-xs font-bold animate-pulse">
                          <Loader className="w-4 h-4 animate-spin" /> SCANNING_PERIPHERALS...
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {devices.cameras.length > 0 && (
                            <div>
                              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Visual_Feed</label>
                              <select
                                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-xs focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                                value={selectedDevices.camera}
                                onChange={(e) => setSelectedDevices({...selectedDevices, camera: parseInt(e.target.value)})}
                              >
                                {devices.cameras.map((cam) => (
                                  <option key={cam.index} value={cam.index}>{cam.name}</option>
                                ))}
                              </select>
                            </div>
                          )}
                          {devices.microphones.length > 0 && (
                            <div>
                              <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Audio_Stream</label>
                              <select
                                className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-xs focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                                value={selectedDevices.microphone}
                                onChange={(e) => setSelectedDevices({...selectedDevices, microphone: parseInt(e.target.value)})}
                              >
                                {devices.microphones.map((mic) => (
                                  <option key={mic.index} value={mic.index}>{mic.name}</option>
                                ))}
                              </select>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="space-y-4">
                      <label className="flex items-start gap-4 p-4 rounded-2xl bg-slate-800/30 border border-white/5 cursor-pointer hover:bg-slate-800/50 transition-colors group">
                        <input
                          type="checkbox"
                          checked={agreedToTerms}
                          onChange={(e) => setAgreedToTerms(e.target.checked)}
                          className="checkbox checkbox-error mt-0.5"
                        />
                        <span className="text-[11px] font-bold uppercase tracking-tight text-slate-400 group-hover:text-slate-200 transition-colors">
                          I accept full responsibility for all system modifications and data capture performed by the AI.
                        </span>
                      </label>

                      <label className="flex items-start gap-4 p-4 rounded-2xl bg-slate-800/30 border border-white/5 cursor-pointer hover:bg-slate-800/50 transition-colors group">
                        <input
                          type="checkbox"
                          checked={acknowledgedRisks}
                          onChange={(e) => setAcknowledgedRisks(e.target.checked)}
                          className="checkbox checkbox-error mt-0.5"
                        />
                        <span className="text-[11px] font-bold uppercase tracking-tight text-slate-400 group-hover:text-slate-200 transition-colors">
                          I acknowledge the High Risk nature of this operational mode and will monitor all egress traffic.
                        </span>
                      </label>
                    </div>
                  </div>

                  <div className="flex justify-end gap-4 mt-10 pt-10 border-t border-white/5">
                    <button onClick={() => setShowDialog(false)} className="px-6 py-3 text-[10px] font-black uppercase tracking-widest text-slate-500 hover:text-white transition-colors">Abort</button>
                    <button
                      onClick={handleActivate}
                      disabled={!agreedToTerms || !acknowledgedRisks}
                      className="px-8 py-3 bg-rose-600 hover:bg-rose-500 disabled:opacity-30 disabled:hover:bg-rose-600 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] shadow-xl shadow-rose-500/20 transition-all active:scale-95"
                    >
                      Confirm Auth
                    </button>
                  </div>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Activity Monitor (when active) */}
        {controllerActive && (
          <div className="mt-8">
            <ControllerActivityMonitor agentId={agentId} backendUrl={backendUrl} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Real-time controller activity monitor
 */
function ControllerActivityMonitor({ agentId, backendUrl }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  // FIX: was hardcoded "http://127.0.0.1:11400", same issue as the parent
  // component - now takes the real value as a prop instead.
  const BACKEND_URL = backendUrl;

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/controller/status?agent_id=${agentId}`);
      const data = await response.json();
      setStatus(data);
      setLoading(false);
    } catch (err) {
      console.error("Failed to fetch controller status:", err);
      setLoading(false);
    }
  };

  if (loading || !status) {
    return (
      <div className="glass-card rounded-[2rem] p-8 text-center">
        <Loader className="w-8 h-8 text-indigo-500 animate-spin mx-auto mb-4" />
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Syncing Payload Status...</p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-[2.5rem] overflow-hidden border border-white/5">
      <div className="p-10">
        <div className="flex items-center justify-between mb-8 border-b border-white/5 pb-8">
          <div className="flex items-center gap-4">
            <Activity className="text-indigo-500 w-5 h-5 animate-pulse" />
            <h3 className="text-sm font-black uppercase tracking-widest">Runtime Analytics</h3>
          </div>
          <button onClick={fetchStatus} className="p-2 hover:bg-white/5 rounded-xl transition-colors text-slate-500"><Check size={18} /></button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-10">
          <ActivityIndicator label="Camera" active={status.camera_active && status.permissions?.camera} icon={Camera} />
          <ActivityIndicator label="Microphone" active={status.microphone_active && status.permissions?.microphone} icon={Mic} />
          <ActivityIndicator label="File Engine" active={status.permissions?.filesystem} icon={Folder} />
          <ActivityIndicator label="Network" active={status.permissions?.network} icon={Wifi} />
        </div>

        {status.stats && (
          <div className="bg-slate-950/50 p-8 rounded-[2rem] border border-white/5">
            <h4 className="font-black text-[11px] uppercase tracking-[0.2em] text-slate-500 mb-6">Core Statistics</h4>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
              <StatItem label="Visual Frames" value={status.stats.frames_processed} color="text-emerald-400" />
              <StatItem label="Audio Buffers" value={status.stats.audio_chunks_processed} color="text-yellow-400" />
              <StatItem label="Neural Events" value={status.stats.learning_events} color="text-indigo-400" />
              <StatItem label="File Ops" value={status.stats.files_processed} color="text-rose-400" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatItem({ label, value, color }) {
  return (
    <div>
      <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest block mb-1">{label}</span>
      <p className={`text-2xl font-black ${color} tracking-tighter`}>{value}</p>
    </div>
  );
}

function ActivityIndicator({ label, active, icon: Icon }) {
  return (
    <div className={`flex flex-col items-center gap-3 p-6 rounded-[2rem] border transition-all ${
      active ? 'border-rose-500/30 bg-rose-500/5' : 'border-slate-800 bg-slate-900/40'
    }`}>
      <Icon className={`w-6 h-6 ${active ? 'text-rose-500' : 'text-slate-600'}`} />
      <span className={`text-[10px] font-black uppercase tracking-widest ${active ? 'text-rose-400' : 'text-slate-500'}`}>{label}</span>
      <div className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-rose-500 animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.6)]' : 'bg-slate-800'}`} />
    </div>
  );
}