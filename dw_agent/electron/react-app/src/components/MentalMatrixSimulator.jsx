// src/components/MentalMatrixSimulator.jsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import { OBJLoader }  from 'three/examples/jsm/loaders/OBJLoader';
import { Plus, Trash2, Play, Pause, RotateCcw, Eye, EyeOff, Upload, Move } from 'lucide-react';

function MentalMatrixSimulator({ agentId, onSimulationEvent }) {
  const containerRef = useRef(null);
  const sceneRef     = useRef(null);
  const cameraRef    = useRef(null);
  const rendererRef  = useRef(null);
  const animFrameRef = useRef(null);
  const initDoneRef  = useRef(false);   // guard: only init Three.js once
  const raycasterRef = useRef(new THREE.Raycaster());
  const meshMapRef   = useRef(new Map());
  const physicsRef   = useRef(new Map());
  const orbitRef     = useRef({ theta: 0.8, phi: 0.9, radius: 35 });
  const mouseRef     = useRef({
    down: false, button: 0, lastX: 0, lastY: 0,
    draggingId: null,
    dragPlane:  new THREE.Plane(),   // rebuilt per-grab as camera-facing plane
    dragOffset: new THREE.Vector3(),
  });
  const isRunningRef = useRef(false);
  const timeScaleRef = useRef(1.0);

  const [isRunning,        setIsRunning]        = useState(false);
  const [simulatedObjects, setSimulatedObjects] = useState([]);
  const [selectedId,       setSelectedId]       = useState(null);
  const [showGrid,         setShowGrid]         = useState(true);
  const [timeScale,        setTimeScale]        = useState(1.0);
  const [showDropdown,     setShowDropdown]     = useState(false);
  const [interactMode,     setInteractMode]     = useState('orbit');
  const [importStatus,     setImportStatus]     = useState(null);
  const [importMsg,        setImportMsg]        = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => { isRunningRef.current = isRunning;  }, [isRunning]);
  useEffect(() => { timeScaleRef.current = timeScale; }, [timeScale]);

  // ── Camera ─────────────────────────────────────────────────────────────────
  const applyOrbit = useCallback(() => {
    const cam = cameraRef.current;
    if (!cam) return;
    const { theta, phi, radius } = orbitRef.current;
    cam.position.set(
      radius * Math.sin(phi) * Math.sin(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.cos(theta),
    );
    cam.lookAt(0, 0, 0);
  }, []);

  // ── Raycast: find which tracked object was clicked ─────────────────────────
  const raycastObjects = useCallback((clientX, clientY) => {
    const renderer = rendererRef.current;
    const camera   = cameraRef.current;
    if (!renderer || !camera) return null;
    const rect = renderer.domElement.getBoundingClientRect();
    raycasterRef.current.setFromCamera(
      new THREE.Vector2(
        ((clientX - rect.left) / rect.width)  *  2 - 1,
        ((clientY - rect.top)  / rect.height) * -2 + 1,
      ),
      camera,
    );
    const targets = [];
    meshMapRef.current.forEach(obj => obj.traverse(c => { if (c.isMesh) targets.push(c); }));
    const hits = raycasterRef.current.intersectObjects(targets, false);
    if (!hits.length) return null;
    let node = hits[0].object;
    while (node) {
      for (const [id, obj] of meshMapRef.current.entries()) {
        let cur = node;
        while (cur) { if (cur === obj) return { id, point: hits[0].point }; cur = cur.parent; }
      }
      node = node.parent;
    }
    return null;
  }, []);

  // ── Three.js init (deferred until container has nonzero size) ──────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const tryInit = (w, h) => {
      if (initDoneRef.current || w === 0 || h === 0) return;
      initDoneRef.current = true;

      // Scene
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x0a0f1e);
      scene.fog = new THREE.FogExp2(0x0a0f1e, 0.008);
      sceneRef.current = scene;

      // Camera
      const camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000);
      cameraRef.current = camera;
      applyOrbit();

      // Renderer
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(window.devicePixelRatio);
      renderer.setSize(w, h);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.2;
      container.appendChild(renderer.domElement);
      rendererRef.current = renderer;

      // Lights
      scene.add(new THREE.AmbientLight(0x334466, 1.5));
      const sun = new THREE.DirectionalLight(0xffffff, 2);
      sun.position.set(30, 40, 20);
      sun.castShadow = true;
      sun.shadow.mapSize.setScalar(2048);
      sun.shadow.camera.left = sun.shadow.camera.bottom = -60;
      sun.shadow.camera.right = sun.shadow.camera.top   =  60;
      sun.shadow.camera.far = 200;
      scene.add(sun);
      const fill = new THREE.DirectionalLight(0x4466ff, 0.4);
      fill.position.set(-20, 10, -20);
      scene.add(fill);

      // Grid + ground
      scene.add(new THREE.GridHelper(80, 20, 0x1e3a5f, 0x0d1f33));
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(80, 80),
        new THREE.MeshStandardMaterial({ color: 0x0d1525, roughness: 0.9, metalness: 0.1 }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.receiveShadow = true;
      scene.add(ground);

      // ── Mouse handlers ─────────────────────────────────────────────────
      const dom = renderer.domElement;

      // Build a camera-facing plane through a world point.
      // This plane's normal points straight at the camera, so intersecting the
      // mouse ray with it gives full X/Y/Z movement — not just XZ.
      const makeCameraPlane = (worldPos) => {
        const normal = new THREE.Vector3();
        camera.getWorldDirection(normal); // points away from camera
        // We want the plane facing the camera, so negate
        normal.negate();
        const plane = new THREE.Plane();
        plane.setFromNormalAndCoplanarPoint(normal, worldPos);
        return plane;
      };

      const onMouseDown = e => {
        mouseRef.current.down   = true;
        mouseRef.current.button = e.button;
        mouseRef.current.lastX  = e.clientX;
        mouseRef.current.lastY  = e.clientY;
        if (e.button !== 0) return;
        const hit = raycastObjects(e.clientX, e.clientY);
        if (hit) {
          mouseRef.current.draggingId = hit.id;
          const obj = meshMapRef.current.get(hit.id);

          // Camera-facing plane through the exact hit point → full 3-axis drag
          mouseRef.current.dragPlane = makeCameraPlane(hit.point);

          // Offset = object origin minus hit point, so grab feels natural
          const intersectPt = new THREE.Vector3();
          raycasterRef.current.ray.intersectPlane(mouseRef.current.dragPlane, intersectPt);
          if (obj) mouseRef.current.dragOffset.subVectors(obj.position, intersectPt);

          const phys = physicsRef.current.get(hit.id);
          if (phys) { phys._savedGravity = phys.useGravity; phys.useGravity = false; phys.velocity = { x:0, y:0, z:0 }; }
          setSelectedId(hit.id);
          setInteractMode('drag');
        } else {
          mouseRef.current.draggingId = null;
          setInteractMode('orbit');
        }
      };

      const onMouseUp = () => {
        const id = mouseRef.current.draggingId;
        if (id) {
          const phys = physicsRef.current.get(id);
          if (phys?._savedGravity !== undefined) { phys.useGravity = phys._savedGravity; delete phys._savedGravity; }
        }
        mouseRef.current.down = false;
        mouseRef.current.draggingId = null;
        setInteractMode('orbit');
      };

      const onMouseMove = e => {
        if (!mouseRef.current.down) return;
        const dx = e.clientX - mouseRef.current.lastX;
        const dy = e.clientY - mouseRef.current.lastY;
        mouseRef.current.lastX = e.clientX;
        mouseRef.current.lastY = e.clientY;
        const did = mouseRef.current.draggingId;
        if (did && mouseRef.current.button === 0) {
          // Project mouse ray onto the camera-facing plane for full 3-axis movement
          const rect2 = dom.getBoundingClientRect();
          raycasterRef.current.setFromCamera(
            new THREE.Vector2(
              ((e.clientX - rect2.left) / rect2.width)  *  2 - 1,
              ((e.clientY - rect2.top)  / rect2.height) * -2 + 1,
            ),
            camera,
          );
          const target = new THREE.Vector3();
          if (raycasterRef.current.ray.intersectPlane(mouseRef.current.dragPlane, target)) {
            target.add(mouseRef.current.dragOffset);
            const obj = meshMapRef.current.get(did);
            if (obj) obj.position.copy(target); // full X, Y, Z
          }
        } else {
          // orbit
          orbitRef.current.theta -= dx * 0.007;
          orbitRef.current.phi   = Math.max(0.05, Math.min(Math.PI - 0.05, orbitRef.current.phi + dy * 0.007));
          applyOrbit();
        }
      };

      const onWheel = e => {
        e.preventDefault();
        orbitRef.current.radius = Math.max(3, Math.min(120, orbitRef.current.radius + e.deltaY * 0.05));
        applyOrbit();
      };

      dom.addEventListener('mousedown', onMouseDown);
      dom.addEventListener('contextmenu', e => e.preventDefault());
      window.addEventListener('mouseup',   onMouseUp);
      window.addEventListener('mousemove', onMouseMove);
      dom.addEventListener('wheel', onWheel, { passive: false });

      // ── Animation loop ──────────────────────────────────────────────────
      const animate = () => {
        animFrameRef.current = requestAnimationFrame(animate);
        if (isRunningRef.current) {
          const dt = (1 / 60) * timeScaleRef.current;
          physicsRef.current.forEach((phys, id) => {
            if (mouseRef.current.draggingId === id) return;
            const mesh = meshMapRef.current.get(id);
            if (!mesh) return;
            mesh.position.x += phys.velocity.x * dt;
            mesh.position.y += phys.velocity.y * dt;
            mesh.position.z += phys.velocity.z * dt;
            if (phys.useGravity) phys.velocity.y -= 9.8 * dt;
            if (mesh.position.y < 1 && phys.useGravity) {
              mesh.position.y  = 1;
              phys.velocity.y *= -0.55;
              phys.velocity.x *= 0.9;
              phys.velocity.z *= 0.9;
            }
          });
        }
        renderer.render(scene, camera);
      };
      animate();

      // store cleanup for the effect return
      renderer._cleanup = () => {
        dom.removeEventListener('mousedown', onMouseDown);
        dom.removeEventListener('contextmenu', e => e.preventDefault());
        dom.removeEventListener('wheel', onWheel);
        window.removeEventListener('mouseup',   onMouseUp);
        window.removeEventListener('mousemove', onMouseMove);
        cancelAnimationFrame(animFrameRef.current);
        renderer.dispose();
        if (container.contains(dom)) container.removeChild(dom);
      };
    }; // end tryInit

    // Try immediately (works if container already has size)
    tryInit(container.clientWidth, container.clientHeight);

    // Also watch via ResizeObserver — fires once the modal finishes animating
    // and the container gets its real layout dimensions
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      tryInit(width, height);
      // Keep renderer in sync with container size after init
      if (initDoneRef.current && rendererRef.current && cameraRef.current) {
        cameraRef.current.aspect = width / height;
        cameraRef.current.updateProjectionMatrix();
        rendererRef.current.setSize(width, height);
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      rendererRef.current?._cleanup?.();
      initDoneRef.current = false;
    };
  }, [applyOrbit, raycastObjects]);

  // Grid visibility
  useEffect(() => {
    const g = sceneRef.current?.children.find(c => c instanceof THREE.GridHelper);
    if (g) g.visible = showGrid;
  }, [showGrid]);

  // ── Register any Object3D into the sim ─────────────────────────────────────
  const registerObject = useCallback((root, type, colorHex) => {
    root.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
    sceneRef.current?.add(root);
    const id = `obj_${Date.now()}_${Math.random().toString(36).slice(2,6)}`;
    meshMapRef.current.set(id, root);
    physicsRef.current.set(id, { velocity: { x:0, y:0, z:0 }, useGravity: true, mass: 1 });
    setSimulatedObjects(prev => [...prev, { id, type, colorHex }]);
    return id;
  }, []);

  // ── Add primitive ──────────────────────────────────────────────────────────
  const addObject = useCallback((type = 'cube') => {
    if (!sceneRef.current) return;
    setShowDropdown(false);
    const color = new THREE.Color().setHSL(Math.random(), 0.8, 0.6);
    let geo;
    if      (type === 'sphere')   geo = new THREE.SphereGeometry(1.2, 32, 32);
    else if (type === 'cylinder') geo = new THREE.CylinderGeometry(1, 1, 2.5, 32);
    else                          geo = new THREE.BoxGeometry(2.2, 2.2, 2.2);
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      color, metalness: 0.3, roughness: 0.5, emissive: color, emissiveIntensity: 0.1,
    }));
    mesh.position.set((Math.random() - 0.5) * 16, 8 + Math.random() * 5, (Math.random() - 0.5) * 16);
    registerObject(mesh, type, color.getHexString());
  }, [registerObject]);

  // ── Import .glb / .gltf / .obj ─────────────────────────────────────────────
  const handleFileImport = useCallback(e => {
    const file = e.target.files?.[0];
    if (!file || !sceneRef.current) return;
    e.target.value = '';
    const ext = file.name.split('.').pop().toLowerCase();
    const url = URL.createObjectURL(file);
    setImportStatus('loading');
    setImportMsg(`Loading ${file.name}…`);

    const onLoaded = root => {
      // Auto-scale to fit a ~10 unit box
      const box  = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const max  = Math.max(size.x, size.y, size.z);
      if (max > 0) root.scale.setScalar(10 / max);
      // Centre and sit on ground
      box.setFromObject(root);
      const ctr = box.getCenter(new THREE.Vector3());
      root.position.sub(ctr);
      box.setFromObject(root);
      root.position.y -= box.min.y - 1;
      root.position.x += (Math.random() - 0.5) * 10;
      root.position.z += (Math.random() - 0.5) * 10;
      URL.revokeObjectURL(url);
      const hex = new THREE.Color().setHSL(Math.random(), 0.7, 0.6).getHexString();
      registerObject(root, ext.toUpperCase(), hex);
      setImportStatus('ok');
      setImportMsg(`✓ ${file.name}`);
      setTimeout(() => setImportStatus(null), 3000);
    };
    const onError = err => {
      console.error(err);
      URL.revokeObjectURL(url);
      setImportStatus('error');
      setImportMsg(`✗ Failed: ${file.name}`);
      setTimeout(() => setImportStatus(null), 4000);
    };

    if (ext === 'glb' || ext === 'gltf') new GLTFLoader().load(url, g => onLoaded(g.scene), undefined, onError);
    else if (ext === 'obj')               new OBJLoader().load(url, onLoaded, undefined, onError);
    else {
      URL.revokeObjectURL(url);
      setImportStatus('error');
      setImportMsg(`Unsupported: .${ext} — use .glb .gltf .obj`);
      setTimeout(() => setImportStatus(null), 4000);
    }
  }, [registerObject]);

  // ── Remove ─────────────────────────────────────────────────────────────────
  const removeObject = useCallback(id => {
    const obj = meshMapRef.current.get(id);
    if (obj && sceneRef.current) {
      sceneRef.current.remove(obj);
      obj.traverse(c => {
        if (!c.isMesh) return;
        c.geometry?.dispose();
        (Array.isArray(c.material) ? c.material : [c.material]).forEach(m => m?.dispose());
      });
      meshMapRef.current.delete(id);
    }
    physicsRef.current.delete(id);
    setSimulatedObjects(p => p.filter(o => o.id !== id));
    setSelectedId(cur => cur === id ? null : cur);
  }, []);

  // ── Reset ──────────────────────────────────────────────────────────────────
  const resetSimulation = useCallback(() => {
    [...meshMapRef.current.keys()].forEach(removeObject);
    setIsRunning(false);
    orbitRef.current = { theta: 0.8, phi: 0.9, radius: 35 };
    applyOrbit();
  }, [removeObject, applyOrbit]);

  const updateVelocity = useCallback((id, axis, val) => {
    const p = physicsRef.current.get(id);
    if (p) { p.velocity[axis] = val; setSimulatedObjects(s => [...s]); }
  }, []);

  const applyImpulse = useCallback((id, f) => {
    const p = physicsRef.current.get(id);
    if (!p) return;
    p.velocity.x += f.x; p.velocity.y += f.y; p.velocity.z += f.z;
    setSimulatedObjects(s => [...s]);
  }, []);

  const selectedPhys = selectedId ? physicsRef.current.get(selectedId) : null;

  return (
    <div className="w-full h-full flex flex-col bg-slate-950 select-none">
      <input ref={fileInputRef} type="file" accept=".glb,.gltf,.obj" className="hidden" onChange={handleFileImport} />

      {/* Toolbar */}
      <div className="flex-shrink-0 bg-slate-900/80 border-b border-slate-800 px-3 py-2 flex flex-wrap gap-2 items-center">
        <button onClick={() => setIsRunning(r => !r)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest transition-all ${
            isRunning ? 'bg-rose-600 hover:bg-rose-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'
          }`}>
          {isRunning ? <Pause size={13} /> : <Play size={13} />}
          {isRunning ? 'Pause' : 'Run'}
        </button>

        <button onClick={resetSimulation}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest bg-slate-800 hover:bg-slate-700 text-slate-300 transition-all">
          <RotateCcw size={13} /> Reset
        </button>

        <div className="relative">
          <button onClick={e => { e.stopPropagation(); setShowDropdown(d => !d); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest bg-indigo-600 hover:bg-indigo-500 text-white transition-all">
            <Plus size={13} /> Add
          </button>
          {showDropdown && (
            <div className="absolute top-full left-0 mt-1 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden shadow-2xl z-50 min-w-[120px]">
              {['cube','sphere','cylinder'].map(t => (
                <button key={t} onClick={e => { e.stopPropagation(); addObject(t); }}
                  className="w-full text-left px-4 py-2.5 text-[11px] font-bold uppercase tracking-widest text-slate-300 hover:bg-indigo-600 hover:text-white transition-colors capitalize">
                  {t}
                </button>
              ))}
            </div>
          )}
        </div>

        <button onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest bg-cyan-700 hover:bg-cyan-600 text-white transition-all"
          title="Import .glb, .gltf or .obj">
          <Upload size={13} /> Import
        </button>

        <button onClick={() => setShowGrid(g => !g)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-widest transition-all ${
            showGrid ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'bg-slate-800 text-slate-500'
          }`}>
          {showGrid ? <Eye size={13} /> : <EyeOff size={13} />} Grid
        </button>

        <div className="flex items-center gap-2 ml-auto">
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Speed</span>
          <input type="range" min="0.1" max="5" step="0.1" value={timeScale}
            onChange={e => setTimeScale(parseFloat(e.target.value))}
            className="w-20 h-1 accent-indigo-500" />
          <span className="text-[10px] font-mono text-slate-400 w-6">{timeScale.toFixed(1)}×</span>
        </div>
      </div>

      {/* 3-D Viewport */}
      <div ref={containerRef}
        className="flex-1 relative"
        style={{ cursor: interactMode === 'drag' ? 'move' : 'grab' }}
        onClick={() => setShowDropdown(false)}
      >
        <div className="absolute top-3 left-3 z-10 pointer-events-none">
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border backdrop-blur-sm ${
            interactMode === 'drag'
              ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
              : 'bg-slate-900/60 border-white/5 text-slate-500'
          }`}>
            <Move size={9} />
            {interactMode === 'drag' ? 'Dragging' : 'Orbit'}
          </div>
        </div>
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <div className="bg-slate-900/60 backdrop-blur-sm border border-white/5 rounded-full px-3 py-1 text-[9px] font-black uppercase tracking-widest text-slate-500">
            Click object to drag • Drag empty to orbit • Scroll zoom
          </div>
        </div>
        {importStatus && (
          <div className={`absolute top-3 right-3 z-20 flex items-center gap-2 px-3 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest border backdrop-blur-sm ${
            importStatus === 'loading' ? 'bg-slate-800/80 border-slate-700 text-slate-300' :
            importStatus === 'ok'      ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' :
                                         'bg-rose-500/20 border-rose-500/40 text-rose-400'
          }`}>
            {importStatus === 'loading' && <div className="w-3 h-3 rounded-full border-2 border-t-transparent border-slate-400 animate-spin" />}
            {importMsg}
          </div>
        )}
      </div>

      {/* Object list */}
      <div className="flex-shrink-0 bg-slate-900/60 border-t border-slate-800 px-3 py-2 max-h-[160px] overflow-y-auto">
        <div className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1.5">
          Scene — {simulatedObjects.length} object{simulatedObjects.length !== 1 ? 's' : ''}
        </div>
        {simulatedObjects.length === 0 && (
          <div className="text-[10px] text-slate-600 italic py-2 text-center">No objects — use Add or Import above</div>
        )}
        <div className="space-y-1">
          {simulatedObjects.map(obj => (
            <div key={obj.id}
              onClick={() => setSelectedId(id => id === obj.id ? null : obj.id)}
              className={`flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                selectedId === obj.id
                  ? 'bg-indigo-600/30 border border-indigo-500/40'
                  : 'bg-slate-800/50 hover:bg-slate-800 border border-transparent'
              }`}>
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: `#${obj.colorHex}` }} />
                <span className="text-[10px] font-bold uppercase tracking-wide text-slate-300 truncate">
                  {obj.type} <span className="text-slate-600">#{obj.id.slice(-4)}</span>
                </span>
              </div>
              <button onClick={e => { e.stopPropagation(); removeObject(obj.id); }}
                className="p-1 text-slate-600 hover:text-rose-400 transition-colors rounded">
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Properties panel */}
      {selectedId && selectedPhys && (
        <div className="flex-shrink-0 bg-slate-900/80 border-t border-indigo-500/20 px-3 py-2">
          <div className="text-[10px] font-black uppercase tracking-widest text-indigo-400 mb-2">
            Velocity — {simulatedObjects.find(o => o.id === selectedId)?.type}
          </div>
          <div className="grid grid-cols-3 gap-2 mb-2">
            {['x','y','z'].map(axis => (
              <div key={axis}>
                <label className="text-[9px] font-black uppercase text-slate-500 block mb-1">V.{axis.toUpperCase()}</label>
                <input type="number" step="0.5"
                  value={selectedPhys.velocity[axis].toFixed(2)}
                  onChange={e => updateVelocity(selectedId, axis, parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-indigo-500" />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => applyImpulse(selectedId, { x:0, y:12, z:0 })}
              className="flex-1 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 text-[10px] font-black uppercase tracking-widest text-indigo-400 border border-indigo-500/30 transition-all">
              ↑ Launch
            </button>
            <button onClick={() => applyImpulse(selectedId, { x:(Math.random()-0.5)*14, y:8, z:(Math.random()-0.5)*14 })}
              className="flex-1 py-1.5 rounded-lg bg-slate-700/50 hover:bg-slate-700 text-[10px] font-black uppercase tracking-widest text-slate-400 border border-slate-600/30 transition-all">
              ⟳ Scatter
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default MentalMatrixSimulator;