import json
from io import BytesIO

import httpx
import numpy as np
import pytest
import tifffile
from fastapi import HTTPException

from app.services import house_data_service
from app.services.house_data_service import (
    GOOGLE_SOLAR_BUILDING_INSIGHTS_URL,
    GOOGLE_SOLAR_DATA_LAYERS_URL,
    HouseDataService,
)


def service(tmp_path) -> HouseDataService:
    return HouseDataService(
        api_key="test-key",
        cache_dir=tmp_path,
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )


def tiff_bytes() -> bytes:
    buffer = BytesIO()
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[..., 0] = 255
    tifffile.imwrite(buffer, image, photometric="rgb")
    return buffer.getvalue()


def test_fetch_house_data_calls_google_solar_and_converts_rgb_geotiff(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        def __init__(
            self,
            *,
            payload: dict[str, object] | None = None,
            content: bytes = b"",
        ) -> None:
            self._payload = payload
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            assert self._payload is not None
            return self._payload

    def fake_get(
        url: str,
        params: dict[str, object] | None = None,
        timeout: float = 0,
        **kwargs: object,
    ) -> FakeResponse:
        captured.append((url, params or {}))
        assert timeout == 3.0
        if url == GOOGLE_SOLAR_BUILDING_INSIGHTS_URL:
            return FakeResponse(
                payload={
                    "name": "buildings/test-place",
                    "center": {"latitude": 52.521, "longitude": 13.406},
                    "boundingBox": {
                        "sw": {"latitude": 52.52, "longitude": 13.405},
                        "ne": {"latitude": 52.522, "longitude": 13.407},
                    },
                    "imageryDate": {"year": 2024, "month": 5, "day": 1},
                    "imageryQuality": "HIGH",
                    "regionCode": "DE",
                    "solarPotential": {
                        "roofSegmentStats": [
                            {
                                "center": {"latitude": 52.521, "longitude": 13.406},
                                "pitchDegrees": 35,
                                "azimuthDegrees": 180,
                                "planeHeightAtCenterMeters": 48.5,
                                "stats": {
                                    "areaMeters2": 42.0,
                                    "sunshineQuantiles": [1000, 1100, 1200],
                                },
                            }
                        ]
                    },
                }
            )
        if url == GOOGLE_SOLAR_DATA_LAYERS_URL:
            return FakeResponse(
                payload={
                    "rgbUrl": "https://solar.googleapis.com/v1/geoTiff:get?id=rgb",
                    "imageryDate": {"year": 2024, "month": 5, "day": 1},
                    "imageryQuality": "HIGH",
                }
            )
        assert url == "https://solar.googleapis.com/v1/geoTiff:get?id=rgb&key=test-key"
        return FakeResponse(content=tiff_bytes())

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)

    result = service(tmp_path).fetch_house_data(52.52, 13.405)

    assert result.status == "fetched"
    assert result.solar_building.name == "buildings/test-place"
    assert result.solar_building.center.latitude == 52.521
    assert result.solar_building.roof_segments[0].area_meters2 == 42.0
    assert result.overhead_image_url.startswith("/api/house-assets/")
    assert result.tiles_3d.root_url == "/api/google-3d-tiles/root.json"
    assert (tmp_path / result.overhead_image_url.split("/")[3] / "overhead.png").is_file()
    metadata_path = tmp_path / result.overhead_image_url.split("/")[3] / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["building_center"] == {"latitude": 52.521, "longitude": 13.406}
    assert captured[0][1]["location.latitude"] == 52.52
    assert captured[1][1]["location.latitude"] == 52.521
    assert captured[1][1]["view"] == "IMAGERY_LAYERS"


def test_fetch_house_data_returns_503_without_api_key(tmp_path) -> None:
    missing_key_service = HouseDataService(
        api_key="",
        cache_dir=tmp_path,
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    with pytest.raises(HTTPException) as exc:
        missing_key_service.fetch_house_data(52.52, 13.405)

    assert exc.value.status_code == 503
    assert exc.value.detail == "Google Maps API key is not configured."


def test_fetch_house_data_returns_502_for_google_timeout(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> None:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service(tmp_path).fetch_house_data(52.52, 13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Google house data request timed out."


def test_fetch_house_data_returns_502_for_google_no_coverage(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 404

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", GOOGLE_SOLAR_BUILDING_INSIGHTS_URL)
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service(tmp_path).fetch_house_data(52.52, 13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Google house data returned HTTP 404."


def test_fetch_house_data_returns_502_for_malformed_json(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[object]:
            return []

    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service(tmp_path).fetch_house_data(52.52, 13.405)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Google house data returned malformed data."
