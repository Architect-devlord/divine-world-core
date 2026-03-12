// src/components/MentalMatrixModal.jsx
import React, { useState } from 'react';
import { X, Download, Upload, Cpu, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import MentalMatrixSimulator from './MentalMatrixSimulator';

function MentalMatrixModal({ isOpen, onClose, agentId }) {
  const [simulationState, setSimulationState] = useState(null);

  const handleExport = () => {
    if (!simulationState) return;
    const blob = new Blob([JSON.stringify(simulationState, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `mental-matrix-${agentId}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 md:p-8">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-slate-950/80 backdrop-blur-xl"
            onClick={onClose}
          />

          {/* Modal panel
              IMPORTANT: NO scale transform on initial — scale(0.9) collapses
              the container to ~0px before Three.js can measure it, causing a
              black viewport. Fade-only entrance avoids the issue entirely.   */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="relative z-10 bg-slate-950 rounded-[2rem] w-full h-full max-w-7xl flex flex-col border border-white/10 shadow-[0_0_50px_rgba(99,102,241,0.15)] overflow-hidden"
          >
            {/* Header */}
            <div className="flex-shrink-0 flex items-center justify-between px-8 py-5 border-b border-white/5 bg-slate-900/40 backdrop-blur-md">
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
                  <Cpu className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-lg font-black uppercase tracking-[0.2em] text-white flex items-center gap-3">
                    Mental Matrix <span className="text-indigo-500">v1.4</span>
                  </h2>
                  <p className="text-[10px] text-slate-500 font-mono tracking-tighter uppercase">
                    Sandbox // Instance: {agentId} // <span className="text-emerald-500">Active</span>
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-xl hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
              >
                <X size={22} />
              </button>
            </div>

            {/* Simulator — takes all remaining height */}
            <div className="flex-1 min-h-0 overflow-hidden">
              <MentalMatrixSimulator
                agentId={agentId}
                onSimulationEvent={setSimulationState}
              />
            </div>

            {/* Footer */}
            <div className="flex-shrink-0 px-8 py-4 border-t border-white/5 bg-slate-900/40 backdrop-blur-md flex justify-between items-center">
              <div className="flex gap-3">
                <button
                  onClick={handleExport}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-800/50 hover:bg-slate-700 border border-slate-700 text-[10px] font-bold uppercase tracking-widest text-slate-300 transition-all"
                >
                  <Download size={13} className="text-indigo-400" />
                  Dump Buffer
                </button>
                <button
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-800/50 hover:bg-slate-700 border border-slate-700 text-[10px] font-bold uppercase tracking-widest text-slate-300 transition-all"
                >
                  <Upload size={13} className="text-cyan-400" />
                  Load State
                </button>
              </div>

              <div className="flex items-center gap-5">
                {simulationState && (
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <Activity size={13} className="text-emerald-500 animate-pulse" />
                      <span className="text-[10px] font-mono text-slate-400 uppercase tracking-tighter">
                        Telemetry: OK
                      </span>
                    </div>
                    <div className="h-3 w-px bg-slate-800" />
                    <span className="text-[10px] font-mono text-slate-500 uppercase">
                      {new Date().toLocaleTimeString()}
                    </span>
                  </div>
                )}
                <div className="px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[9px] font-black text-indigo-400 uppercase tracking-widest">
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