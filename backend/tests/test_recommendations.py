import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.recommendation import RecommendationRequest


def valid_recommendation_payload() -> dict[str, object]:
    return {
        "address": "Test Street 1, Berlin",
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


def test_recommendation_route_accepts_multipart_without_model_file() -> None:
    client = TestClient(app)

    response = client.post("/api/recommendations", files=multipart_request(valid_recommendation_payload()))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "validated"
    assert payload["input"]["load_profile"] == "H0"
    assert payload["model_file"] == {"provided": False, "filename": None, "size_bytes": None, "format": None, "version": None}
    assert {"field": "load_profile", "value": "H0", "reason": "defaulted"} in payload["estimated_inputs"]
    assert {"field": "shading_level", "value": "unknown", "reason": "not_provided"} in payload["estimated_inputs"]


def test_recommendation_route_accepts_valid_glb_model_file() -> None:
    client = TestClient(app)
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


def test_recommendation_route_returns_422_for_missing_required_fields() -> None:
    client = TestClient(app)
    payload = valid_recommendation_payload()
    del payload["address"]

    response = client.post("/api/recommendations", files=multipart_request(payload))

    assert response.status_code == 422


def test_recommendation_route_returns_400_for_invalid_json() -> None:
    client = TestClient(app)

    response = client.post("/api/recommendations", files={"request": (None, "{")})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON in request field."


def test_recommendation_route_returns_400_for_non_glb_upload() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/recommendations",
        files={
            **multipart_request(valid_recommendation_payload()),
            "model_file": ("house.txt", b"not a model", "text/plain"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Model upload must be a .glb file."


def test_recommendation_route_returns_400_for_oversized_glb_upload() -> None:
    client = TestClient(app)
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


def test_recommendation_route_returns_400_for_bad_glb_magic() -> None:
    client = TestClient(app)
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


def test_recommendation_route_returns_400_for_bad_glb_version() -> None:
    client = TestClient(app)
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


def test_recommendation_route_returns_400_for_bad_glb_length() -> None:
    client = TestClient(app)
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
