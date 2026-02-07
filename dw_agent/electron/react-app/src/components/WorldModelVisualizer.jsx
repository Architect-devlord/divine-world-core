// src/components/WorldModelVisualizer.jsx
import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Target, Zap, Shield } from "lucide-react";

function WorldModelVisualizer({ data, onPredictionRequest }) {
  const canvasRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [showPredictions, setShowPredictions] = useState(true);
  const [animationFrame, setAnimationFrame] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Deep Dark Space Background
    ctx.fillStyle = '#020617';
    ctx.fillRect(0, 0, width, height);

    // Subtle grid pattern
    ctx.strokeStyle = 'rgba(30, 41, 59, 0.3)';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    }
    for (let y = 0; y < height; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
    }

    // Draw world model network
    if (data.network) {
      drawNetwork(ctx, data.network, width, height);
    }

    // Draw info panel highlights
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.1)';
    ctx.strokeRect(10, 10, 250, 85);
    ctx.strokeRect(width - 200, 10, 190, 125);

  }, [data, showPredictions, animationFrame]);

  useEffect(() => {
    const interval = setInterval(() => {
      setAnimationFrame(prev => prev + 1);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const drawNetwork = (ctx, network, width, height) => {
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.35;

    // Draw connections
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.15)';
    ctx.lineWidth = 1;

    network.nodes.forEach((node, i) => {
      network.nodes.forEach((otherNode, j) => {
        if (i !== j && (i + j) % 7 === 0) { // Deterministic connections for visualization
          const angle1 = (i / network.nodes.length) * Math.PI * 2;
          const angle2 = (j / network.nodes.length) * Math.PI * 2;
          const x1 = centerX + Math.cos(angle1) * radius;
          const y1 = centerY + Math.sin(angle1) * radius;
          const x2 = centerX + Math.cos(angle2) * radius;
          const y2 = centerY + Math.sin(angle2) * radius;

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();

          // Flow animation on connection
          if ((animationFrame + i) % 20 < 5) {
            const t = ((animationFrame + i) % 20) / 5;
            const fx = x1 + (x2 - x1) * t;
            const fy = y1 + (y2 - y1) * t;
            ctx.fillStyle = 'rgba(129, 140, 248, 0.4)';
            ctx.beginPath(); ctx.arc(fx, fy, 2, 0, Math.PI * 2); ctx.fill();
          }
        }
      });
    });

    // Draw nodes
    network.nodes.forEach((node, i) => {
      const angle = (i / network.nodes.length) * Math.PI * 2;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;

      const isSelected = selectedNode === i;
      const isHovered = hoveredNode === i;

      const baseSize = 6;
      const activation = node.activation || 0;
      const size = baseSize + activation * 15;

      // Color Palette matching theme
      let color = '#475569'; // Slate 600
      let glowColor = 'rgba(71, 85, 105, 0.2)';

      if (node.type === 'vision') { color = '#3b82f6'; glowColor = 'rgba(59, 130, 246, 0.4)'; }
      if (node.type === 'action') { color = '#f43f5e'; glowColor = 'rgba(244, 63, 94, 0.4)'; }
      if (node.type === 'reward') { color = '#eab308'; glowColor = 'rgba(234, 179, 8, 0.4)'; }
      if (node.type === 'state') { color = '#10b981'; glowColor = 'rgba(16, 185, 129, 0.4)'; }

      // Glow effect
      const pulse = Math.sin(animationFrame * 0.2 + i) * 0.4 + 0.6;
      const grad = ctx.createRadialGradient(x, y, 0, x, y, size * 2);
      grad.addColorStop(0, color);
      grad.addColorStop(1, 'transparent');

      ctx.fillStyle = glowColor;
      ctx.beginPath(); ctx.arc(x, y, size * (1.5 + pulse * 0.5), 0, Math.PI * 2); ctx.fill();

      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI * 2); ctx.fill();

      if (isSelected || isHovered) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.font = 'bold 9px font-mono';
      ctx.textAlign = 'center';
      ctx.fillText(node.label?.toUpperCase() || `N${i}`, x, y + size + 14);
    });
  };

  const handleCanvasClick = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (data?.network?.nodes) {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = Math.min(canvas.width, canvas.height) * 0.35;

      data.network.nodes.forEach((node, i) => {
        const angle = (i / data.network.nodes.length) * Math.PI * 2;
        const nodeX = centerX + Math.cos(angle) * radius;
        const nodeY = centerY + Math.sin(angle) * radius;
        const distance = Math.sqrt((x - nodeX) ** 2 + (y - nodeY) ** 2);
        if (distance < 20) setSelectedNode(selectedNode === i ? null : i);
      });
    }
  };

  return (
    <div className="relative w-full h-full group">
      <canvas
        ref={canvasRef}
        width={800}
        height={600}
        className="w-full h-full cursor-crosshair rounded-2xl"
        onClick={handleCanvasClick}
      />

      {/* Overlay UI */}
      <div className="absolute top-4 left-4 pointer-events-none">
        <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-white">World_Model_Latent_Space</h3>
        <p className="text-[9px] text-slate-500 font-mono tracking-tighter uppercase mt-1">Neural_Map // Resolution: 2048px</p>
      </div>

      <div className="absolute top-4 right-4 flex gap-2">
        <button
          onClick={() => setShowPredictions(!showPredictions)}
          className={`btn btn-xs h-7 rounded-lg border-none transition-all px-3 text-[9px] font-black uppercase tracking-widest ${showPredictions ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400'}`}
        >
          {showPredictions ? 'Predictions: On' : 'Predictions: Off'}
        </button>
      </div>

      {/* State Metrics (Simplified) */}
      <div className="absolute bottom-4 right-4 bg-slate-900/60 backdrop-blur-md p-4 rounded-2xl border border-white/5 min-w-[160px]">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3 border-b border-white/5 pb-2">Internal State</h4>
        <div className="space-y-2">
          {data.currentState && (
            <>
              <div className="flex justify-between items-center">
                <span className="text-[9px] text-slate-400 uppercase font-bold">Health</span>
                <span className="text-[10px] font-mono text-emerald-400">{(data.currentState.health || 0).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
                <div className="bg-emerald-500 h-full" style={{ width: `${data.currentState.health || 0}%` }}></div>
              </div>
              <div className="flex justify-between items-center mt-2">
                <span className="text-[9px] text-slate-400 uppercase font-bold">Buffer</span>
                <span className="text-[10px] font-mono text-indigo-400">{data.bufferSize || 0}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Node Detail */}
      <AnimatePresence>
        {selectedNode !== null && data?.network?.nodes && (
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="absolute bottom-4 left-4 bg-slate-900/80 backdrop-blur-xl p-5 rounded-3xl border border-indigo-500/30 w-64 shadow-2xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-indigo-500/20 rounded-xl border border-indigo-500/20">
                <Target className="w-4 h-4 text-indigo-400" />
              </div>
              <h4 className="text-white font-black uppercase tracking-widest text-xs">
                Node_Metadata
              </h4>
            </div>
            <div className="space-y-3 font-mono text-[10px]">
              <div className="flex justify-between border-b border-white/5 pb-1">
                <span className="text-slate-500 uppercase">Label</span>
                <span className="text-indigo-400">{data.network.nodes[selectedNode].label}</span>
              </div>
              <div className="flex justify-between border-b border-white/5 pb-1">
                <span className="text-slate-500 uppercase">Class</span>
                <span className="text-slate-300 capitalize">{data.network.nodes[selectedNode].type}</span>
              </div>
              <div className="flex justify-between border-b border-white/5 pb-1">
                <span className="text-slate-500 uppercase">Activation</span>
                <span className="text-emerald-400">{(data.network.nodes[selectedNode].activation || 0).toFixed(4)}</span>
              </div>
            </div>
            <button onClick={() => setSelectedNode(null)} className="w-full mt-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-[9px] font-black uppercase tracking-widest transition-colors">
              Close Inspection
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default WorldModelVisualizer;
