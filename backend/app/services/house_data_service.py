from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlencode, urljoin, urlparse

import httpx
import numpy as np
import tifffile
from fastapi import HTTPException
from PIL import Image

from app.core.config import settings
from app.models.recommendation import (
    Google3DTilesData,
    GoogleSolarDate,
    HouseData,
    LatLng,
    LatLngBox,
    SolarBuildingData,
    SolarRoofSegment,
)


GOOGLE_SOLAR_BUILDING_INSIGHTS_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
GOOGLE_SOLAR_DATA_LAYERS_URL = "https://solar.googleapis.com/v1/dataLayers:get"
GOOGLE_3D_TILES_BASE_URL = "https://tile.googleapis.com/v1/3dtiles/"


class HouseDataService:
    def __init__(
        self,
        api_key: str | None,
        cache_dir: Path,
        timeout_seconds: float,
        solar_radius_meters: float,
        solar_pixel_size_meters: float,
    ) -> None:
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.solar_radius_meters = solar_radius_meters
        self.solar_pixel_size_meters = solar_pixel_size_meters

    def fetch_house_data(self, latitude: float, longitude: float) -> HouseData:
        self._require_api_key()

        building_payload = self._get_json(
            GOOGLE_SOLAR_BUILDING_INSIGHTS_URL,
            params={
                "location.latitude": latitude,
                "location.longitude": longitude,
                "requiredQuality": "HIGH",
                "exactQualityRequired": "false",
                "key": self.api_key,
            },
        )
        solar_building = self._parse_building(building_payload, fallback_latitude=latitude, fallback_longitude=longitude)

        data_layers_payload = self._get_json(
            GOOGLE_SOLAR_DATA_LAYERS_URL,
            params={
                "location.latitude": solar_building.center.latitude,
                "location.longitude": solar_building.center.longitude,
                "radiusMeters": self.solar_radius_meters,
                "view": "IMAGERY_LAYERS",
                "requiredQuality": "HIGH",
                "exactQualityRequired": "false",
                "pixelSizeMeters": self.solar_pixel_size_meters,
                "key": self.api_key,
            },
        )
        asset_id = self._asset_id(solar_building, data_layers_payload)
        overhead_image_url = f"/api/house-assets/{asset_id}/overhead.png"
        self._ensure_overhead_image(asset_id, data_layers_payload)
        self._write_asset_metadata(
            asset_id,
            {
                "provider": "google",
                "requested_location": {"latitude": latitude, "longitude": longitude},
                "building_center": solar_building.center.model_dump(mode="json"),
                "solar_radius_meters": self.solar_radius_meters,
                "solar_pixel_size_meters": self.solar_pixel_size_meters,
                "solar_building": solar_building.model_dump(mode="json"),
            },
        )

        return HouseData(
            status="fetched",
            provider="google",
            location=LatLng(latitude=latitude, longitude=longitude),
            solar_building=solar_building,
            overhead_image_url=overhead_image_url,
            tiles_3d=Google3DTilesData(
                root_url="/api/google-3d-tiles/root.json",
                origin=solar_building.center,
            ),
            warnings=[],
        )

    def overhead_image_path(self, asset_id: str) -> Path:
        if not asset_id or "/" in asset_id or "\\" in asset_id or ".." in asset_id:
            raise HTTPException(status_code=404, detail="House asset not found.")

        path = (self._resolved_cache_dir() / asset_id / "overhead.png").resolve()
        try:
            path.relative_to(self._resolved_cache_dir())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="House asset not found.") from exc

        if not path.is_file():
            raise HTTPException(status_code=404, detail="House asset not found.")
        return path

    def house_asset_metadata(self, asset_id: str) -> dict[str, Any]:
        path = self._safe_asset_path(asset_id, "metadata.json")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="House asset metadata not found.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="House asset metadata could not be loaded.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="House asset metadata is malformed.")
        return payload

    def house_model_cache_path(self, asset_id: str) -> Path:
        return self._safe_asset_path(asset_id, "house.glb")

    def house_model_metadata_cache_path(self, asset_id: str) -> Path:
        return self._safe_asset_path(asset_id, "house_model_metadata.json")

    def fetch_3d_tile(
        self,
        tile_path: str,
        query_params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        self._require_api_key()
        safe_tile_path = self._validate_tile_path(tile_path)
        upstream_params = self._upstream_tile_query_params(query_params or {})

        try:
            response = httpx.get(
                urljoin(GOOGLE_3D_TILES_BASE_URL, safe_tile_path),
                params={**upstream_params, "key": self.api_key},
                timeout=self.timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="Google 3D Tiles request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google 3D Tiles returned HTTP {exc.response.status_code}.",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Google 3D Tiles request failed.") from exc

        return response

    def rewrite_3d_tiles_json(
        self,
        payload: Any,
        inherited_query_params: Mapping[str, str] | None = None,
    ) -> Any:
        if isinstance(payload, dict):
            rewritten: dict[str, Any] = {}
            for key, value in payload.items():
                if key == "uri" and isinstance(value, str):
                    rewritten[key] = self._proxy_tile_uri(value, inherited_query_params or {})
                else:
                    rewritten[key] = self.rewrite_3d_tiles_json(value, inherited_query_params)
            return rewritten
        if isinstance(payload, list):
            return [self.rewrite_3d_tiles_json(item, inherited_query_params) for item in payload]
        return payload

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise HTTPException(status_code=503, detail="Google Maps API key is not configured.")

    def _get_json(self, url: str, params: dict[str, str | float]) -> dict[str, Any]:
        try:
            response = httpx.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="Google house data request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google house data returned HTTP {exc.response.status_code}.",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="Google house data request failed.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Google house data returned malformed data.")
        return payload

    def _ensure_overhead_image(self, asset_id: str, data_layers_payload: dict[str, Any]) -> None:
        png_path = self._resolved_cache_dir() / asset_id / "overhead.png"
        if png_path.exists():
            return

        rgb_url = data_layers_payload.get("rgbUrl")
        if not isinstance(rgb_url, str) or not rgb_url:
            raise HTTPException(status_code=502, detail="Google Solar data layers did not include an RGB image.")

        try:
            response = httpx.get(self._with_api_key(rgb_url), timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="Google Solar RGB image request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Google Solar RGB image returned HTTP {exc.response.status_code}.",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Google Solar RGB image request failed.") from exc

        try:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            image = self._tiff_bytes_to_image(response.content)
            image.save(png_path, format="PNG")
        except (OSError, ValueError, tifffile.TiffFileError) as exc:
            raise HTTPException(status_code=502, detail="Google Solar RGB image could not be converted.") from exc

    def _tiff_bytes_to_image(self, content: bytes) -> Image.Image:
        array = tifffile.imread(BytesIO(content))
        if array.ndim == 2:
            array = np.stack([array, array, array], axis=-1)
        elif array.ndim == 3 and array.shape[0] in (3, 4) and array.shape[-1] not in (3, 4):
            array = np.moveaxis(array, 0, -1)

        if array.ndim != 3:
            raise ValueError("Expected a 2D or RGB TIFF image.")
        if array.shape[-1] > 4:
            array = array[..., :3]

        if array.dtype != np.uint8:
            valid = array[np.isfinite(array)]
            if valid.size == 0:
                raise ValueError("TIFF image contains no finite values.")
            minimum = float(valid.min())
            maximum = float(valid.max())
            if maximum <= minimum:
                array = np.zeros(array.shape, dtype=np.uint8)
            else:
                array = ((array - minimum) / (maximum - minimum) * 255).clip(0, 255).astype(np.uint8)

        mode = "RGBA" if array.shape[-1] == 4 else "RGB"
        return Image.fromarray(array, mode=mode).convert("RGB")

    def _parse_building(
        self,
        payload: dict[str, Any],
        fallback_latitude: float,
        fallback_longitude: float,
    ) -> SolarBuildingData:
        center = self._parse_lat_lng(payload.get("center")) or LatLng(
            latitude=fallback_latitude,
            longitude=fallback_longitude,
        )

        solar_potential = payload.get("solarPotential")
        roof_segments: list[SolarRoofSegment] = []
        if isinstance(solar_potential, dict):
            raw_segments = solar_potential.get("roofSegmentStats")
            if isinstance(raw_segments, list):
                roof_segments = [
                    self._parse_roof_segment(item)
                    for item in raw_segments
                    if isinstance(item, dict)
                ]

        return SolarBuildingData(
            name=self._optional_str(payload.get("name")),
            center=center,
            bounding_box=self._parse_bounding_box(payload.get("boundingBox")),
            imagery_date=self._parse_date(payload.get("imageryDate")),
            imagery_processed_date=self._parse_date(payload.get("imageryProcessedDate")),
            imagery_quality=self._optional_str(payload.get("imageryQuality")),
            region_code=self._optional_str(payload.get("regionCode")),
            postal_code=self._optional_str(payload.get("postalCode")),
            administrative_area=self._optional_str(payload.get("administrativeArea")),
            roof_segments=roof_segments,
        )

    def _parse_roof_segment(self, payload: dict[str, Any]) -> SolarRoofSegment:
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        return SolarRoofSegment(
            center=self._parse_lat_lng(payload.get("center")),
            bounding_box=self._parse_bounding_box(payload.get("boundingBox")),
            pitch_degrees=self._optional_float(payload.get("pitchDegrees")),
            azimuth_degrees=self._optional_float(payload.get("azimuthDegrees")),
            plane_height_at_center_meters=self._optional_float(payload.get("planeHeightAtCenterMeters")),
            area_meters2=self._optional_float(stats.get("areaMeters2")) if isinstance(stats, dict) else None,
            sunshine_quantiles=self._float_list(stats.get("sunshineQuantiles")) if isinstance(stats, dict) else [],
        )

    def _parse_lat_lng(self, value: Any) -> LatLng | None:
        if not isinstance(value, dict):
            return None
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if latitude is None or longitude is None:
            return None
        return LatLng(latitude=float(latitude), longitude=float(longitude))

    def _parse_bounding_box(self, value: Any) -> LatLngBox | None:
        if not isinstance(value, dict):
            return None
        southwest = self._parse_lat_lng(value.get("sw"))
        northeast = self._parse_lat_lng(value.get("ne"))
        if southwest is None or northeast is None:
            return None
        return LatLngBox(southwest=southwest, northeast=northeast)

    def _parse_date(self, value: Any) -> GoogleSolarDate | None:
        if not isinstance(value, dict):
            return None
        return GoogleSolarDate(
            year=self._optional_int(value.get("year")),
            month=self._optional_int(value.get("month")),
            day=self._optional_int(value.get("day")),
        )

    def _asset_id(self, solar_building: SolarBuildingData, data_layers_payload: dict[str, Any]) -> str:
        source = "|".join(
            [
                solar_building.name or "",
                str(solar_building.center.latitude),
                str(solar_building.center.longitude),
                str(data_layers_payload.get("imageryDate", "")),
                str(data_layers_payload.get("imageryProcessedDate", "")),
            ]
        )
        return sha256(source.encode("utf-8")).hexdigest()[:24]

    def _resolved_cache_dir(self) -> Path:
        return self.cache_dir.expanduser().resolve()

    def _write_asset_metadata(self, asset_id: str, payload: dict[str, Any]) -> None:
        path = self._safe_asset_path(asset_id, "metadata.json", require_exists=False)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=502, detail="House asset metadata could not be cached.") from exc

    def _safe_asset_path(
        self,
        asset_id: str,
        filename: str,
        *,
        require_exists: bool = False,
    ) -> Path:
        if not asset_id or "/" in asset_id or "\\" in asset_id or ".." in asset_id:
            raise HTTPException(status_code=404, detail="House asset not found.")
        path = (self._resolved_cache_dir() / asset_id / filename).resolve()
        try:
            path.relative_to(self._resolved_cache_dir())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="House asset not found.") from exc
        if require_exists and not path.is_file():
            raise HTTPException(status_code=404, detail="House asset not found.")
        return path

    def _validate_tile_path(self, tile_path: str) -> str:
        parsed = urlparse(tile_path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise HTTPException(status_code=400, detail="Invalid Google 3D tile path.")

        normalized = tile_path.lstrip("/")
        if normalized.startswith("v1/3dtiles/"):
            normalized = normalized.removeprefix("v1/3dtiles/")

        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts or not tile_path or "\\" in tile_path:
            raise HTTPException(status_code=400, detail="Invalid Google 3D tile path.")
        return path.as_posix()

    def _upstream_tile_query_params(self, query_params: Mapping[str, str]) -> dict[str, str]:
        allowed_params: dict[str, str] = {}
        for key, value in query_params.items():
            if key == "session":
                allowed_params[key] = value
                continue
            raise HTTPException(status_code=400, detail="Invalid Google 3D tile query parameter.")
        return allowed_params

    def _with_api_key(self, url: str) -> str:
        return str(httpx.URL(url).copy_add_param("key", self.api_key or ""))

    def _proxy_tile_uri(self, uri: str, inherited_query_params: Mapping[str, str]) -> str:
        parsed = urlparse(uri)
        if parsed.scheme or parsed.netloc:
            if not uri.startswith(GOOGLE_3D_TILES_BASE_URL):
                raise HTTPException(status_code=502, detail="Google 3D Tiles returned an unsafe tile URI.")
            relative = uri.removeprefix(GOOGLE_3D_TILES_BASE_URL)
        else:
            relative = uri

        relative_parsed = urlparse(relative)
        safe_path = self._validate_tile_path(relative_parsed.path)
        query_params = self._upstream_tile_query_params(dict(httpx.QueryParams(relative_parsed.query)))
        if "session" not in query_params and "session" in inherited_query_params:
            query_params["session"] = inherited_query_params["session"]
        query = f"?{urlencode(query_params)}" if query_params else ""
        return f"/api/google-3d-tiles/{safe_path}{query}"

    def _optional_str(self, value: Any) -> str | None:
        return value if isinstance(value, str) else None

    def _optional_float(self, value: Any) -> float | None:
        return float(value) if value is not None else None

    def _optional_int(self, value: Any) -> int | None:
        return int(value) if value is not None else None

    def _float_list(self, value: Any) -> list[float]:
        if not isinstance(value, list):
            return []
        return [float(item) for item in value]


def get_house_data_service() -> HouseDataService:
    return HouseDataService(
        api_key=settings.google_api_key or settings.google_maps_api_key,
        cache_dir=settings.house_data_cache_dir,
        timeout_seconds=settings.google_timeout_seconds,
        solar_radius_meters=settings.google_solar_radius_meters,
        solar_pixel_size_meters=settings.google_solar_pixel_size_meters,
    )
