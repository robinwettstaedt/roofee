from fastapi.testclient import TestClient

from app.main import app
from app.models.roof import (
    BoundingBoxPixels,
    OrthographicWorldBounds,
    RegistrationQualityMetrics,
    RoofGeometryAnalysisRequest,
    RoofGeometryAnalysisResponse,
    RoofOutline,
    RoofRegistrationResponse,
    SelectedRoof,
    SimilarityTransform,
    TopDownRenderMetadata,
)
from app.services.house_data_service import get_house_data_service
from app.services.location.google_3d_tiles_service import get_google_3d_tiles_service
from app.services.roof.geometry_pipeline_service import get_roof_geometry_pipeline_service


class FakeRoofGeometryPipelineService:
    def analyze_geometry(
        self,
        request: RoofGeometryAnalysisRequest,
        *,
        house_data_service: object,
        tiles_service: object,
    ) -> RoofGeometryAnalysisResponse:
        assert request.selected_roof_outline_ids == ["roof-003"]
        assert request.model_radius_m == 50
        selected_roof = _selected_roof(request)
        metadata = _metadata()
        registration = RoofRegistrationResponse(
            status="registered",
            selected_roof=selected_roof,
            transform=SimilarityTransform(
                matrix=[[1, 0, 0], [0, 1, 0]],
                scale=1,
                rotation_degrees=0,
                translation_pixels=[0, 0],
                algorithm="orb",
            ),
            mapped_roof_polygon_pixels=[[4, 5], [20, 5], [20, 30], [4, 30]],
            render_metadata=metadata,
            quality=RegistrationQualityMetrics(confidence=0.9),
        )
        return RoofGeometryAnalysisResponse(
            status="analyzed",
            selected_roof=selected_roof,
            registration=registration,
            render_metadata=metadata,
            warnings=[],
        )


def test_roof_geometry_route_runs_from_selected_roof_ids_without_frontend_render() -> None:
    app.dependency_overrides[get_house_data_service] = lambda: object()
    app.dependency_overrides[get_google_3d_tiles_service] = lambda: object()
    app.dependency_overrides[get_roof_geometry_pipeline_service] = lambda: FakeRoofGeometryPipelineService()
    try:
        response = TestClient(app).post(
            "/api/roof/geometry",
            json={
                "satellite_image_url": "/api/house-assets/test-asset/overhead.png",
                "selected_roof_outline_ids": ["roof-003"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "analyzed"
    assert payload["selected_roof"]["selected_roof_outline_ids"] == ["roof-003"]
    assert payload["registration"]["status"] == "registered"


def _selected_roof(request: RoofGeometryAnalysisRequest) -> SelectedRoof:
    outline = RoofOutline(
        id=request.selected_roof_outline_ids[0],
        source="test",
        model_id="test-building-outline",
        bounding_box_pixels=BoundingBoxPixels(x_min=4, y_min=5, x_max=20, y_max=30),
        polygon_pixels=[[4, 5], [20, 5], [20, 30], [4, 30]],
        area_pixels=400,
        confidence=0.9,
    )
    return SelectedRoof(
        satellite_image_url=request.satellite_image_url,
        selected_roof_outline_ids=request.selected_roof_outline_ids,
        selected_roof_outlines=[outline],
        bounding_box_pixels=outline.bounding_box_pixels,
        area_pixels=outline.area_pixels,
    )


def _metadata() -> TopDownRenderMetadata:
    return TopDownRenderMetadata(
        render_width=100,
        render_height=100,
        orthographic_world_bounds=OrthographicWorldBounds(x_min=0, x_max=10, z_min=0, z_max=10),
        model_orientation={"up_axis": "y"},
    )
