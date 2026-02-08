// src/components/FileDropZone.jsx
import React, { useState } from "react";
import { Upload, FileCode, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

function FileDropZone({ onFileSend }) {
  const [isDragging, setIsDragging] = useState(false);
  const [sync, setSync] = useState(false);
  const [lastFile, setLastFile] = useState(null);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      setLastFile(file.name);
      const type = file.type.split("/")[0];
      onFileSend(file, type, sync);
      setTimeout(() => setLastFile(null), 3000);
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
    <motion.div
      layout
      className={`relative transition-all duration-500 border-2 border-dashed rounded-2xl overflow-hidden ${
        isDragging
          ? "border-indigo-500 bg-indigo-500/10 scale-[1.01] shadow-lg shadow-indigo-500/10"
          : "border-slate-300 dark:border-slate-800 bg-slate-200/50 dark:bg-slate-900/40 hover:border-indigo-400 dark:hover:border-slate-700"
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="p-6 flex flex-col items-center justify-center text-center">
        <AnimatePresence mode="wait">
          {lastFile ? (
            <motion.div
              key="success"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.5, opacity: 0 }}
              className="flex flex-col items-center"
            >
              <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center mb-3 border border-emerald-500/30">
                <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              </div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-400">Payload Ingested</p>
              <p className="text-[10px] text-slate-500 mt-1 truncate max-w-[200px]">{lastFile}</p>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center"
            >
              <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 transition-colors ${
                isDragging ? "bg-indigo-500 text-white" : "bg-slate-300 dark:bg-slate-800 text-slate-500 dark:text-slate-500"
              }`}>
                <Upload className="w-6 h-6" />
              </div>
              <p className={`text-[11px] font-bold uppercase tracking-widest transition-colors ${
                isDragging ? "text-indigo-400" : "text-slate-600 dark:text-slate-400"
              }`}>
                {isDragging ? "Release to Ingest" : "Drop Data Modules Here"}
              </p>
              <p className="text-[9px] font-black text-slate-500 dark:text-slate-600 mt-1 uppercase tracking-tighter">
                Img • Vid • Doc • Code
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mt-4 flex items-center gap-2">
          <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              checked={sync}
              onChange={(e) => setSync(e.target.checked)}
              className="checkbox checkbox-xs checkbox-primary border-slate-700"
            />
            <span className="text-[10px] font-bold uppercase tracking-tight text-slate-500 group-hover:text-slate-300 transition-colors">
              Synchronous Processing
            </span>
          </label>
        </div>
      </div>

      {isDragging && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="absolute inset-0 pointer-events-none bg-indigo-500/5 backdrop-blur-[2px]"
        />
      )}
    </motion.div>
  );
}

export default FileDropZone;
