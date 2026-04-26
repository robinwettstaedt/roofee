from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from app.models.roof import BoundingBoxPixels, RoofObstructionRequest, RoofOutline
from app.services.roof.obstruction_service import RoofObstructionService
from app.services.roof.rid_detector import RawObstructionDetection
from app.services.roof.roof_analysis_service import RoofAnalysisService


class FakeBuildingOutlineService:
    def detect_outlines(self, image_path: Path) -> list[RoofOutline]:
        return [
            RoofOutline(
                id="detected-roof-1",
                source="test",
                model_id="test-building-outline",
                bounding_box_pixels=BoundingBoxPixels(x_min=0, y_min=0, x_max=40, y_max=40),
                polygon_pixels=[[0, 0], [40, 0], [40, 40], [0, 40]],
                area_pixels=1600,
                confidence=0.4,
            ),
            RoofOutline(
                id="detected-roof-2",
                source="test",
                model_id="test-building-outline",
                bounding_box_pixels=BoundingBoxPixels(x_min=45, y_min=45, x_max=55, y_max=55),
                polygon_pixels=[[45, 45], [55, 45], [55, 55], [45, 55]],
                area_pixels=100,
                confidence=0.85,
            ),
        ]


class FakeHouseDataService:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    def overhead_image_path(self, asset_id: str) -> Path:
        assert asset_id == "test-asset"
        return self.image_path


class FakeRidDetector:
    def __init__(self) -> None:
        self.image_path: Path | None = None

    def detect(self, image_path: Path) -> list[RawObstructionDetection]:
        self.image_path = image_path
        return [
            RawObstructionDetection(
                class_name="chimney",
                polygon_pixels=[[5, 5], [15, 5], [15, 15], [5, 15]],
                area_pixels=100,
                confidence=0.834,
            ),
            RawObstructionDetection(
                class_name="window",
                polygon_pixels=[[20, 20], [28, 20], [28, 28], [20, 28]],
                area_pixels=64,
                confidence=0.2,
            ),
            RawObstructionDetection(
                class_name="dormer",
                polygon_pixels=[[30, 30], [33, 30], [33, 33], [30, 33]],
                area_pixels=9,
                confidence=0.9,
            ),
            RawObstructionDetection(
                class_name="tree",
                polygon_pixels=[[5, 5], [15, 5], [15, 15], [5, 15]],
                area_pixels=100,
                confidence=0.9,
            ),
        ]


def test_roof_obstruction_service_maps_crop_coordinates_to_full_image(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    detector = FakeRidDetector()

    response = RoofObstructionService(
        RoofAnalysisService(FakeBuildingOutlineService()),
        detector,
        crop_padding_pixels=5,
        min_confidence=0.5,
        min_area_pixels=50,
    ).analyze_obstructions(
        RoofObstructionRequest(
            satellite_image_url="/api/house-assets/test-asset/overhead.png",
            selected_roof_outline_ids=["roof-002"],
        ),
        FakeHouseDataService(image_path),
    )

    assert detector.image_path is not None
    with Image.open(detector.image_path) as crop:
        assert crop.size == (21, 21)

    assert response.status == "analyzed"
    assert response.selected_roof.selected_roof_outline_ids == ["roof-002"]
    assert len(response.obstructions) == 1
    obstruction = response.obstructions[0]
    assert obstruction.id == "obstruction-001"
    assert obstruction.class_name == "chimney"
    assert obstruction.polygon_pixels == [[45, 45], [55, 45], [55, 55], [45, 55]]
    assert obstruction.bounding_box_pixels.model_dump() == {
        "x_min": 45,
        "y_min": 45,
        "x_max": 55,
        "y_max": 55,
    }
    assert obstruction.area_pixels == 100
    assert obstruction.confidence == 0.834
    assert obstruction.source == "rid_unet"
    assert obstruction.model_id == "rid_unet_resnet34_best"


def test_roof_obstruction_service_rejects_invalid_selected_roof_ids(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)

    with pytest.raises(HTTPException) as exc:
        RoofObstructionService(
            RoofAnalysisService(FakeBuildingOutlineService()),
            FakeRidDetector(),
        ).analyze_obstructions(
            RoofObstructionRequest(
                satellite_image_url="/api/house-assets/test-asset/overhead.png",
                selected_roof_outline_ids=["roof-999"],
            ),
            FakeHouseDataService(image_path),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Selected roof outline IDs were not found: roof-999."
