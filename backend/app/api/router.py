from fastapi import APIRouter

from app.api.routes import data, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
