from fastapi import APIRouter

from app.api.routes import catalog, health, house_assets, location, proposals, recommendations, roof

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(house_assets.router, tags=["house-data"])
api_router.include_router(location.router, tags=["location"])
api_router.include_router(proposals.router, tags=["proposals"])
api_router.include_router(recommendations.router, tags=["recommendations"])
api_router.include_router(roof.router, tags=["roof"])
