// src/components/MessageBubble.jsx
import React from "react";

function MessageBubble({ sender, text }) {
  const isUser = sender === "user";
  const isAgent = sender === "agent";
  const isSystem = sender === "system";

  return (
    <div className={`chat transition-transform duration-300 hover:scale-[1.02] ${
      isUser ? "chat-end" : "chat-start"
    }`}>
      <div className={`chat-bubble shadow-md transition-all duration-200 ${
        isUser
          ? "bg-indigo-600/70"
          : isAgent
          ? "bg-cyan-700/60"
          : "bg-slate-700/60"
      }`}>
        {text}
      </div>
    </div>
  );
}

export default MessageBubble;