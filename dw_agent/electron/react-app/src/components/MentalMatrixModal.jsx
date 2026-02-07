// src/components/MentalMatrixModal.jsx
import React, { useState } from 'react';
import { X, Share2, Download, Upload, Cpu, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import MentalMatrixSimulator from './MentalMatrixSimulator';

function MentalMatrixModal({ isOpen, onClose, agentId }) {
  const [simulationState, setSimulationState] = useState(null);

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
    setSimulationState(event);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 md:p-8">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-slate-950/80 backdrop-blur-xl"
            onClick={onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="bg-slate-950 rounded-[2rem] w-full h-full max-w-7xl relative flex flex-col border border-white/10 shadow-[0_0_50px_rgba(99,102,241,0.15)] overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-8 py-6 border-b border-white/5 bg-slate-900/40 backdrop-blur-md">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20 shadow-inner">
                  <Cpu className="w-6 h-6 text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-xl font-black uppercase tracking-[0.2em] text-white flex items-center gap-3">
                    Mental Matrix <span className="text-indigo-500">v1.4</span>
                  </h2>
                  <p className="text-[10px] text-slate-500 font-mono tracking-tighter uppercase">
                    Sandbox Engine // Instance: {agentId} // Status: <span className="text-emerald-500">Active</span>
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="btn btn-ghost btn-circle hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden bg-slate-950">
              <MentalMatrixSimulator agentId={agentId} onSimulationEvent={handleSimulationEvent} />
            </div>

            {/* Footer with Controls */}
            <div className="px-8 py-5 border-t border-white/5 bg-slate-900/40 backdrop-blur-md flex justify-between items-center">
              <div className="flex gap-3">
                <button onClick={handleExport} className="btn btn-sm h-9 rounded-xl border-slate-800 bg-slate-800/50 hover:bg-slate-700 text-[10px] font-bold uppercase tracking-widest gap-2">
                  <Download size={14} className="text-indigo-400" />
                  Dump Buffer
                </button>
                <button className="btn btn-sm h-9 rounded-xl border-slate-800 bg-slate-800/50 hover:bg-slate-700 text-[10px] font-bold uppercase tracking-widest gap-2">
                  <Upload size={14} className="text-cyan-400" />
                  Load State
                </button>
              </div>

              <div className="flex items-center gap-6">
                {simulationState && (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Activity size={14} className="text-emerald-500 animate-pulse" />
                      <span className="text-[10px] font-mono text-slate-400 uppercase tracking-tighter">Telemetery Stream: OK</span>
                    </div>
                    <div className="h-4 w-px bg-slate-800"></div>
                    <span className="text-[10px] font-mono text-slate-500 uppercase">
                      L_UPD: {new Date().toLocaleTimeString()}
                    </span>
                  </div>
                )}
                <div className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[9px] font-black text-indigo-400 uppercase tracking-widest">
                  Secure Layer 7
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

export default MentalMatrixModal;
