import React, { useState, useEffect } from 'react';
import { Camera, Mic, Folder, Wifi, AlertTriangle, Shield, Check, Loader, X } from 'lucide-react';

/**
 * Safety dialog for Controller Mode activation.
 * Displays permissions and warnings before enabling system access.
 * Detects available devices (cameras, microphones).
 */
export default function ControllerSafety({ onModeChange }) {
  const [showDialog, setShowDialog] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [acknowledgedRisks, setAcknowledgedRisks] = useState(false);
  const [controllerActive, setControllerActive] = useState(false);
  const [devices, setDevices] = useState({ cameras: [], microphones: [] });
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [selectedDevices, setSelectedDevices] = useState({ camera: 0, microphone: 0 });
  
  // Permission toggles
  const [permissions, setPermissions] = useState({
    camera: true,
    microphone: true,
    filesystem: true,
    network: true
  });
  
  const BACKEND_URL = "http://127.0.0.1:11400";
  
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
      const response = await fetch(`${BACKEND_URL}/api/controller/detect-devices?agent_id=demo`);
      const data = await response.json();
      
      if (data.status === "success") {
        setDevices(data.devices);
        console.log("Detected devices:", data.devices);
      } else {
        console.error("Device detection failed:", data.message);
      }
    } catch (err) {
      console.error("Device detection error:", err);
    } finally {
      setDevicesLoading(false);
    }
  };

  const handleActivate = async () => {
    if (!agreedToTerms || !acknowledgedRisks) {
      alert('Please read and acknowledge all warnings');
      return;
    }

    try {
      // Get enabled permissions
      const enabledPermissions = permissionsList
        .filter(p => permissions[p.key])
        .map(p => p.name);
      
      if (enabledPermissions.length === 0) {
        alert('Please enable at least one permission to activate controller mode');
        return;
      }

      // Send activation request to backend
      const response = await fetch(`${BACKEND_URL}/api/controller/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: "demo",
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
        console.log("Controller mode activated successfully");
      } else {
        alert(`Failed to activate controller: ${data.message}`);
      }
    } catch (err) {
      console.error('Failed to activate controller:', err);
      alert('Failed to activate controller mode');
    }
  };

  const handleDeactivate = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/controller/deactivate?agent_id=demo`, { method: 'POST' });
      setControllerActive(false);
      setAgreedToTerms(false);
      setAcknowledgedRisks(false);
      console.log("Controller mode deactivated");
    } catch (err) {
      console.error("Failed to deactivate:", err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-gray-100 p-8">
      {/* Back Button and Status Badge */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => onModeChange && onModeChange()}
            className="btn btn-sm btn-ghost"
            title="Return to chat mode"
          >
            ← Back to Chat
          </button>
          <Shield className={`w-8 h-8 ${controllerActive ? 'text-red-500' : 'text-gray-500'}`} />
          <div>
            <h1 className="text-2xl font-bold">Controller Mode</h1>
            <p className="text-sm text-gray-400">
              {controllerActive ? (
                <>🟢 ACTIVE - {Object.values(permissions).filter(v => v).length}/{permissionsList.length} permissions enabled</>
              ) : (
                <>⚫ Inactive - {Object.values(permissions).filter(v => v).length}/{permissionsList.length} permissions enabled</>
              )}
            </p>
          </div>
        </div>

        {controllerActive ? (
          <button
            onClick={handleDeactivate}
            className="btn btn-error gap-2"
          >
            <AlertTriangle className="w-5 h-5" />
            Deactivate
          </button>
        ) : (
          <button
            onClick={() => setShowDialog(true)}
            className="btn btn-primary gap-2"
          >
            <Shield className="w-5 h-5" />
            Activate Controller Mode
          </button>
        )}
      </div>

      {/* Active Controller Status */}
      {controllerActive && (
        <div className="alert alert-warning shadow-lg mb-8">
          <AlertTriangle className="w-6 h-6" />
          <div>
            <h3 className="font-bold">Controller Mode Active</h3>
            <p className="text-sm">AI has full system access. Monitor activity carefully.</p>
          </div>
        </div>
      )}

      {/* Permissions Overview with Toggles */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {permissionsList.map((perm, idx) => {
          const Icon = perm.icon;
          const isEnabled = permissions[perm.key];
          return (
            <div
              key={idx}
              className={`card bg-slate-900 border transition-all ${
                isEnabled 
                  ? (perm.risk === 'high' ? 'border-red-500/30' : 'border-yellow-500/30')
                  : 'border-slate-700/30 opacity-60'
              }`}
            >
              <div className="card-body">
                <div className="flex items-start gap-4 justify-between">
                  <div className="flex items-start gap-4 flex-1">
                    <Icon className={`w-8 h-8 flex-shrink-0 ${
                      isEnabled
                        ? (perm.risk === 'high' ? 'text-red-500' : 'text-yellow-500')
                        : 'text-gray-600'
                    }`} />
                    <div>
                      <h3 className="font-bold">{perm.name}</h3>
                      <p className="text-sm text-gray-400">{perm.description}</p>
                      <div className="mt-2">
                        <span className={`badge ${
                          isEnabled
                            ? (perm.risk === 'high' ? 'badge-error' : 'badge-warning')
                            : 'badge-ghost'
                        }`}>
                          {isEnabled ? `${perm.risk.toUpperCase()} RISK` : 'DISABLED'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={(e) => setPermissions({
                        ...permissions,
                        [perm.key]: e.target.checked
                      })}
                      className="checkbox checkbox-sm"
                      disabled={controllerActive}
                      title={controllerActive ? "Cannot change permissions while active" : "Allow this permission"}
                    />
                  </label>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Activation Dialog */}
      {showDialog && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="card w-full max-w-2xl bg-slate-900 border border-red-500 max-h-[90vh] overflow-y-auto">
            <div className="card-body">
              <h2 className="card-title text-2xl text-red-500 mb-4">
                <AlertTriangle className="w-8 h-8" />
                Controller Mode Activation Warning
              </h2>

              <div className="space-y-4 my-6">
                <div className="alert alert-error">
                  <AlertTriangle className="w-6 h-6" />
                  <div>
                    <h3 className="font-bold">⚠️ CRITICAL WARNING</h3>
                    <p className="text-sm">
                      Controller Mode grants the AI extensive system access.
                      Only activate if you fully understand the implications.
                    </p>
                  </div>
                </div>

                {/* Device Detection Section */}
                <div className="bg-slate-800 p-4 rounded-lg">
                  <h4 className="font-bold mb-3 flex items-center gap-2">
                    {devicesLoading ? (
                      <>
                        <Loader className="w-4 h-4 animate-spin" />
                        Detecting Devices...
                      </>
                    ) : (
                      <>
                        <Check className="w-4 h-4 text-green-500" />
                        Available Devices
                      </>
                    )}
                  </h4>
                  
                  {devices.cameras.length > 0 && (
                    <div className="mb-4">
                      <label className="text-sm font-semibold text-gray-300 mb-2 block">
                        📷 Cameras ({devices.cameras.length} detected)
                      </label>
                      <select 
                        className="select select-bordered w-full bg-slate-700"
                        value={selectedDevices.camera}
                        onChange={(e) => setSelectedDevices({...selectedDevices, camera: parseInt(e.target.value)})}
                      >
                        {devices.cameras.map((cam) => (
                          <option key={cam.index} value={cam.index}>
                            {cam.name} - {cam.resolution[0]}x{cam.resolution[1]}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  
                  {devices.microphones.length > 0 && (
                    <div className="mb-4">
                      <label className="text-sm font-semibold text-gray-300 mb-2 block">
                        🎤 Microphones ({devices.microphones.length} detected)
                      </label>
                      <select 
                        className="select select-bordered w-full bg-slate-700"
                        value={selectedDevices.microphone}
                        onChange={(e) => setSelectedDevices({...selectedDevices, microphone: parseInt(e.target.value)})}
                      >
                        {devices.microphones.map((mic) => (
                          <option key={mic.index} value={mic.index}>
                            {mic.name} - {mic.channels}ch @ {mic.sample_rate}Hz
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {devices.cameras.length === 0 && devices.microphones.length === 0 && !devicesLoading && (
                    <p className="text-yellow-500 text-sm">⚠️ No devices detected. Check system permissions.</p>
                  )}
                </div>

                <div className="bg-slate-800 p-4 rounded-lg">
                  <h4 className="font-bold mb-2">What AI Can Do:</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-gray-300">
                    <li>See through your camera in real-time</li>
                    <li>Listen to audio from your microphone</li>
                    <li>Read and write files on your computer</li>
                    <li>Make network connections</li>
                    <li>Monitor system resources and processes</li>
                    <li>Learn from all captured data</li>
                  </ul>
                </div>

                <div className="bg-slate-800 p-4 rounded-lg">
                  <h4 className="font-bold mb-2">Safety Measures:</h4>
                  <ul className="list-disc list-inside space-y-1 text-sm text-gray-300">
                    <li>All activities are logged and can be reviewed</li>
                    <li>You can deactivate controller mode at any time</li>
                    <li>File system access is sandboxed (configurable)</li>
                    <li>Network requests can be filtered</li>
                  </ul>
                </div>

                {/* Permission Summary */}
                <div className="bg-slate-800 p-4 rounded-lg mb-6">
                  <h4 className="font-bold mb-3 text-gray-300">🔐 Permission Summary</h4>
                  <div className="grid grid-cols-2 gap-3">
                    {permissionsList.map((perm) => (
                      <div key={perm.key} className="flex items-center gap-2">
                        {permissions[perm.key] ? (
                          <Check className="w-5 h-5 text-green-500 flex-shrink-0" />
                        ) : (
                          <X className="w-5 h-5 text-gray-500 flex-shrink-0" />
                        )}
                        <span className={`text-sm ${permissions[perm.key] ? 'text-gray-200' : 'text-gray-500 line-through'}`}>
                          {perm.name}
                        </span>
                      </div>
                    ))}
                  </div>
                  {Object.values(permissions).every(v => !v) && (
                    <div className="text-red-500 text-sm mt-3">
                      ⚠️ All permissions are disabled! Enable at least one to activate.
                    </div>
                  )}
                </div>

                {/* Acknowledgment Checkboxes */}
                <div className="space-y-3 mt-6">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={agreedToTerms}
                      onChange={(e) => setAgreedToTerms(e.target.checked)}
                      className="checkbox checkbox-error mt-1"
                    />
                    <span className="text-sm">
                      I understand that the AI will have access to my camera, microphone,
                      file system, and network, and I accept the associated risks.
                    </span>
                  </label>

                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={acknowledgedRisks}
                      onChange={(e) => setAcknowledgedRisks(e.target.checked)}
                      className="checkbox checkbox-error mt-1"
                    />
                    <span className="text-sm">
                      I acknowledge that I am responsible for monitoring the AI's behavior
                      and will deactivate controller mode if any concerning activity occurs.
                    </span>
                  </label>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="card-actions justify-end mt-4">
                <button
                  onClick={() => {
                    setShowDialog(false);
                    setAgreedToTerms(false);
                    setAcknowledgedRisks(false);
                  }}
                  className="btn btn-ghost"
                >
                  Cancel
                </button>
                <button
                  onClick={handleActivate}
                  disabled={!agreedToTerms || !acknowledgedRisks}
                  className="btn btn-error gap-2"
                >
                  {agreedToTerms && acknowledgedRisks ? (
                    <>
                      <Check className="w-5 h-5" />
                      Activate Controller Mode
                    </>
                  ) : (
                    'Read & Acknowledge All Warnings'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Activity Monitor (when active) */}
      {controllerActive && (
        <ControllerActivityMonitor agentId="demo" />
      )}
    </div>
  );
}

/**
 * Real-time controller activity monitor
 */
function ControllerActivityMonitor({ agentId }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const BACKEND_URL = "http://127.0.0.1:11400";

  useEffect(() => {
    // Fetch initial status
    fetchStatus();
    
    // Poll for updates every 2 seconds
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
      <div className="card bg-slate-900 border border-slate-800">
        <div className="card-body">
          <h3 className="card-title">Controller Activity Monitor</h3>
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-slate-900 border border-slate-800">
      <div className="card-body">
        <div className="flex items-center justify-between mb-4">
          <h3 className="card-title">Controller Activity Monitor</h3>
          <button 
            onClick={fetchStatus}
            className="btn btn-sm btn-ghost"
          >
            🔄 Refresh
          </button>
        </div>
        
        {/* Current Permissions */}
        {status.permissions && (
          <div className="bg-slate-800 p-4 rounded-lg mb-6">
            <h4 className="font-bold mb-3 text-gray-300">
              🔐 Active Permissions ({status.permissions_count}/4)
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="flex items-center gap-2">
                {status.permissions.camera ? (
                  <><Check className="w-4 h-4 text-green-500" /> <span>📷 Camera</span></>
                ) : (
                  <><X className="w-4 h-4 text-gray-500" /> <span className="text-gray-500">📷 Camera</span></>
                )}
              </div>
              <div className="flex items-center gap-2">
                {status.permissions.microphone ? (
                  <><Check className="w-4 h-4 text-green-500" /> <span>🎤 Microphone</span></>
                ) : (
                  <><X className="w-4 h-4 text-gray-500" /> <span className="text-gray-500">🎤 Microphone</span></>
                )}
              </div>
              <div className="flex items-center gap-2">
                {status.permissions.filesystem ? (
                  <><Check className="w-4 h-4 text-green-500" /> <span>📁 File System</span></>
                ) : (
                  <><X className="w-4 h-4 text-gray-500" /> <span className="text-gray-500">📁 File System</span></>
                )}
              </div>
              <div className="flex items-center gap-2">
                {status.permissions.network ? (
                  <><Check className="w-4 h-4 text-green-500" /> <span>🌐 Network</span></>
                ) : (
                  <><X className="w-4 h-4 text-gray-500" /> <span className="text-gray-500">🌐 Network</span></>
                )}
              </div>
            </div>
          </div>
        )}
        
        {/* Device Status */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <ActivityIndicator
            label="Camera"
            active={status.camera_active && status.permissions?.camera}
            icon={Camera}
          />
          <ActivityIndicator
            label="Microphone"
            active={status.microphone_active && status.permissions?.microphone}
            icon={Mic}
          />
          <ActivityIndicator
            label="File Access"
            active={status.permissions?.filesystem}
            icon={Folder}
          />
          <ActivityIndicator
            label="Network"
            active={status.permissions?.network}
            icon={Wifi}
          />
        </div>

        {/* Stats */}
        {status.stats && (
          <div className="bg-slate-800 p-4 rounded-lg">
            <h4 className="font-bold mb-3 text-gray-300">Runtime Statistics</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div>
                <span className="text-gray-500">Frames Processed</span>
                <p className="text-xl font-bold text-green-400">{status.stats.frames_processed}</p>
              </div>
              <div>
                <span className="text-gray-500">Audio Chunks</span>
                <p className="text-xl font-bold text-yellow-400">{status.stats.audio_chunks_processed}</p>
              </div>
              <div>
                <span className="text-gray-500">Learning Events</span>
                <p className="text-xl font-bold text-blue-400">{status.stats.learning_events}</p>
              </div>
              <div>
                <span className="text-gray-500">Files Processed</span>
                <p className="text-xl font-bold text-purple-400">{status.stats.files_processed}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Activity indicator component
 */
function ActivityIndicator({ label, active, icon: Icon }) {
  return (
    <div className={`flex flex-col items-center gap-2 p-4 rounded-lg border ${
      active ? 'border-red-500 bg-red-500/10' : 'border-slate-700 bg-slate-800'
    }`}>
      <Icon className={`w-6 h-6 ${active ? 'text-red-500' : 'text-gray-500'}`} />
      <span className="text-sm font-medium">{label}</span>
      <div className={`w-2 h-2 rounded-full ${
        active ? 'bg-red-500 animate-pulse' : 'bg-gray-600'
      }`} />
    </div>
  );
}
                