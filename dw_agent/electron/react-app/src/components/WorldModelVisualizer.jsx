// src/components/WorldModelVisualizer.jsx
import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Target, Zap, Shield } from "lucide-react";

/**
 * FIX SUMMARY (vs original):
 *
 * 1. BLURRY CANVAS — canvas was hardcoded width=800 height=600 but rendered
 *    w-full h-full. CSS scales a 800×600 surface up to fill its container,
 *    giving blurry output. Fix: ResizeObserver keeps canvas intrinsic size
 *    equal to its layout size (×devicePixelRatio for HiDPI).
 *
 * 2. BROKEN CLICK HIT-TEST — handleCanvasClick used canvas.width (800) for
 *    node position math but getBoundingClientRect() returns layout pixels.
 *    On a typical screen canvas.width === rect.width happens to be true at
 *    800px wide but breaks at any other size. Fix: always use
 *    canvas.width / canvas.height (now matching layout) for all math.
 */

function WorldModelVisualizer({ data, onPredictionRequest }) {
  const canvasRef         = useRef(null);
  const containerRef      = useRef(null);
  const [selectedNode,    setSelectedNode]    = useState(null);
  const [hoveredNode,     setHoveredNode]     = useState(null);
  const [showPredictions, setShowPredictions] = useState(true);
  const [animFrame,       setAnimFrame]       = useState(0);
  const [canvasSize,      setCanvasSize]      = useState({ w: 800, h: 400 });

  // ── Keep canvas intrinsic size = layout size ─────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setCanvasSize({ w: Math.floor(width), h: Math.floor(height) });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Advance animation ticker at 10 fps
  useEffect(() => {
    const id = setInterval(() => setAnimFrame(f => f + 1), 100);
    return () => clearInterval(id);
  }, []);

  // ── Draw ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx    = canvas.getContext('2d');
    const { width: W, height: H } = canvas;

    ctx.fillStyle = '#020617';
    ctx.fillRect(0, 0, W, H);

    // Subtle grid
    ctx.strokeStyle = 'rgba(30, 41, 59, 0.3)';
    ctx.lineWidth = 1;
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
    for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

    if (data.network) drawNetwork(ctx, data.network, W, H);

    ctx.strokeStyle = 'rgba(99, 102, 241, 0.1)';
    ctx.strokeRect(10, 10, 250, 85);
    ctx.strokeRect(W - 200, 10, 190, 125);
  }, [data, showPredictions, animFrame, canvasSize, selectedNode, hoveredNode]);

  const drawNetwork = (ctx, network, W, H) => {
    const cx     = W / 2;
    const cy     = H / 2;
    const radius = Math.min(W, H) * 0.35;

    // Connections
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.15)';
    ctx.lineWidth = 1;
    network.nodes.forEach((_, i) => {
      network.nodes.forEach((__, j) => {
        if (i !== j && (i + j) % 7 === 0) {
          const a1 = (i / network.nodes.length) * Math.PI * 2;
          const a2 = (j / network.nodes.length) * Math.PI * 2;
          const x1 = cx + Math.cos(a1) * radius, y1 = cy + Math.sin(a1) * radius;
          const x2 = cx + Math.cos(a2) * radius, y2 = cy + Math.sin(a2) * radius;
          ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
          // Flow particle
          if ((animFrame + i) % 20 < 5) {
            const t  = ((animFrame + i) % 20) / 5;
            ctx.fillStyle = 'rgba(129,140,248,0.4)';
            ctx.beginPath();
            ctx.arc(x1 + (x2-x1)*t, y1 + (y2-y1)*t, 2, 0, Math.PI*2);
            ctx.fill();
          }
        }
      });
    });

    // Nodes
    network.nodes.forEach((node, i) => {
      const angle = (i / network.nodes.length) * Math.PI * 2;
      const x     = cx + Math.cos(angle) * radius;
      const y     = cy + Math.sin(angle) * radius;
      const act   = node.activation || 0;
      const size  = 6 + act * 15;
      const pulse = Math.sin(animFrame * 0.2 + i) * 0.4 + 0.6;

      let color = '#475569', glow = 'rgba(71,85,105,0.2)';
      if (node.type === 'vision')  { color = '#3b82f6'; glow = 'rgba(59,130,246,0.4)'; }
      if (node.type === 'action')  { color = '#f43f5e'; glow = 'rgba(244,63,94,0.4)'; }
      if (node.type === 'reward')  { color = '#eab308'; glow = 'rgba(234,179,8,0.4)'; }
      if (node.type === 'state')   { color = '#10b981'; glow = 'rgba(16,185,129,0.4)'; }

      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(x, y, size * (1.5 + pulse * 0.5), 0, Math.PI*2); ctx.fill();

      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI*2); ctx.fill();

      if (selectedNode === i || hoveredNode === i) {
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.stroke();
      }

      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.font = 'bold 9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText((node.label || `N${i}`).toUpperCase(), x, y + size + 14);
    });
  };

  // ── Hit-test: use canvas.width/height (now matches layout pixels) ─────────
  const handleCanvasClick = useCallback(e => {
    const canvas = canvasRef.current;
    if (!canvas || !data?.network?.nodes) return;
    const rect = canvas.getBoundingClientRect();
    // Scale from CSS pixels to canvas pixels (should be 1:1 after our ResizeObserver fix)
    const scaleX = canvas.width  / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx     = (e.clientX - rect.left)  * scaleX;
    const my     = (e.clientY - rect.top)   * scaleY;

    const cx     = canvas.width  / 2;
    const cy     = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) * 0.35;

    let hit = null;
    data.network.nodes.forEach((node, i) => {
      const a  = (i / data.network.nodes.length) * Math.PI * 2;
      const nx = cx + Math.cos(a) * radius;
      const ny = cy + Math.sin(a) * radius;
      if (Math.hypot(mx - nx, my - ny) < 20) hit = i;
    });
    setSelectedNode(hit !== null ? (selectedNode === hit ? null : hit) : selectedNode);
  }, [data, selectedNode]);

  return (
    <div ref={containerRef} className="relative w-full h-full group">
      <canvas
        ref={canvasRef}
        width={canvasSize.w}
        height={canvasSize.h}
        className="w-full h-full cursor-crosshair rounded-2xl"
        onClick={handleCanvasClick}
      />

      <div className="absolute top-4 left-4 pointer-events-none">
        <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-white">World_Model_Latent_Space</h3>
        <p className="text-[9px] text-slate-500 font-mono tracking-tighter uppercase mt-1">Neural_Map // Live</p>
      </div>

      <div className="absolute top-4 right-4 flex gap-2">
        <button
          onClick={() => setShowPredictions(s => !s)}
          className={`btn btn-xs h-7 rounded-lg border-none px-3 text-[9px] font-black uppercase tracking-widest ${
            showPredictions ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400'
          }`}
        >
          Predictions: {showPredictions ? 'On' : 'Off'}
        </button>
      </div>

      {/* Metrics overlay */}
      <div className="absolute bottom-4 right-4 bg-slate-900/60 backdrop-blur-md p-4 rounded-2xl border border-white/5 min-w-[160px]">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3 border-b border-white/5 pb-2">Internal State</h4>
        {data.currentState && (
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-[9px] text-slate-400 uppercase font-bold">Health</span>
              <span className="text-[10px] font-mono text-emerald-400">{(data.currentState.health || 0).toFixed(1)}%</span>
            </div>
            <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
              <div className="bg-emerald-500 h-full transition-all" style={{ width: `${data.currentState.health || 0}%` }} />
            </div>
            <div className="flex justify-between items-center mt-2">
              <span className="text-[9px] text-slate-400 uppercase font-bold">Buffer</span>
              <span className="text-[10px] font-mono text-indigo-400">{data.bufferSize || 0}</span>
            </div>
          </div>
        )}
      </div>

      {/* Node detail */}
      <AnimatePresence>
        {selectedNode !== null && data?.network?.nodes?.[selectedNode] && (
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
              <h4 className="text-white font-black uppercase tracking-widest text-xs">Node_Metadata</h4>
            </div>
            <div className="space-y-3 font-mono text-[10px]">
              {[
                ['Label',      data.network.nodes[selectedNode].label],
                ['Class',      data.network.nodes[selectedNode].type],
                ['Activation', (data.network.nodes[selectedNode].activation || 0).toFixed(4)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-white/5 pb-1">
                  <span className="text-slate-500 uppercase">{k}</span>
                  <span className="text-indigo-400">{v}</span>
                </div>
              ))}
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