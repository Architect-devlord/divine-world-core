"""
Mental Matrix API Routes
========================
Thin re-export shim so that any code that does

    from py_backend.mental_matrix_routes import mental_matrix_router

continues to work without change after the implementation was moved
into ai_core/world_model.py.

All real logic lives in ai_core/world_model.py.
This file is a server-side module (main.py includes the router) and is
therefore listed in Config.AGENT_EXCLUDE_MODULES — it is NOT bundled into
packaged agent executables.

Usage (in main.py or a test):
    from py_backend.mental_matrix_routes import (
        mental_matrix_router,
        register_mental_matrix_api,
        get_mental_matrix_service,
    )
    app.include_router(mental_matrix_router)
"""

from ai_core.world_model import (
    get_mental_matrix_router,
    register_mental_matrix_api,
    get_mental_matrix_service,
)

# Materialise the router once at import time so callers can do a simple
# app.include_router(mental_matrix_router) without calling the factory.
mental_matrix_router = get_mental_matrix_router()

__all__ = [
    "mental_matrix_router",
    "register_mental_matrix_api",
    "get_mental_matrix_service",
]