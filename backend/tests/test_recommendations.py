import json
import struct
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.recommendation import (
    Google3DTilesData,
    HouseData,
    LatLng,
    RecommendationRequest,
    SolarBuildingData,
    SolarWeatherMetadata,
)
from app.services.house_data_service import get_house_data_service
from app.services.pvgis_service import get_pvgis_service


class FakePvgisService:
    def fetch_solar_weather(self, latitude: float, longitude: float) -> SolarWeatherMetadata:
        return SolarWeatherMetadata(
            provider="pvgis",
            api_version="5.3",
            latitude=latitude,
            longitude=longitude,
            source_url="https://re.jrc.ec.europa.eu/api/v5_3/MRcalc",
            request_params={
                "lat": latitude,
                "lon": longitude,
                "horirrad": 1,
                "optrad": 1,
                "avtemp": 1,
                "outputformat": "json",
            },
            annual_horizontal_irradiation_kwh_per_m2=1200,
            annual_optimal_irradiation_kwh_per_m2=1400,
            average_temperature_c=11,
            monthly=[
                {
                    "month": month,
                    "horizontal_irradiation_kwh_per_m2": 100,
                    "optimal_irradiation_kwh_per_m2": 116.67,
                    "average_temperature_c": 11,
                }
                for month in range(1, 13)
            ],
        )


class FailingPvgisService:
    def fetch_solar_weather(self, latitude: float, longitude: float) -> SolarWeatherMetadata:
        raise HTTPException(status_code=502, detail="PVGIS request timed out.")


class FakeHouseDataService:
    def fetch_house_data(self, latitude: float, longitude: float) -> HouseData:
        center = LatLng(latitude=latitude, longitude=longitude)
        return HouseData(
            status="fetched",
            provider="google",
            location=center,
            solar_building=SolarBuildingData(center=center, imagery_quality="HIGH"),
            overhead_image_url="/api/house-assets/test-asset/overhead.png",
            tiles_3d=Google3DTilesData(root_url="/api/google-3d-tiles/root.json", origin=center),
            warnings=[],
        )


class FailingHouseDataService:
    def fetch_house_data(self, latitude: float, longitude: float) -> HouseData:
        raise HTTPException(status_code=503, detail="Google Maps API key is not configured.")


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_pvgis_service] = lambda: FakePvgisService()
    app.dependency_overrides[get_house_data_service] = lambda: FakeHouseDataService()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def valid_recommendation_payload() -> dict[str, object]:
    return {
        "address": "Test Street 1, Berlin",
        "latitude": 52.52,
        "longitude": 13.405,
        "annual_electricity_demand_kwh": 4500,
        "electricity_price_per_kwh": 0.39,
        "num_inhabitants": 3,
        "house_size_sqm": 140,
        "heating_existing_type": "gas",
        "has_ev": False,
        "has_solar": False,
        "has_storage": False,
        "has_wallbox": False,
        "recommendation_goal": "balanced",
        "battery_preference": "consider",
        "heat_pump_preference": "consider",
        "ev_charger_preference": "consider",
    }


def multipart_request(payload: dict[str, object]) -> dict[str, tuple[None, str]]:
    return {"request": (None, json.dumps(payload))}


def test_recommendation_request_accepts_valid_payload_and_defaults_load_profile() -> None:
    request = RecommendationRequest.model_validate(valid_recommendation_payload())

    assert request.load_profile == "H0"
    assert request.shading_level == "unknown"
    assert request.latitude == 52.52
    assert request.longitude == 13.405


def test_recommendation_request_accepts_optional_google_place_id() -> None:
    payload = valid_recommendation_payload()
    payload["google_place_id"] = "ChIJAVkDPzdOqEcRcDteW0YgIQQ"

    request = RecommendationRequest.model_validate(payload)

    assert request.google_place_id == "ChIJAVkDPzdOqEcRcDteW0YgIQQ"


def test_recommendation_request_rejects_unknown_fields() -> None:
    payload = valid_recommendation_payload()
    payload["unexpected"] = "value"

    try:
        RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("Expected unknown fields to be rejected")


def test_recommendation_request_rejects_invalid_enum() -> None:
    payload = valid_recommendation_payload()
    payload["recommendation_goal"] = "fastest_install"

    try:
        RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "enum"
    else:
        raise AssertionError("Expected invalid enum to be rejected")


def test_recommendation_request_rejects_invalid_numbers() -> None:
    payload = valid_recommendation_payload()
    payload["annual_electricity_demand_kwh"] = -1

    try:
        RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "greater_than"
    else:
        raise AssertionError("Expected negative demand to be rejected")


def test_recommendation_request_rejects_missing_coordinates() -> None:
    payload = valid_recommendation_payload()
    del payload["latitude"]

    try:
        RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "missing"
        assert exc.errors()[0]["loc"] == ("latitude",)
    else:
        raise AssertionError("Expected missing latitude to be rejected")


def test_recommendation_request_rejects_out_of_range_coordinates() -> None:
    payload = valid_recommendation_payload()
    payload["longitude"] = 181

    try:
        RecommendationRequest.model_validate(payload)
    except ValidationError as exc:
        assert exc.errors()[0]["type"] == "less_than_equal"
        assert exc.errors()[0]["loc"] == ("longitude",)
    else:
        raise AssertionError("Expected out-of-range longitude to be rejected")


def test_recommendation_route_accepts_multipart_without_model_file(client: TestClient) -> None:
    response = client.post("/api/recommendations", files=multipart_request(valid_recommendation_payload()))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "validated"
    assert payload["input"]["load_profile"] == "H0"
    assert payload["model_file"] == {"provided": False, "filename": None, "size_bytes": None, "format": None, "version": None}
    assert payload["solar_weather"]["provider"] == "pvgis"
    assert payload["solar_weather"]["latitude"] == 52.52
    assert payload["solar_weather"]["longitude"] == 13.405
    assert len(payload["solar_weather"]["monthly"]) == 12
    assert payload["house_data"]["provider"] == "google"
    assert payload["house_data"]["overhead_image_url"] == "/api/house-assets/test-asset/overhead.png"
    assert payload["house_data"]["tiles_3d"]["root_url"] == "/api/google-3d-tiles/root.json"
    assert {"field": "load_profile", "value": "H0", "reason": "defaulted"} in payload["estimated_inputs"]
    assert {"field": "shading_level", "value": "unknown", "reason": "not_provided"} in payload["estimated_inputs"]


def test_recommendation_route_accepts_valid_glb_model_file(client: TestClient) -> None:
    model_path = Path("data/Exp 3D-Modells/3D_Modell Hamburg.glb")

    with model_path.open("rb") as model_file:
        response = client.post(
            "/api/recommendations",
            files={
                **multipart_request(valid_recommendation_payload()),
                "model_file": ("house.glb", model_file, "model/gltf-binary"),
            },
        )

    assert response.status_code == 200
    model_payload = response.json()["model_file"]
    assert model_payload["provided"] is True
    assert model_payload["filename"] == "house.glb"
    assert model_payload["format"] == "glb"
    assert model_payload["version"] == 2
    assert model_payload["size_bytes"] == model_path.stat().st_size


def test_recommendation_route_returns_422_for_missing_required_fields(client: TestClient) -> None:
    payload = valid_recommendation_payload()
    del payload["address"]

    response = client.post("/api/recommendations", files=multipart_request(payload))

    assert response.status_code == 422


def test_recommendation_route_returns_422_for_missing_latitude(client: TestClient) -> None:
    payload = valid_recommendation_payload()
    del payload["latitude"]

    response = client.post("/api/recommendations", files=multipart_request(payload))

    assert response.status_code == 422


def test_recommendation_route_returns_422_for_invalid_coordinates(client: TestClient) -> None:
    payload = valid_recommendation_payload()
    payload["latitude"] = -91

    response = client.post("/api/recommendations", files=multipart_request(payload))

    assert response.status_code == 422


def test_recommendation_route_returns_502_when_pvgis_fails() -> None:
    app.dependency_overrides[get_pvgis_service] = lambda: FailingPvgisService()
    app.dependency_overrides[get_house_data_service] = lambda: FakeHouseDataService()
    try:
        client = TestClient(app)
        response = client.post("/api/recommendations", files=multipart_request(valid_recommendation_payload()))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "PVGIS request timed out."


def test_recommendation_route_returns_503_when_house_data_is_not_configured() -> None:
    app.dependency_overrides[get_pvgis_service] = lambda: FakePvgisService()
    app.dependency_overrides[get_house_data_service] = lambda: FailingHouseDataService()
    try:
        client = TestClient(app)
        response = client.post("/api/recommendations", files=multipart_request(valid_recommendation_payload()))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Google Maps API key is not configured."


def test_recommendation_route_returns_400_for_invalid_json(client: TestClient) -> None:
    response = client.post("/api/recommendations", files={"request": (None, "{")})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON in request field."


def test_recommendation_route_returns_400_for_non_glb_upload(client: TestClient) -> None:
    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.txt", b"not a model", "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Model upload must be a .glb file."


def test_recommendation_route_returns_400_for_oversized_glb_upload(client: TestClient) -> None:
    size_bytes = 50 * 1024 * 1024 + 1
    content = b"glTF" + struct.pack("<II", 2, size_bytes) + (b"\0" * (size_bytes - 12))

    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.glb", content, "model/gltf-binary"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Model upload must be 50 MB or smaller."


def test_recommendation_route_returns_400_for_bad_glb_magic(client: TestClient) -> None:
    content = b"BAD!" + struct.pack("<II", 2, 12)

    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.glb", content, "model/gltf-binary"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid GLB file: missing glTF magic header."


def test_recommendation_route_returns_400_for_bad_glb_version(client: TestClient) -> None:
    content = b"glTF" + struct.pack("<II", 1, 12)

    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.glb", content, "model/gltf-binary"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid GLB file: only version 2 is supported."


def test_recommendation_route_returns_400_for_bad_glb_length(client: TestClient) -> None:
    content = b"glTF" + struct.pack("<II", 2, 100)

    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.glb", content, "model/gltf-binary"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid GLB file: declared length does not match upload size."
