# Changelog

## [2.1.0] - 2025-07-17

### Added
- Complete Divine World Minecraft mod REST API integration with 13 new endpoints.
- New `start_backend.sh` script for intelligent startup and dependency checking.
- Automated API test suite `test_divine_api.sh`.
- Enhanced `EnhancedAgentSpawner` with UltimMC support.
- Comprehensive documentation for REST API, God entities, and NPC management.

### Changed
- Updated root endpoint (`GET /`) to provide full API documentation in JSON format.
- Improved configuration auto-detection for Minecraft JAR files.
- Refactored `AgentSpawner` to support graceful fallback when UltimMC is unavailable.

### Fixed
- Resolved pathing issues in standalone agent builds.
- Fixed WebSocket protocol negotiation for high-performance binary streaming.

## [2.0.0] - 2024-12-28

### Added
- Mental Matrix 3D simulation environment.
- Granular permission system for AI system access.
- Support for standalone agent packaging via PyInstaller.
- Binary WebSocket protocol for low-latency perception/action flow.

---

*Note: For detailed commit history, please refer to the git logs.*
