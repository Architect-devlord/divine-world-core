import React, { useState } from 'react';
import { Camera, Mic, Folder, Wifi, AlertTriangle, Shield, Check } from 'lucide-react';

/**
 * Safety dialog for Controller Mode activation.
 * Displays permissions and warnings before enabling system access.
 */
export default function ControllerSafety() {
  const [showDialog, setShowDialog] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [acknowledgedRisks, setAcknowledgedRisks] = useState(false);
  const [controllerActive, setControllerActive] = useState(false);
  
  const permissions = [
    {
      icon: Camera,
      name: 'Camera Access',
      description: 'AI will capture and process visual input from webcam',
      risk: 'medium'
    },
    {
      icon: Mic,
      name: 'Microphone Access',
      description: 'AI will listen to and process audio from microphone',
      risk: 'medium'
    },
    {
      icon: Folder,
      name: 'File System Access',
      description: 'AI can read and write files on your computer',
      risk: 'high'
    },
    {
      icon: Wifi,
      name: 'Network Access',
      description: 'AI can make network requests and connections',
      risk: 'high'
    }
  ];

  const handleActivate = () => {
    if (!agreedToTerms || !acknowledgedRisks) {
      alert('Please read and acknowledge all warnings');
      return;
    }

    // Send activation request to backend
    fetch('/api/controller/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        permissions: permissions.map(p => p.name),
        timestamp: Date.now(),
        acknowledged: true
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        setControllerActive(true);
        setShowDialog(false);
      }
    })
    .catch(err => {
      console.error('Failed to activate controller:', err);
      alert('Failed to activate controller mode');
    });
  };

  const handleDeactivate = () => {
    fetch('/api/controller/deactivate', { method: 'POST' })
      .then(() => {
        setControllerActive(false);
        setAgreedToTerms(false);
        setAcknowledgedRisks(false);
      });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-gray-100 p-8">
      {/* Status Badge */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Shield className={`w-8 h-8 ${controllerActive ? 'text-red-500' : 'text-gray-500'}`} />
          <div>
            <h1 className="text-2xl font-bold">Controller Mode</h1>
            <p className="text-sm text-gray-400">
              {controllerActive ? 'ACTIVE - System Access Enabled' : 'Inactive'}
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

      {/* Permissions Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {permissions.map((perm, idx) => {
          const Icon = perm.icon;
          return (
            <div
              key={idx}
              className={`card bg-slate-900 border ${
                perm.risk === 'high' ? 'border-red-500/30' : 'border-yellow-500/30'
              }`}
            >
              <div className="card-body">
                <div className="flex items-start gap-4">
                  <Icon className={`w-8 h-8 ${
                    perm.risk === 'high' ? 'text-red-500' : 'text-yellow-500'
                  }`} />
                  <div>
                    <h3 className="font-bold">{perm.name}</h3>
                    <p className="text-sm text-gray-400">{perm.description}</p>
                    <div className="mt-2">
                      <span className={`badge ${
                        perm.risk === 'high' ? 'badge-error' : 'badge-warning'
                      }`}>
                        {perm.risk.toUpperCase()} RISK
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Activation Dialog */}
      {showDialog && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="card w-full max-w-2xl bg-slate-900 border border-red-500">
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
        <div className="card bg-slate-900 border border-slate-800">
          <div className="card-body">
            <h3 className="card-title">Controller Activity Monitor</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <ActivityIndicator
                label="Camera"
                active={true}
                icon={Camera}
              />
              <ActivityIndicator
                label="Microphone"
                active={true}
                icon={Mic}
              />
              <ActivityIndicator
                label="File Access"
                active={false}
                icon={Folder}
              />
              <ActivityIndicator
                label="Network"
                active={true}
                icon={Wifi}
              />
            </div>
          </div>
        </div>
      )}
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
                