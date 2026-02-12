"""
API v1 Router
Aggregates all API endpoints.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, files, users

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

# Future endpoints
# api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
