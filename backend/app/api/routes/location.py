from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.config import settings
from app.models.location import GeocodingMetadata, HouseModelMetadata, HouseModelRequest, TileSelection
from app.services.location.geocoding_service import GeocodingService, get_geocoding_service
from app.services.location.google_3d_tiles_service import Google3DTilesService, get_google_3d_tiles_service

router = APIRouter()


@router.post(
    "/location/house-model",
    responses={
        200: {
            "content": {"model/gltf-binary": {}},
            "description": (
                "Binary GLB of the geometry around the requested anchor. "
                "Structured metadata is JSON-encoded in the Roofee-Metadata response header."
            ),
        }
    },
)
def get_house_model(
    request: HouseModelRequest,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    tiles_service: Google3DTilesService = Depends(get_google_3d_tiles_service),
) -> Response:
    _require_google_api_key()
    geocoding_metadata, latitude, longitude = _resolve_anchor(request, geocoding_service)
    glb_bytes, selected_tile, candidate_count, copyright_text = tiles_service.fetch_house_glb(
        latitude=latitude,
        longitude=longitude,
        radius_m=request.radius_m,
    )
    metadata = HouseModelMetadata(
        anchor_latitude=latitude,
        anchor_longitude=longitude,
        radius_m=request.radius_m,
        query_height_m=getattr(tiles_service, "query_height_m", None),
        geocoding=geocoding_metadata,
        tile=TileSelection(
            uri=selected_tile.uri,
            geometric_error=selected_tile.geometric_error,
            bounding_sphere_radius_m=selected_tile.bounding_sphere_radius_m,
            center_distance_m=selected_tile.distance_m,
            transform=list(selected_tile.transform),
        ),
        candidate_tile_count=candidate_count,
        copyright=copyright_text,
        glb_size_bytes=len(glb_bytes),
    )
    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Roofee-Metadata": json.dumps(metadata.model_dump(mode="json"), ensure_ascii=True)},
    )


def _resolve_anchor(
    request: HouseModelRequest,
    geocoding_service: GeocodingService,
) -> tuple[GeocodingMetadata, float, float]:
    if request.latitude is not None and request.longitude is not None:
        return (
            GeocodingMetadata(source="request"),
            request.latitude,
            request.longitude,
        )
    if request.address is None:
        raise HTTPException(status_code=400, detail="Provide either address or latitude and longitude.")
    return geocoding_service.geocode(request.address)


def _require_google_api_key() -> None:
    if not (settings.google_api_key or settings.google_maps_api_key):
        raise HTTPException(status_code=503, detail="Google API key is not configured.")
