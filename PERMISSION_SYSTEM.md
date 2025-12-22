# Permission Control System

## Overview

The permission control system provides granular control over AI system access in Controller Mode. Users can enable/disable access to camera, microphone, file system, and network resources.

## Four Permission Types

### 1. **Camera Access** 🎥
- **Risk Level**: Medium
- **Purpose**: AI captures and processes visual input from webcam
- **Backend Enforcement**: Checked in `ControllerRuntime.start_camera()`
- **Status**: Returns `False` if permission denied

### 2. **Microphone Access** 🎤
- **Risk Level**: Medium
- **Purpose**: AI listens to and processes audio from microphone
- **Backend Enforcement**: Checked in `ControllerRuntime.start_microphone()`
- **Status**: Returns `False` if permission denied

### 3. **File System Access** 📁
- **Risk Level**: High
- **Purpose**: AI can read and write files on the computer
- **Backend Enforcement**: Checked via `runtime.can_access_filesystem()`
- **Usage**: Can be checked before file operations

### 4. **Network Access** 🌐
- **Risk Level**: High
- **Purpose**: AI can make network requests and connections
- **Backend Enforcement**: Checked via `runtime.can_access_network()`
- **Usage**: Can be checked before network operations

## Frontend Implementation

### Permission State Management

```javascript
const [permissions, setPermissions] = useState({
  camera: true,
  microphone: true,
  filesystem: true,
  network: true
});
```

### Permission UI

- **Toggles**: Individual checkbox for each permission
- **Visual Feedback**: 
  - Enabled: Red/Yellow border with risk badge
  - Disabled: Greyed out with "DISABLED" badge
- **Validation**: Requires at least one permission enabled to activate
- **Status Badge**: Shows "X/4 permissions enabled" in real-time

### Permission Summary

Before activation, users see a clear summary showing:
- ✅ Checkmark for enabled permissions
- ❌ Cross for disabled permissions
- Warning if all permissions are disabled

## Backend Implementation

### ControllerRuntime Permission Storage

```python
class ControllerRuntime:
    def __init__(self, ...):
        self.permission_settings = {}  # Full permission dict
        self.enabled_permissions = {
            'camera': False,
            'microphone': False,
            'filesystem': False,
            'network': False
        }
```

### Permission Enforcement

#### Device Access
```python
def start_camera(self, ...):
    if not self.enabled_permissions.get('camera', False):
        log.warning("❌ Camera access DENIED by permission settings")
        return False
    # ... proceed with camera initialization

def start_microphone(self, ...):
    if not self.enabled_permissions.get('microphone', False):
        log.warning("❌ Microphone access DENIED by permission settings")
        return False
    # ... proceed with microphone initialization
```

#### Multimodal Learning Initialization
```python
def start_multimodal_learning(self, vision: bool = True, audio: bool = True):
    # Vision only starts if:
    # 1. Vision is requested AND
    # 2. Camera permission is enabled
    if vision and self.enabled_permissions.get('camera', False):
        self.start_camera()
    
    # Audio only starts if:
    # 1. Audio is requested AND
    # 2. Microphone permission is enabled
    if audio and self.enabled_permissions.get('microphone', False):
        self.start_microphone()
```

### Permission Check Methods

```python
def can_access_filesystem(self) -> bool:
    """Check if filesystem access is permitted"""
    return self.enabled_permissions.get('filesystem', False)

def can_access_network(self) -> bool:
    """Check if network access is permitted"""
    return self.enabled_permissions.get('network', False)

def can_use_camera(self) -> bool:
    """Check if camera access is permitted"""
    return self.enabled_permissions.get('camera', False)

def can_use_microphone(self) -> bool:
    """Check if microphone access is permitted"""
    return self.enabled_permissions.get('microphone', False)
```

## API Endpoints

### POST `/api/controller/activate`

**Request:**
```json
{
  "agent_id": "demo",
  "permissions": ["Camera Access", "Microphone Access", ...],
  "permissionSettings": {
    "camera": true,
    "microphone": true,
    "filesystem": false,
    "network": false
  },
  "devices": {
    "camera": 0,
    "microphone": 0
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Controller mode activated for demo",
  "permissions": ["Camera Access", "Microphone Access"],
  "settings": {
    "camera": true,
    "microphone": true,
    "filesystem": false,
    "network": false
  }
}
```

**Backend Actions:**
1. Stores `permissionSettings` in ControllerRuntime instance
2. Creates `enabled_permissions` dict from settings
3. Starts multimodal learning with camera/microphone only if permissions granted
4. Logs permission restrictions (e.g., "🔒 File system access DISABLED")

### GET `/api/controller/status?agent_id=demo`

**Response:**
```json
{
  "agent_id": "demo",
  "active": true,
  "permissions": {
    "camera": true,
    "microphone": true,
    "filesystem": false,
    "network": false
  },
  "permissions_count": 2,
  "camera_active": true,
  "microphone_active": false,
  "stats": {
    "frames_processed": 150,
    "audio_chunks_processed": 0,
    "learning_events": 5,
    "files_processed": 0
  }
}
```

## Activity Monitor Display

The real-time activity monitor shows:

### Active Permissions Section
- Shows which permissions are currently active (✅) or disabled (❌)
- Counts active permissions: "2/4 permissions enabled"
- Color-coded: Green checkmarks for enabled, gray crosses for disabled

### Device Status Indicators
- Camera: Only shows as active if BOTH camera_active AND camera permission enabled
- Microphone: Only shows as active if BOTH microphone_active AND microphone permission enabled
- File Access: Shows active if filesystem permission enabled
- Network: Shows active if network permission enabled

### Real-time Updates
- Status polled every 2 seconds
- Permissions reflect current runtime state
- Statistics updated in real-time

## Usage Examples

### Checking Permissions Before Operations

```python
# In agent code or middleware
runtime = agent_runtimes[agent_id]

# Before file operations
if runtime.can_access_filesystem():
    # Proceed with file read/write
    pass
else:
    runtime.log_permission_denied("file system")

# Before network operations
if runtime.can_access_network():
    # Proceed with network request
    pass
else:
    runtime.log_permission_denied("network")

# Camera access automatically handled by start_camera()
# Microphone access automatically handled by start_microphone()
```

### Frontend: Viewing Active Permissions

```javascript
// In ControllerActivityMonitor
{status.permissions && (
  <div>
    <h4>🔐 Active Permissions ({status.permissions_count}/4)</h4>
    <div>
      {status.permissions.camera && <span>✅ Camera</span>}
      {status.permissions.microphone && <span>✅ Microphone</span>}
      {status.permissions.filesystem && <span>✅ File System</span>}
      {status.permissions.network && <span>✅ Network</span>}
    </div>
  </div>
)}
```

## Security Considerations

1. **Device Access**: Camera and microphone can only be started if permissions are granted
2. **Multimodal Learning**: Only activates sensors that have permissions enabled
3. **File System**: Agents should check `can_access_filesystem()` before file operations
4. **Network**: Agents should check `can_access_network()` before network requests
5. **Logging**: All permission denials are logged with timestamps
6. **Runtime Control**: Permissions are stored per-runtime instance and cannot be changed while active

## Future Enhancements

- Granular file path restrictions (sandbox certain directories)
- Network domain whitelist/blacklist
- Per-operation permission prompts
- Permission audit logs with timestamps
- Time-based permission expiration
- Permission history and rollback

## Files Modified

- `/py_backend/main.py`: Permission storage in activate endpoint, status endpoint updates
- `/py_backend/utils/dw_controller.py`: Permission enforcement in device access, multimodal learning, permission check methods
- `/dw_agent/electron/react-app/src/ControllerSafety.jsx`: Permission toggles, summary display, activity monitor updates
