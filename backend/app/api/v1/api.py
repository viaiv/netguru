"""
API v1 Router
Aggregates all API endpoints.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, billing, chat, files, plans, settings, users, ws_chat

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
api_router.include_router(ws_chat.router, tags=["WebSocket Chat"])

api_router.include_router(plans.router, prefix="/plans", tags=["Plans"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(settings.router, prefix="/admin", tags=["Admin Settings"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])

# Future endpoints
# api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
