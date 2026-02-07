// src/components/FileDropZone.jsx
import React, { useState } from "react";
import { Upload } from "lucide-react";

function FileDropZone({ onFileSend }) {
  const [isDragging, setIsDragging] = useState(false);
  const [sync, setSync] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const file = e.dataTransfer.files[0];
    if (file) {
      const type = file.type.split("/")[0]; // 'image', 'video', 'text', etc.
      onFileSend(file, type, sync);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  return (
    <div
      className={`transition-all duration-300 border-2 border-dashed m-4 rounded-lg ${
        isDragging
          ? "border-indigo-500 bg-indigo-500/10 scale-[1.02]"
          : "border-slate-700 bg-slate-800/30 hover:border-slate-600"
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="p-6 text-center">
        <Upload className={`w-8 h-8 mx-auto mb-2 transition-colors ${
          isDragging ? "text-indigo-400" : "text-slate-500"
        }`} />
        <p className={`text-sm font-medium transition-colors ${
          isDragging ? "text-indigo-400" : "text-slate-400"
        }`}>
          {isDragging ? "Drop file here" : "Drop files here to send to agent"}
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Supports images, videos, documents, and more
        </p>
        <div className="mt-3 flex items-center justify-center gap-2 text-xs">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={sync} onChange={(e) => setSync(e.target.checked)} className="checkbox checkbox-sm" />
            <span>Request immediate processing (sync)</span>
          </label>
        </div>
      </div>
    </div>
  );
}

export default FileDropZone;