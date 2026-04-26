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


def service() -> Google3DTilesService:
    return Google3DTilesService(
        api_key="test-key",
        root_url="https://tile.googleapis.com/v1/3dtiles/root.json",
        max_radius_m=200,
        max_walk_depth=32,
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


def test_fetch_tile_glb_normalizes_key_and_appends_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_url: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured_url.append(url)
        return httpx.Response(200, request=httpx.Request("GET", url), content=GLB_BYTES)

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    body = service().fetch_tile_glb(
        "https://tile.googleapis.com/v1/3dtiles/leaf.glb?key=browser-key",
        session="session-abc",
    )

    assert body == GLB_BYTES
    # Browser key was stripped, server key was set, session was appended.
    assert "key=test-key" in captured_url[0]
    assert "key=browser-key" not in captured_url[0]
    assert "session=session-abc" in captured_url[0]


def test_fetch_tile_glb_preserves_existing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_url: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured_url.append(url)
        return httpx.Response(200, request=httpx.Request("GET", url), content=GLB_BYTES)

    monkeypatch.setattr(google_3d_tiles_service.httpx, "get", fake_get)

    service().fetch_tile_glb(
        "https://tile.googleapis.com/v1/3dtiles/leaf.glb?session=already-set",
        session="ignored-because-uri-already-has-one",
    )

    assert "session=already-set" in captured_url[0]
    assert "ignored-because-uri-already-has-one" not in captured_url[0]


def test_fetch_tile_glb_rejects_unauthorized_host() -> None:
    with pytest.raises(HTTPException) as exc:
        service().fetch_tile_glb("https://evil.example.com/3dtiles/leaf.glb")

    assert exc.value.status_code == 422
    assert "not allowed" in exc.value.detail


def test_fetch_tile_glb_rejects_relative_uri() -> None:
    with pytest.raises(HTTPException) as exc:
        service().fetch_tile_glb("leaf.glb")

    assert exc.value.status_code == 422
    assert exc.value.detail == "tile_uri must be an absolute http(s) URL."


def test_fetch_tile_glb_rejects_empty_uri() -> None:
    with pytest.raises(HTTPException) as exc:
        service().fetch_tile_glb("   ")

    assert exc.value.status_code == 422
    assert exc.value.detail == "tile_uri must be a non-empty string."


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


def _json_response(url: str, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("GET", url), json=payload)
