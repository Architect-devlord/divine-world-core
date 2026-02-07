// src/components/MessageBubble.jsx
import React from "react";
import { motion } from "framer-motion";

function MessageBubble({ sender, text }) {
  const isUser = sender === "user";
  const isAgent = sender === "agent";
  const isSystem = sender === "system";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`chat ${isUser ? "chat-end" : "chat-start"} mb-2`}
    >
      <div className="chat-header text-[10px] opacity-50 mb-1 px-2 uppercase tracking-wider font-bold">
        {sender}
      </div>
      <div
        className={`chat-bubble shadow-lg border backdrop-blur-md transition-all duration-300 hover:shadow-indigo-500/10 ${
          isUser
            ? "bg-indigo-600/40 border-indigo-500/30 text-indigo-50"
            : isAgent
            ? "bg-cyan-600/30 border-cyan-500/20 text-cyan-50"
            : "bg-slate-800/40 border-slate-700/30 text-slate-100 italic"
        }`}
      >
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {text}
        </div>
      </div>
    </motion.div>
  );
}

export default MessageBubble;
