from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from app.services.location import google_3d_tiles_service
from app.services.location.coordinates import lla_to_ecef
from app.services.location.google_3d_tiles_service import Google3DTilesService


BERLIN_LATITUDE = 52.520815
BERLIN_LONGITUDE = 13.409419
GLB_BYTES = b"glTF" + b"\x02\x00\x00\x00" + b"\x0c\x00\x00\x00"


def service(query_height_m: float = 100) -> Google3DTilesService:
    return Google3DTilesService(
        api_key="test-key",
        root_url="https://tile.googleapis.com/v1/3dtiles/root.json",
        max_radius_m=200,
        max_walk_depth=32,
        query_height_m=query_height_m,
        timeout_seconds=3,
    )


def test_fetch_house_glb_returns_lowest_geometric_error_leaf_within_radius(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_urls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured_urls.append(url)
        assert kwargs["timeout"] == 3
        if url == "https://tile.googleapis.com/v1/3dtiles/root.json?key=test-key":
            return _json_response(
                "https://tile.googleapis.com/v1/3dtiles/root.json?session=session-123&key=test-key",
                {
                    "asset": {"copyright": "Google"},
                    "root": {
                        "boundingVolume": {"box": _box(offset_m=0, half_m=500)},
                        "geometricError": 16,
                        "children": [
                            {
                                "boundingVolume": {"box": _box(offset_m=0, half_m=150)},
                                "geometricError": 8,
                                "content": {"uri": "subtree/area.json"},
                            },
                            {
                                "boundingVolume": {"box": _box(offset_m=500, half_m=10)},
                                "geometricError": 1,
                                "content": {"uri": "far.glb"},
                            },
                        ],
                    },
                },
            )
        if url == "https://tile.googleapis.com/v1/3dtiles/subtree/area.json?session=session-123&key=test-key":
            return _json_response(
                url,
                {
                    "asset": {"copyright": "Airbus"},
                    "root": {
                        "boundingVolume": {"box": _box(offset_m=0, half_m=100)},
                        "geometricError": 4,
                        "children": [
                            {
                                "boundingVolume": {"box": _box(offset_m=3, half_m=15)},
                                "geometricError": 1.0,
                                "content": {"uri": "leaf_near.glb"},
                            },
                            {
                                "boundingVolume": {"box": _box(offset_m=5, half_m=15)},
                                "geometricError": 0.5,
                                "content": {"uri": "leaf_close.glb"},
                            },
                        ],
                    },
                },
            )
        if url == "https://tile.googleapis.com/v1/3dtiles/subtree/leaf_close.glb?session=session-123&key=test-key":
            return httpx.Response(200, request=httpx.Request("GET", url), content=GLB_BYTES)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    glb_bytes, selected_tile, candidate_count, copyright_text = service().fetch_house_glb(
        latitude=BERLIN_LATITUDE,
        longitude=BERLIN_LONGITUDE,
        radius_m=50,
    )

    assert glb_bytes == GLB_BYTES
    assert selected_tile.uri.endswith("/subtree/leaf_close.glb?session=session-123&key=test-key")
    assert selected_tile.geometric_error == 0.5
    assert candidate_count == 2
    assert copyright_text == "Airbus; Google"
    assert "https://tile.googleapis.com/v1/3dtiles/far.glb?session=session-123&key=test-key" not in captured_urls


def test_fetch_house_glb_returns_404_when_no_tile_intersects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return _json_response(
            url,
            {
                "root": {
                    "boundingVolume": {"box": _box(offset_m=1000, half_m=10)},
                    "content": {"uri": "far.glb"},
                }
            },
        )

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service().fetch_house_glb(BERLIN_LATITUDE, BERLIN_LONGITUDE, radius_m=50)

    assert exc.value.status_code == 404
    assert exc.value.detail == "No 3D tiles intersected the requested radius around the anchor."


def test_fetch_house_glb_returns_502_for_invalid_glb_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        if url.endswith(".glb?key=test-key"):
            return httpx.Response(200, request=httpx.Request("GET", url), content=b"not-a-glb")
        return _json_response(
            url,
            {
                "root": {
                    "boundingVolume": {"box": _box(offset_m=0, half_m=20)},
                    "content": {"uri": "leaf.glb"},
                }
            },
        )

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service().fetch_house_glb(BERLIN_LATITUDE, BERLIN_LONGITUDE, radius_m=50)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Google 3D Tiles returned a tile that is not a valid GLB."


def test_fetch_house_glb_returns_502_for_upstream_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> None:
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service().fetch_house_glb(BERLIN_LATITUDE, BERLIN_LONGITUDE, radius_m=50)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Google 3D Tiles request timed out."


def test_fetch_house_glb_rejects_radius_above_max() -> None:
    with pytest.raises(HTTPException) as exc:
        service().fetch_house_glb(BERLIN_LATITUDE, BERLIN_LONGITUDE, radius_m=1000)

    assert exc.value.status_code == 422
    assert exc.value.detail == "radius_m must be 200 or smaller."


def test_fetch_house_glb_includes_tiles_up_to_configured_query_height(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        if url == "https://tile.googleapis.com/v1/3dtiles/root.json?key=test-key":
            return _json_response(
                "https://tile.googleapis.com/v1/3dtiles/root.json?key=test-key",
                {
                    "root": {
                        "boundingVolume": {"box": _box_at_altitude(altitude_m=80, half_m=1)},
                        "geometricError": 1,
                        "content": {"uri": "elevated-roof.glb"},
                    }
                },
            )
        if url == "https://tile.googleapis.com/v1/3dtiles/elevated-roof.glb?key=test-key":
            return httpx.Response(200, request=httpx.Request("GET", url), content=GLB_BYTES)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    glb_bytes, selected_tile, candidate_count, _copyright_text = service(query_height_m=100).fetch_house_glb(
        BERLIN_LATITUDE,
        BERLIN_LONGITUDE,
        radius_m=20,
    )

    assert glb_bytes == GLB_BYTES
    assert selected_tile.uri.endswith("/elevated-roof.glb?key=test-key")
    assert candidate_count == 1


def test_fetch_house_glb_excludes_tiles_above_configured_query_height(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return _json_response(
            url,
            {
                "root": {
                    "boundingVolume": {"box": _box_at_altitude(altitude_m=130, half_m=1)},
                    "content": {"uri": "too-high.glb"},
                }
            },
        )

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc:
        service(query_height_m=100).fetch_house_glb(BERLIN_LATITUDE, BERLIN_LONGITUDE, radius_m=20)

    assert exc.value.status_code == 404
    assert exc.value.detail == "No 3D tiles intersected the requested radius around the anchor."


def _box(offset_m: float, half_m: float) -> list[float]:
    base = lla_to_ecef(BERLIN_LATITUDE, BERLIN_LONGITUDE)
    return [
        base[0] + offset_m,
        base[1],
        base[2],
        half_m,
        0,
        0,
        0,
        half_m,
        0,
        0,
        0,
        half_m,
    ]


def _box_at_altitude(altitude_m: float, half_m: float) -> list[float]:
    base = lla_to_ecef(BERLIN_LATITUDE, BERLIN_LONGITUDE, altitude_m=altitude_m)
    return [
        base[0],
        base[1],
        base[2],
        half_m,
        0,
        0,
        0,
        half_m,
        0,
        0,
        0,
        half_m,
    ]


def _json_response(url: str, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("GET", url), json=payload)
