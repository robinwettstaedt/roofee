from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.routes import location
from app.main import app
from app.services.location.coordinates import IDENTITY_MATRIX4
from app.services.location.geocoding_service import get_geocoding_service
from app.services.location.google_3d_tiles_service import TileCandidate, get_google_3d_tiles_service


def test_house_model_route_returns_glb_with_metadata_header(monkeypatch) -> None:
    glb_bytes = b"glTF" + b"\x02\x00\x00\x00" + b"\x0c\x00\x00\x00"

    class FakeGeocodingService:
        pass

    class FakeTilesService:
        def fetch_house_glb(self, latitude: float, longitude: float, radius_m: float) -> tuple[bytes, TileCandidate, int, str]:
            assert latitude == 52.520815
            assert longitude == 13.409419
            assert radius_m == 25
            return (
                glb_bytes,
                TileCandidate(
                    uri="https://tile.googleapis.com/v1/3dtiles/leaf.glb?session=session-123&key=test-key",
                    geometric_error=0.25,
                    distance_m=3.5,
                    bounding_sphere_center=(1, 2, 3),
                    bounding_sphere_radius_m=12.5,
                    transform=IDENTITY_MATRIX4,
                ),
                4,
                "Google",
            )

    monkeypatch.setattr(location.settings, "google_api_key", "test-key")
    monkeypatch.setattr(location.settings, "google_maps_api_key", None)
    app.dependency_overrides[get_geocoding_service] = lambda: FakeGeocodingService()
    app.dependency_overrides[get_google_3d_tiles_service] = lambda: FakeTilesService()
    try:
        response = TestClient(app).post(
            "/api/location/house-model",
            json={"latitude": 52.520815, "longitude": 13.409419, "radius_m": 25},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "model/gltf-binary"
    assert response.content == glb_bytes
    metadata = json.loads(response.headers["Roofee-Metadata"])
    assert metadata["anchor_latitude"] == 52.520815
    assert metadata["anchor_longitude"] == 13.409419
    assert metadata["geocoding"]["source"] == "request"
    assert metadata["candidate_tile_count"] == 4
    assert metadata["tile"]["geometric_error"] == 0.25
    assert metadata["glb_size_bytes"] == len(glb_bytes)


def test_house_model_route_returns_503_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(location.settings, "google_api_key", None)
    monkeypatch.setattr(location.settings, "google_maps_api_key", None)

    response = TestClient(app).post(
        "/api/location/house-model",
        json={"latitude": 52.520815, "longitude": 13.409419, "radius_m": 25},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Google API key is not configured."


def test_house_model_route_returns_400_without_anchor(monkeypatch) -> None:
    monkeypatch.setattr(location.settings, "google_api_key", "test-key")
    monkeypatch.setattr(location.settings, "google_maps_api_key", None)

    response = TestClient(app).post("/api/location/house-model", json={"radius_m": 25})

    assert response.status_code == 400
    assert response.json()["detail"] == "Provide either address or latitude and longitude."
