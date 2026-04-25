import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services.house_data_service import HouseDataService, get_house_data_service


def test_overhead_asset_route_serves_cached_png(tmp_path) -> None:
    asset_dir = tmp_path / "asset-123"
    asset_dir.mkdir()
    (asset_dir / "overhead.png").write_bytes(b"png-bytes")

    service = HouseDataService(
        api_key="test-key",
        cache_dir=tmp_path,
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )
    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get("/api/house-assets/asset-123/overhead.png")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"] == "image/png"


def test_google_3d_tiles_proxy_rewrites_json_uris(monkeypatch) -> None:
    service = HouseDataService(
        api_key="test-key",
        cache_dir="unused",
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> httpx.Response:
        assert url == "https://tile.googleapis.com/v1/3dtiles/root.json"
        assert params == {"key": "test-key"}
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "root": {
                    "children": [
                        {"content": {"uri": "tiles/0.b3dm"}},
                        {
                            "content": {
                                "uri": "https://tile.googleapis.com/v1/3dtiles/tiles/1.b3dm"
                            }
                        },
                        {
                            "content": {
                                "uri": "/v1/3dtiles/datasets/example.glb?session=session-123"
                            }
                        },
                    ]
                }
            },
            headers={"content-type": "application/json"},
        )

    from app.services import house_data_service

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)
    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get("/api/google-3d-tiles/root.json")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    children = payload["root"]["children"]
    assert children[0]["content"]["uri"] == "/api/google-3d-tiles/tiles/0.b3dm"
    assert children[1]["content"]["uri"] == "/api/google-3d-tiles/tiles/1.b3dm"
    assert (
        children[2]["content"]["uri"]
        == "/api/google-3d-tiles/datasets/example.glb?session=session-123"
    )


def test_google_3d_tiles_proxy_streams_binary_tiles(monkeypatch) -> None:
    service = HouseDataService(
        api_key="test-key",
        cache_dir="unused",
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> httpx.Response:
        assert url == "https://tile.googleapis.com/v1/3dtiles/datasets/example.glb"
        assert params == {"session": "session-123", "key": "test-key"}
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=b"tile-bytes",
            headers={"content-type": "model/gltf-binary"},
        )

    from app.services import house_data_service

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)
    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get(
            "/api/google-3d-tiles/v1/3dtiles/datasets/example.glb?session=session-123"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"tile-bytes"
    assert response.headers["content-type"] == "model/gltf-binary"


def test_google_3d_tiles_proxy_inherits_session_when_rewriting_child_json(monkeypatch) -> None:
    service = HouseDataService(
        api_key="test-key",
        cache_dir="unused",
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    def fake_get(url: str, params: dict[str, object], timeout: float, **kwargs: object) -> httpx.Response:
        assert url == "https://tile.googleapis.com/v1/3dtiles/datasets/child.json"
        assert params == {"session": "session-123", "key": "test-key"}
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"root": {"content": {"uri": "/v1/3dtiles/datasets/local.glb"}}},
            headers={"content-type": "application/json"},
        )

    from app.services import house_data_service

    monkeypatch.setattr(house_data_service.httpx, "get", fake_get)
    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get(
            "/api/google-3d-tiles/datasets/child.json?session=session-123"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (
        response.json()["root"]["content"]["uri"]
        == "/api/google-3d-tiles/datasets/local.glb?session=session-123"
    )


def test_google_3d_tiles_proxy_rejects_unsafe_paths(tmp_path) -> None:
    service = HouseDataService(
        api_key="test-key",
        cache_dir=tmp_path,
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get("/api/google-3d-tiles/https:%2F%2Fevil.example%2Ftile.json")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Google 3D tile path."


def test_google_3d_tiles_proxy_rejects_unexpected_query_params(tmp_path) -> None:
    service = HouseDataService(
        api_key="test-key",
        cache_dir=tmp_path,
        timeout_seconds=3.0,
        solar_radius_meters=50,
        solar_pixel_size_meters=0.25,
    )

    app.dependency_overrides[get_house_data_service] = lambda: service
    try:
        response = TestClient(app).get("/api/google-3d-tiles/root.json?host=evil.example")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Google 3D tile query parameter."
