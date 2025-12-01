import React, { useState } from "react";
import MessageBubble from "./MessageBubble";

function ChatWindow({ messages, onSend }) {
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    onSend(input);
    setInput("");
  };

  return (
    <div className="chat-window">
      {messages.map((msg, i) => (
        <MessageBubble key={i} sender={msg.sender} text={msg.text} />
      ))}
      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <button onClick={handleSend}>Send</button>
      </div>
    </div>
  );
}

export default ChatWindow;
