from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.services.house_data_service import HouseDataService
from app.services.location.google_3d_tiles_service import Google3DTilesService


class ModelAssetService:
    def load_or_fetch_model(
        self,
        *,
        asset_id: str,
        radius_m: float,
        house_data_service: HouseDataService,
        tiles_service: Google3DTilesService,
    ) -> bytes:
        model_path = house_data_service.house_model_cache_path(asset_id)
        if model_path.is_file():
            try:
                return model_path.read_bytes()
            except OSError as exc:
                raise HTTPException(status_code=422, detail="Cached house model could not be loaded.") from exc

        metadata = house_data_service.house_asset_metadata(asset_id)
        center = metadata.get("building_center")
        if not isinstance(center, dict):
            raise HTTPException(status_code=422, detail="House asset metadata has no building center.")
        try:
            latitude = float(center["latitude"])
            longitude = float(center["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="House asset metadata has invalid coordinates.") from exc

        glb_bytes, selected_tile, candidate_count, copyright_text = tiles_service.fetch_house_glb(
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
        )
        self._write_model_cache(
            model_path,
            glb_bytes,
            house_data_service.house_model_metadata_cache_path(asset_id),
            {
                "provider": "google_3d_tiles",
                "anchor_latitude": latitude,
                "anchor_longitude": longitude,
                "radius_m": radius_m,
                "tile_uri": selected_tile.uri,
                "tile_geometric_error": selected_tile.geometric_error,
                "candidate_tile_count": candidate_count,
                "copyright": copyright_text,
                "glb_size_bytes": len(glb_bytes),
            },
        )
        return glb_bytes

    def _write_model_cache(
        self,
        model_path: Path,
        glb_bytes: bytes,
        metadata_path: Path,
        metadata: dict[str, Any],
    ) -> None:
        try:
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_bytes(glb_bytes)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=502, detail="House model could not be cached.") from exc


def get_model_asset_service() -> ModelAssetService:
    return ModelAssetService()
