// src/components/AgentStatus.jsx
import React from "react";
import { motion, AnimatePresence } from "framer-motion";

function AgentStatus({ connected, active }) {
  return (
    <div className="flex items-center gap-4 px-4 py-1.5 rounded-full bg-slate-900/60 border border-slate-800/50 backdrop-blur-md shadow-inner">
      {/* Connection Status */}
      <div className="flex items-center gap-2">
        <div className="relative flex h-2.5 w-2.5">
          {connected && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          )}
          <span className={`relative inline-flex rounded-full h-2.5 w-2.5 transition-colors duration-500 ${
            connected ? "bg-emerald-500 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]"
          }`}></span>
        </div>
        <span className={`text-[11px] font-bold uppercase tracking-wider ${
          connected ? "text-emerald-400" : "text-rose-400"
        }`}>
          {connected ? "Online" : "Offline"}
        </span>
      </div>

      <div className="h-4 w-px bg-slate-800"></div>

      {/* Brain Activity Status */}
      <div className="flex items-center gap-2">
        <AnimatePresence mode="wait">
          {active ? (
            <motion.div
              key="active"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="flex items-center gap-2"
            >
              <div className="relative">
                <motion.div
                  animate={{
                    scale: [1, 1.3, 1],
                    opacity: [0.5, 1, 0.5],
                  }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  className="absolute inset-0 bg-indigo-500 rounded-full blur-sm"
                />
                <span className="relative flex h-2.5 w-2.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]"></span>
              </div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-400">
                Thinking
              </span>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="flex items-center gap-2"
            >
              <span className="flex h-2.5 w-2.5 rounded-full bg-slate-700"></span>
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Idle
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default AgentStatus;
