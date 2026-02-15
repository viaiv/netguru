"""
API v1 Router
Aggregates all API endpoints.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    admin_usage,
    auth,
    billing,
    chat,
    files,
    memories,
    plans,
    settings,
    topology,
    users,
    ws_chat,
)

api_router = APIRouter()

# Health check for API
@api_router.get("/ping", tags=["Health"])
async def ping():
    """Simple ping endpoint to verify API is responding"""
    return {"message": "pong", "api_version": "v1"}

# Include endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(memories.router, prefix="/memories", tags=["Memories"])
api_router.include_router(ws_chat.router, tags=["WebSocket Chat"])

api_router.include_router(plans.router, prefix="/plans", tags=["Plans"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(admin_usage.router, prefix="/admin", tags=["Admin Usage"])
api_router.include_router(settings.router, prefix="/admin", tags=["Admin Settings"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
api_router.include_router(topology.router, prefix="/topology", tags=["Topology"])

# Future endpoints
# api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
