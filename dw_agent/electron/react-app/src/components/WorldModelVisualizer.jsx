// src/components/WorldModelVisualizer.jsx
import React, { useState, useEffect, useRef } from "react";

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

    // Clear canvas
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, height);

    // Draw world model network
    if (data.network) {
      drawNetwork(ctx, data.network, width, height);
    }

    // Draw predictions if available
    if (showPredictions && data.predictions) {
      drawPredictions(ctx, data.predictions, width, height);
    }

    // Draw current state
    if (data.currentState) {
      drawCurrentState(ctx, data.currentState, width, height);
    }

    // Draw info panel
    drawInfoPanel(ctx, data, width, height);

  }, [data, showPredictions, animationFrame]);

  // Animation loop for dynamic elements
  useEffect(() => {
    const interval = setInterval(() => {
      setAnimationFrame(prev => prev + 1);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const drawNetwork = (ctx, network, width, height) => {
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.3;

    // Draw connections
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.2)';
    ctx.lineWidth = 1;

    network.nodes.forEach((node, i) => {
      network.nodes.forEach((otherNode, j) => {
        if (i !== j && Math.random() > 0.8) { // Random connections for visualization
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

      // Node size based on activation
      const baseSize = 8;
      const activation = node.activation || 0;
      const size = baseSize + activation * 12;

      // Color based on type
      let color = '#64748b'; // Default gray
      if (node.type === 'vision') color = '#3b82f6'; // Blue
      if (node.type === 'action') color = '#ef4444'; // Red
      if (node.type === 'reward') color = '#eab308'; // Yellow
      if (node.type === 'state') color = '#22c55e'; // Green

      // Pulsing effect for active nodes
      const pulse = Math.sin(animationFrame * 0.1 + i) * 0.3 + 0.7;
      ctx.fillStyle = color + Math.floor(pulse * 255).toString(16).padStart(2, '0');

      ctx.beginPath();
      ctx.arc(x, y, size, 0, Math.PI * 2);
      ctx.fill();

      // Border for selected/hovered
      if (isSelected || isHovered) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Label
      ctx.fillStyle = '#ffffff';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(node.label || `N${i}`, x, y + size + 15);
    });
  };

  const drawPredictions = (ctx, predictions, width, height) => {
    const startY = height - 100;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.fillRect(10, startY, width - 20, 90);

    ctx.fillStyle = '#ffffff';
    ctx.font = '12px monospace';
    ctx.fillText('Predictions:', 20, startY + 20);

    predictions.slice(0, 3).forEach((pred, i) => {
      const y = startY + 35 + i * 15;
      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`${pred.action}: ${pred.probability.toFixed(2)}`, 20, y);
    });
  };

  const drawCurrentState = (ctx, state, width, height) => {
    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.fillRect(width - 200, 10, 190, 120);

    ctx.fillStyle = '#ffffff';
    ctx.font = '11px monospace';
    ctx.fillText('Current State:', width - 190, 30);

    const metrics = [
      `Health: ${state.health?.toFixed(1) || 'N/A'}`,
      `Hunger: ${state.hunger?.toFixed(1) || 'N/A'}`,
      `Position: ${state.position ? `(${state.position.x?.toFixed(1)}, ${state.position.y?.toFixed(1)}, ${state.position.z?.toFixed(1)})` : 'N/A'}`,
      `Thoughts: ${state.thoughts?.length || 0}`,
      `Memories: ${state.memories || 0}`
    ];

    metrics.forEach((metric, i) => {
      ctx.fillStyle = '#94a3b8';
      ctx.fillText(metric, width - 190, 50 + i * 15);
    });
  };

  const drawInfoPanel = (ctx, data, width, height) => {
    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.fillRect(10, 10, 250, 80);

    ctx.fillStyle = '#ffffff';
    ctx.font = '12px monospace';
    ctx.fillText('World Model Status', 20, 30);

    const stats = [
      `Parameters: ${data.parameters?.toLocaleString() || 'N/A'}`,
      `Training Steps: ${data.trainingSteps || 0}`,
      `Buffer Size: ${data.bufferSize || 0}`,
      `Last Update: ${data.lastUpdate || 'Never'}`
    ];

    stats.forEach((stat, i) => {
      ctx.fillStyle = '#94a3b8';
      ctx.fillText(stat, 20, 50 + i * 15);
    });
  };

  const handleCanvasClick = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Check if clicked on a node
    if (data?.network?.nodes) {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = Math.min(canvas.width, canvas.height) * 0.3;

      data.network.nodes.forEach((node, i) => {
        const angle = (i / data.network.nodes.length) * Math.PI * 2;
        const nodeX = centerX + Math.cos(angle) * radius;
        const nodeY = centerY + Math.sin(angle) * radius;

        const distance = Math.sqrt((x - nodeX) ** 2 + (y - nodeY) ** 2);
        if (distance < 20) {
          setSelectedNode(selectedNode === i ? null : i);
        }
      });
    }
  };

  const requestPrediction = () => {
    if (onPredictionRequest) {
      onPredictionRequest();
    }
  };

  return (
    <div className="relative w-full h-full">
      <canvas
        ref={canvasRef}
        width={800}
        height={600}
        className="w-full h-full cursor-pointer"
        onClick={handleCanvasClick}
      />

      {/* Controls */}
      <div className="absolute top-4 right-4 flex gap-2">
        <button
          onClick={() => setShowPredictions(!showPredictions)}
          className={`btn btn-xs ${showPredictions ? 'btn-primary' : 'btn-ghost'}`}
        >
          {showPredictions ? 'Hide' : 'Show'} Predictions
        </button>
        <button
          onClick={requestPrediction}
          className="btn btn-xs btn-success"
        >
          Request Prediction
        </button>
      </div>

      {/* Selected Node Info */}
      {selectedNode !== null && data?.network?.nodes && (
        <div className="absolute bottom-4 left-4 bg-slate-800 p-3 rounded-lg max-w-xs">
          <h4 className="text-white font-semibold mb-2">
            Node {selectedNode}: {data.network.nodes[selectedNode].label}
          </h4>
          <div className="text-gray-300 text-sm space-y-1">
            <div>Type: {data.network.nodes[selectedNode].type}</div>
            <div>Activation: {data.network.nodes[selectedNode].activation?.toFixed(3) || 'N/A'}</div>
            <div>Connections: {data.network.nodes[selectedNode].connections || 'N/A'}</div>
          </div>
        </div>
      )}

      {/* Title */}
      <div className="absolute top-4 left-4 text-white">
        <h3 className="text-lg font-semibold">World Model Visualization</h3>
        <p className="text-sm text-gray-400">Click nodes to inspect • Real-time neural activity</p>
      </div>
    </div>
  );
}

export default WorldModelVisualizer;