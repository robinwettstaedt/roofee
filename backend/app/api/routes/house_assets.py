from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.services.house_data_service import HouseDataService, get_house_data_service

router = APIRouter()


@router.get("/house-assets/{asset_id}/overhead.png")
def get_overhead_image(
    asset_id: str,
    house_data_service: HouseDataService = Depends(get_house_data_service),
) -> FileResponse:
    return FileResponse(
        house_data_service.overhead_image_path(asset_id),
        media_type="image/png",
    )


@router.get("/house-assets/{asset_id}/house.glb")
def get_house_model_asset(
    asset_id: str,
    house_data_service: HouseDataService = Depends(get_house_data_service),
) -> FileResponse:
    model_path = house_data_service.house_model_cache_path(asset_id)
    if not model_path.is_file():
        raise HTTPException(status_code=404, detail="House model not found.")
    return FileResponse(model_path, media_type="model/gltf-binary")


@router.get("/google-3d-tiles/{tile_path:path}")
def proxy_google_3d_tile(
    request: Request,
    tile_path: str,
    house_data_service: HouseDataService = Depends(get_house_data_service),
) -> Response:
    upstream_response = house_data_service.fetch_3d_tile(tile_path, request.query_params)
    content_type = upstream_response.headers.get("content-type", "application/octet-stream")

    if "json" in content_type or tile_path.endswith(".json"):
        return JSONResponse(
            house_data_service.rewrite_3d_tiles_json(upstream_response.json(), request.query_params),
            headers=_cache_headers(upstream_response),
        )

    return Response(
        content=upstream_response.content,
        media_type=content_type,
        headers=_cache_headers(upstream_response),
    )


def _cache_headers(response: object) -> dict[str, str]:
    headers = getattr(response, "headers", {})
    cache_control = headers.get("cache-control") if hasattr(headers, "get") else None
    return {"cache-control": cache_control} if cache_control else {}
