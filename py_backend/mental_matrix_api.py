"""
Mental Matrix API Routes
========================
FastAPI routes for the Mental Matrix simulation service.
This module re-exports the API from world_model.py for convenience.
All implementation is now in ai_core/world_model.py
"""

from ai_core.world_model import (
    get_mental_matrix_router,
    register_mental_matrix_api,
    get_mental_matrix_service,
)

# For backward compatibility - use the world_model router
mental_matrix_router = get_mental_matrix_router()

__all__ = [
    'mental_matrix_router',
    'register_mental_matrix_api',
    'get_mental_matrix_service',
]
