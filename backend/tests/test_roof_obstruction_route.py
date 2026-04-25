from fastapi.testclient import TestClient

from app.main import app
from app.models.roof import (
    BoundingBoxPixels,
    RoofObstruction,
    RoofObstructionAnalysis,
    RoofObstructionRequest,
    RoofOutline,
    SelectedRoof,
)
from app.services.house_data_service import get_house_data_service
from app.services.roof.obstruction_service import get_roof_obstruction_service


class FakeRoofObstructionService:
    def analyze_obstructions(
        self,
        request: RoofObstructionRequest,
        house_data_service: object,
    ) -> RoofObstructionAnalysis:
        outline = RoofOutline(
            id=request.selected_roof_outline_ids[0],
            source="test",
            model_id="test-building-outline",
            bounding_box_pixels=BoundingBoxPixels(x_min=40, y_min=40, x_max=60, y_max=60),
            polygon_pixels=[[40, 40], [60, 40], [60, 60], [40, 60]],
            area_pixels=400,
            confidence=0.9,
        )
        return RoofObstructionAnalysis(
            status="analyzed",
            selected_roof=SelectedRoof(
                satellite_image_url=request.satellite_image_url,
                selected_roof_outline_ids=request.selected_roof_outline_ids,
                selected_roof_outlines=[outline],
                bounding_box_pixels=outline.bounding_box_pixels,
                area_pixels=outline.area_pixels,
            ),
            obstructions=[
                RoofObstruction(
                    id="obstruction-001",
                    class_name="chimney",
                    polygon_pixels=[[45, 45], [55, 45], [55, 55], [45, 55]],
                    bounding_box_pixels=BoundingBoxPixels(x_min=45, y_min=45, x_max=55, y_max=55),
                    area_pixels=100,
                    confidence=0.834,
                    source="rid_unet",
                    model_id="rid_unet_resnet34_best",
                )
            ],
            warnings=[],
        )


def test_roof_obstructions_route_returns_detection_contract() -> None:
    app.dependency_overrides[get_house_data_service] = lambda: object()
    app.dependency_overrides[get_roof_obstruction_service] = lambda: FakeRoofObstructionService()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/roof/obstructions",
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
    assert payload["obstructions"] == [
        {
            "id": "obstruction-001",
            "class_name": "chimney",
            "polygon_pixels": [[45, 45], [55, 45], [55, 55], [45, 55]],
            "bounding_box_pixels": {
                "x_min": 45,
                "y_min": 45,
                "x_max": 55,
                "y_max": 55,
            },
            "area_pixels": 100,
            "confidence": 0.834,
            "source": "rid_unet",
            "model_id": "rid_unet_resnet34_best",
        }
    ]
    assert payload["warnings"] == []
