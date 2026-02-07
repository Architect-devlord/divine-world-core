// src/components/AgentStatus.jsx
import React from "react";

function AgentStatus({ connected, active }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-slate-800/50 border border-slate-700">
      {/* Connection Status */}
      <div className="flex items-center gap-1.5">
        <div className={`h-2 w-2 rounded-full transition-all duration-300 ${
          connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
        }`}></div>
        <span className="text-xs font-medium">
          {connected ? "🟢 Connected" : "🔴 Disconnected"}
        </span>
      </div>

      {/* Brain Activity Status */}
      <div className="h-4 w-px bg-slate-600"></div>
      <div className="flex items-center gap-1.5">
        <div className={`h-2 w-2 rounded-full transition-all duration-300 ${
          active ? "bg-blue-400 animate-pulse" : "bg-slate-600"
        }`}></div>
        <span className="text-xs font-medium">
          {active ? "🧠 Thinking" : "💤 Idle"}
        </span>
      </div>
    </div>
  );
}

export default AgentStatus;