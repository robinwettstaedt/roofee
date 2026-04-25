from fastapi.testclient import TestClient

from app.main import app
from app.models.roof import (
    BoundingBoxPixels,
    RoofOutline,
    RoofSelectionRequest,
    RoofSelectionResponse,
    SelectedRoof,
)
from app.services.house_data_service import get_house_data_service
from app.services.roof.roof_analysis_service import get_roof_analysis_service


class FakeRoofAnalysisService:
    def select_roof(
        self,
        request: RoofSelectionRequest,
        house_data_service: object,
    ) -> RoofSelectionResponse:
        outline = RoofOutline(
            id=request.selected_roof_outline_ids[0],
            source="test",
            model_id="test-building-outline",
            bounding_box_pixels=BoundingBoxPixels(x_min=4, y_min=5, x_max=20, y_max=30),
            polygon_pixels=[[4, 5], [20, 5], [20, 30], [4, 30]],
            area_pixels=400,
            confidence=0.9,
        )
        return RoofSelectionResponse(
            status="selected",
            selected_roof=SelectedRoof(
                satellite_image_url=request.satellite_image_url,
                selected_roof_outline_ids=request.selected_roof_outline_ids,
                selected_roof_outlines=[outline],
                bounding_box_pixels=outline.bounding_box_pixels,
                area_pixels=outline.area_pixels,
            ),
        )


def test_roof_selection_route_accepts_selected_outline_ids() -> None:
    app.dependency_overrides[get_house_data_service] = lambda: object()
    app.dependency_overrides[get_roof_analysis_service] = lambda: FakeRoofAnalysisService()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/roof/selection",
            json={
                "satellite_image_url": "/api/house-assets/test-asset/overhead.png",
                "selected_roof_outline_ids": ["roof-003"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "selected"
    assert payload["selected_roof"]["satellite_image_url"] == "/api/house-assets/test-asset/overhead.png"
    assert payload["selected_roof"]["selected_roof_outline_ids"] == ["roof-003"]
    assert payload["selected_roof"]["bounding_box_pixels"] == {
        "x_min": 4,
        "y_min": 5,
        "x_max": 20,
        "y_max": 30,
    }
