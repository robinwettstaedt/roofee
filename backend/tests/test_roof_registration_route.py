from fastapi.testclient import TestClient

from app.main import app
from app.models.roof import (
    BoundingBoxPixels,
    OrthographicWorldBounds,
    RegistrationQualityMetrics,
    RoofOutline,
    RoofRegistrationRequest,
    RoofRegistrationResponse,
    SelectedRoof,
    SimilarityTransform,
    TopDownRenderMetadata,
)
from app.services.house_data_service import get_house_data_service
from app.services.roof.registration_service import get_roof_registration_service


class FakeRoofRegistrationService:
    def register_roof(
        self,
        request: RoofRegistrationRequest,
        top_down_render_png: bytes,
        house_data_service: object,
    ) -> RoofRegistrationResponse:
        outline = RoofOutline(
            id=request.selected_roof_outline_ids[0],
            source="test",
            model_id="test-building-outline",
            bounding_box_pixels=BoundingBoxPixels(x_min=40, y_min=40, x_max=60, y_max=60),
            polygon_pixels=[[40, 40], [60, 40], [60, 60], [40, 60]],
            area_pixels=400,
            confidence=0.9,
        )
        return RoofRegistrationResponse(
            status="registered",
            selected_roof=SelectedRoof(
                satellite_image_url=request.satellite_image_url,
                selected_roof_outline_ids=request.selected_roof_outline_ids,
                selected_roof_outlines=[outline],
                bounding_box_pixels=outline.bounding_box_pixels,
                area_pixels=outline.area_pixels,
            ),
            transform=SimilarityTransform(
                matrix=[[1, 0, 12], [0, 1, 24]],
                scale=1,
                rotation_degrees=0,
                translation_pixels=[12, 24],
                algorithm="orb",
            ),
            mapped_roof_polygon_pixels=[[52, 64], [72, 64], [72, 84], [52, 84]],
            render_metadata=request.top_down_render_metadata,
            quality=RegistrationQualityMetrics(
                algorithm="orb",
                confidence=0.9,
                satellite_keypoints=20,
                render_keypoints=22,
                good_matches=18,
                inliers=15,
                inlier_ratio=0.8333,
                mean_reprojection_error_pixels=1.2,
            ),
            warnings=[],
        )


def test_roof_registration_route_accepts_multipart_request() -> None:
    app.dependency_overrides[get_house_data_service] = lambda: object()
    app.dependency_overrides[get_roof_registration_service] = lambda: FakeRoofRegistrationService()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/roof/registration",
            data={"request": _request_json()},
            files={"top_down_render": ("render.png", b"png-bytes", "image/png")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "registered"
    assert payload["selected_roof"]["selected_roof_outline_ids"] == ["roof-003"]
    assert payload["transform"]["matrix"] == [[1.0, 0.0, 12.0], [0.0, 1.0, 24.0]]
    assert payload["mapped_roof_polygon_pixels"] == [[52, 64], [72, 64], [72, 84], [52, 84]]
    assert payload["quality"]["confidence"] == 0.9


def test_roof_registration_route_rejects_invalid_json() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/roof/registration",
        data={"request": "{not-json"},
        files={"top_down_render": ("render.png", b"png-bytes", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid registration request JSON."


def _request_json() -> str:
    request = RoofRegistrationRequest(
        satellite_image_url="/api/house-assets/test-asset/overhead.png",
        selected_roof_outline_ids=["roof-003"],
        top_down_render_metadata=TopDownRenderMetadata(
            render_width=1024,
            render_height=1024,
            orthographic_world_bounds=OrthographicWorldBounds(
                x_min=-12,
                x_max=12,
                z_min=-12,
                z_max=12,
                y_min=0,
                y_max=8,
            ),
            model_orientation={"up_axis": "y"},
        ),
    )
    return request.model_dump_json()
