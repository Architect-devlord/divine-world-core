import React from "react";

function AgentStatus({ connected, active }) {
  return (
    <div style={{ padding: "0.6rem", background: "#f0f0f0", fontSize: "0.9rem" }}>
      {connected ? "🟢 Connected" : "🔴 Disconnected"} | Brain:{" "}
      {active ? "🧠 Active" : "💤 Idle"}
    </div>
  );
}

export default AgentStatus;
