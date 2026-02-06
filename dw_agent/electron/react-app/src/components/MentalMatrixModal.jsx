// src/components/MentalMatrixModal.jsx
import React, { useState } from 'react';
import { X, Share2, Download, Upload } from 'lucide-react';
import MentalMatrixSimulator from './MentalMatrixSimulator';

function MentalMatrixModal({ isOpen, onClose, agentId }) {
  const [simulationState, setSimulationState] = useState(null);
  const [exportFormat, setExportFormat] = useState('json');

  if (!isOpen) return null;

  const handleExport = () => {
    if (simulationState) {
      const dataStr = JSON.stringify(simulationState, null, 2);
      const dataBlob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `mental-matrix-${agentId}-${Date.now()}.json`;
      link.click();
    }
  };

  const handleSimulationEvent = (event) => {
    console.log('Simulation event:', event);
    setSimulationState(event);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-slate-950 rounded-lg w-full h-full max-w-6xl max-h-screen flex flex-col border border-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <span className="text-purple-400">🧠</span>
              Mental Matrix Simulator
            </h2>
            <p className="text-xs text-gray-400 mt-1">
              Real-time simulation environment for {agentId}
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-circle btn-lg"
          >
            <X size={24} />
          </button>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <MentalMatrixSimulator agentId={agentId} onSimulationEvent={handleSimulationEvent} />
        </div>

        {/* Footer with Controls */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/50 flex justify-between items-center">
          <div className="flex gap-2">
            <button onClick={handleExport} className="btn btn-sm btn-outline gap-2">
              <Download size={16} />
              Export
            </button>
            <button className="btn btn-sm btn-outline gap-2">
              <Upload size={16} />
              Import
            </button>
            <button className="btn btn-sm btn-outline gap-2">
              <Share2 size={16} />
              Share Simulation
            </button>
          </div>
          <div className="text-xs text-gray-400">
            {simulationState && (
              <span>
                Last update: {new Date().toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default MentalMatrixModal;
