from fastapi import APIRouter

from app.api.routes import catalog, data, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
