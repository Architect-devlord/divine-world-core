// src/components/MentalMatrixSimulator.jsx
import React, { useState, useEffect, useRef } from 'react';
import * as THREE from 'three';
import { Plus, Trash2, Play, Pause, RotateCcw, Copy, Code2, Eye, EyeOff } from 'lucide-react';

function MentalMatrixSimulator({ agentId, onSimulationEvent }) {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const controlsRef = useRef(null);
  const objectsRef = useRef(new Map());
  const animationFrameRef = useRef(null);

  const [isRunning, setIsRunning] = useState(false);
  const [simulatedObjects, setSimulatedObjects] = useState([]);
  const [selectedObject, setSelectedObject] = useState(null);
  const [showGrid, setShowGrid] = useState(true);
  const [showPhysics, setShowPhysics] = useState(true);
  const [timeScale, setTimeScale] = useState(1.0);
  const [selectedTool, setSelectedTool] = useState('select');
  const [physicsData, setPhysicsData] = useState({});

  // Initialize Three.js scene
  useEffect(() => {
    if (!containerRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);
    scene.fog = new THREE.Fog(0x0f172a, 100, 500);
    sceneRef.current = scene;

    // Camera setup
    const camera = new THREE.PerspectiveCamera(
      75,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      10000
    );
    camera.position.set(20, 20, 20);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // Renderer setup
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(50, 50, 50);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    directionalLight.shadow.camera.far = 200;
    directionalLight.shadow.camera.left = -100;
    directionalLight.shadow.camera.right = 100;
    directionalLight.shadow.camera.top = 100;
    directionalLight.shadow.camera.bottom = -100;
    scene.add(directionalLight);

    // Grid
    const gridHelper = new THREE.GridHelper(100, 20, 0x1e40af, 0x334155);
    gridHelper.visible = showGrid;
    scene.add(gridHelper);

    // Axes helper
    const axesHelper = new THREE.AxesHelper(10);
    scene.add(axesHelper);

    // Basic ground plane
    const groundGeometry = new THREE.PlaneGeometry(100, 100);
    const groundMaterial = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      metalness: 0.1,
      roughness: 0.9,
    });
    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // Simple orbit controls
    const controls = {
      autoRotate: false,
      rotateSpeed: 0.005,
      zoomSpeed: 0.1,
      panSpeed: 0.5,
    };
    controlsRef.current = controls;

    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };

    renderer.domElement.addEventListener('mousedown', (e) => {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    renderer.domElement.addEventListener('mousemove', (e) => {
      if (isDragging) {
        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;

        if (e.buttons === 1) {
          // Rotate
          const rotation = new THREE.Quaternion();
          rotation.setFromAxisAngle(new THREE.Vector3(0, 1, 0), deltaX * controls.rotateSpeed);
          camera.position.applyQuaternion(rotation);

          rotation.setFromAxisAngle(
            camera.position.clone().cross(new THREE.Vector3(0, 1, 0)).normalize(),
            deltaY * controls.rotateSpeed
          );
          camera.position.applyQuaternion(rotation);
          camera.lookAt(0, 0, 0);
        } else if (e.buttons === 2) {
          // Pan
          const panVector = new THREE.Vector3(-deltaX * controls.panSpeed, deltaY * controls.panSpeed, 0);
          camera.position.add(panVector);
        }

        previousMousePosition = { x: e.clientX, y: e.clientY };
      }
    });

    renderer.domElement.addEventListener('mouseup', () => {
      isDragging = false;
    });

    renderer.domElement.addEventListener('wheel', (e) => {
      e.preventDefault();
      const direction = camera.position.clone().normalize();
      const distance = camera.position.length();
      const newDistance = distance + e.deltaY * controls.zoomSpeed;
      camera.position.copy(direction.multiplyScalar(Math.max(5, newDistance)));
      camera.lookAt(0, 0, 0);
    }, { passive: false });

    // Animation loop
    const animate = () => {
      animationFrameRef.current = requestAnimationFrame(animate);

      // Update physics if running
      if (isRunning) {
        objectsRef.current.forEach((mesh, objId) => {
          const obj = simulatedObjects.find(o => o.id === objId);
          if (obj && obj.physics) {
            // Simple gravity and velocity
            if (obj.physics.velocity) {
              mesh.position.x += obj.physics.velocity.x * timeScale * 0.016;
              mesh.position.y += obj.physics.velocity.y * timeScale * 0.016;
              mesh.position.z += obj.physics.velocity.z * timeScale * 0.016;

              // Gravity
              if (obj.physics.useGravity) {
                obj.physics.velocity.y -= 0.1 * timeScale * 0.016;
              }

              // Ground collision
              if (mesh.position.y < 1 && obj.physics.useGravity) {
                mesh.position.y = 1;
                obj.physics.velocity.y *= -0.6; // Bounce
              }
            }

            // Update physics visualization
            if (obj.physics.showVelocityVector && mesh.userData.velocityLine) {
              const endPoint = new THREE.Vector3(
                mesh.position.x + (obj.physics.velocity?.x || 0) * 2,
                mesh.position.y + (obj.physics.velocity?.y || 0) * 2,
                mesh.position.z + (obj.physics.velocity?.z || 0) * 2
              );
              mesh.userData.velocityLine.geometry.setFromPoints([
                mesh.position.clone(),
                endPoint,
              ]);
            }
          }
        });
      }

      renderer.render(scene, camera);
    };

    animate();

    // Handle window resize
    const handleResize = () => {
      if (containerRef.current) {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
      }
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      renderer.dispose();
      if (containerRef.current?.contains(renderer.domElement)) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update grid visibility
  useEffect(() => {
    if (sceneRef.current) {
      const gridHelper = sceneRef.current.children.find(c => c instanceof THREE.GridHelper);
      if (gridHelper) {
        gridHelper.visible = showGrid;
      }
    }
  }, [showGrid]);

  // Add object to simulation
  const addObject = (type = 'cube') => {
    let geometry, material, mesh;
    const color = Math.random() * 0xffffff;

    switch (type) {
      case 'cube':
        geometry = new THREE.BoxGeometry(2, 2, 2);
        break;
      case 'sphere':
        geometry = new THREE.SphereGeometry(1, 32, 32);
        break;
      case 'cylinder':
        geometry = new THREE.CylinderGeometry(1, 1, 2, 32);
        break;
      default:
        geometry = new THREE.BoxGeometry(2, 2, 2);
    }

    material = new THREE.MeshStandardMaterial({
      color,
      metalness: 0.5,
      roughness: 0.7,
    });

    mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.position.set(Math.random() * 20 - 10, 5, Math.random() * 20 - 10);

    const objId = `obj_${Date.now()}`;
    const newObj = {
      id: objId,
      type,
      position: { ...mesh.position },
      physics: {
        velocity: { x: 0, y: 0, z: 0 },
        useGravity: true,
        mass: 1,
        showVelocityVector: false,
      },
      color,
    };

    sceneRef.current.add(mesh);
    objectsRef.current.set(objId, mesh);
    setSimulatedObjects(prev => [...prev, newObj]);

    return objId;
  };

  // Remove object from simulation
  const removeObject = (objId) => {
    const mesh = objectsRef.current.get(objId);
    if (mesh) {
      sceneRef.current.remove(mesh);
      mesh.geometry.dispose();
      mesh.material.dispose();
      objectsRef.current.delete(objId);
    }
    setSimulatedObjects(prev => prev.filter(o => o.id !== objId));
    if (selectedObject?.id === objId) {
      setSelectedObject(null);
    }
  };

  // Reset simulation
  const resetSimulation = () => {
    simulatedObjects.forEach(obj => removeObject(obj.id));
    setIsRunning(false);
  };

  // Apply impulse to object
  const applyImpulse = (objId, force) => {
    const obj = simulatedObjects.find(o => o.id === objId);
    if (obj && obj.physics) {
      obj.physics.velocity.x += force.x;
      obj.physics.velocity.y += force.y;
      obj.physics.velocity.z += force.z;
      setSimulatedObjects([...simulatedObjects]);
    }
  };

  return (
    <div className="w-full h-full flex flex-col bg-slate-950">
      {/* Toolbar */}
      <div className="bg-slate-900 border-b border-slate-800 p-3 flex flex-wrap gap-2 items-center">
        <button
          onClick={() => setIsRunning(!isRunning)}
          className={`btn btn-sm gap-2 ${isRunning ? 'btn-error' : 'btn-success'}`}
        >
          {isRunning ? <Pause size={16} /> : <Play size={16} />}
          {isRunning ? 'Running' : 'Paused'}
        </button>

        <button
          onClick={resetSimulation}
          className="btn btn-sm btn-outline gap-2"
        >
          <RotateCcw size={16} />
          Reset
        </button>

        <div className="divider divider-horizontal m-0" />

        <div className="dropdown dropdown-bottom">
          <button className="btn btn-sm btn-primary gap-2">
            <Plus size={16} />
            Add Object
          </button>
          <ul className="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-52">
            <li><a onClick={() => addObject('cube')}>Cube</a></li>
            <li><a onClick={() => addObject('sphere')}>Sphere</a></li>
            <li><a onClick={() => addObject('cylinder')}>Cylinder</a></li>
          </ul>
        </div>

        <button
          onClick={() => setShowGrid(!showGrid)}
          className={`btn btn-sm ${showGrid ? 'btn-primary' : 'btn-ghost'}`}
        >
          {showGrid ? <Eye size={16} /> : <EyeOff size={16} />}
          Grid
        </button>

        <button
          onClick={() => setShowPhysics(!showPhysics)}
          className={`btn btn-sm ${showPhysics ? 'btn-primary' : 'btn-ghost'}`}
        >
          Physics
        </button>

        <div className="form-control">
          <label className="label">
            <span className="label-text text-xs">Time Scale</span>
          </label>
          <input
            type="range"
            min="0.1"
            max="5"
            step="0.1"
            value={timeScale}
            onChange={(e) => setTimeScale(parseFloat(e.target.value))}
            className="range range-xs range-primary w-24"
          />
          <span className="text-xs text-gray-400">{timeScale.toFixed(1)}x</span>
        </div>
      </div>

      {/* 3D Viewport */}
      <div ref={containerRef} className="flex-1 bg-gradient-to-b from-slate-950 to-slate-900 relative" />

      {/* Objects Panel */}
      <div className="bg-slate-900 border-t border-slate-800 p-3 max-h-[200px] overflow-y-auto">
        <div className="text-xs font-semibold text-gray-300 mb-2">
          Objects in Simulation ({simulatedObjects.length})
        </div>
        <div className="space-y-1">
          {simulatedObjects.map(obj => (
            <div
              key={obj.id}
              onClick={() => setSelectedObject(obj)}
              className={`flex items-center justify-between p-2 rounded cursor-pointer transition-colors ${
                selectedObject?.id === obj.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 hover:bg-slate-700 text-gray-300'
              }`}
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <div
                  className="w-3 h-3 rounded"
                  style={{ backgroundColor: `#${obj.color.toString(16).padStart(6, '0')}` }}
                />
                <span className="text-xs truncate">{obj.type} - {obj.id.slice(-4)}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeObject(obj.id);
                }}
                className="btn btn-xs btn-ghost"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Properties Panel for Selected Object */}
      {selectedObject && (
        <div className="bg-slate-900 border-t border-slate-800 p-3 max-h-[150px] overflow-y-auto">
          <div className="text-xs font-semibold text-gray-300 mb-2">
            Properties: {selectedObject.type}
          </div>
          <div className="space-y-2 text-xs text-gray-400">
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="label-text">Velocity X</label>
                <input
                  type="number"
                  step="0.1"
                  value={selectedObject.physics.velocity.x}
                  onChange={(e) => {
                    const updated = { ...selectedObject };
                    updated.physics.velocity.x = parseFloat(e.target.value);
                    setSelectedObject(updated);
                  }}
                  className="input input-xs input-bordered w-full"
                />
              </div>
              <div>
                <label className="label-text">Velocity Y</label>
                <input
                  type="number"
                  step="0.1"
                  value={selectedObject.physics.velocity.y}
                  onChange={(e) => {
                    const updated = { ...selectedObject };
                    updated.physics.velocity.y = parseFloat(e.target.value);
                    setSelectedObject(updated);
                  }}
                  className="input input-xs input-bordered w-full"
                />
              </div>
              <div>
                <label className="label-text">Velocity Z</label>
                <input
                  type="number"
                  step="0.1"
                  value={selectedObject.physics.velocity.z}
                  onChange={(e) => {
                    const updated = { ...selectedObject };
                    updated.physics.velocity.z = parseFloat(e.target.value);
                    setSelectedObject(updated);
                  }}
                  className="input input-xs input-bordered w-full"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default MentalMatrixSimulator;
