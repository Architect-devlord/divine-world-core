import React from "react";

function MessageBubble({ sender, text }) {
  return (
    <div className={`message ${sender}`}>
      <span>{text}</span>
    </div>
  );
}

export default MessageBubble;
