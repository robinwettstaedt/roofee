from pathlib import Path

import numpy as np
from PIL import Image

from app.models.recommendation import (
    Google3DTilesData,
    HouseData,
    LatLng,
    SolarBuildingData,
    SolarRoofSegment,
)
from app.services.roof.building_outline_service import (
    BuildingOutlineService,
    BuildingOutlineUnavailableError,
)
from app.services.roof.roof_analysis_service import RoofAnalysisService


class FakeTensor:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def detach(self) -> "FakeTensor":
        return self

    def cpu(self) -> "FakeTensor":
        return self

    def numpy(self) -> np.ndarray:
        return np.array(self.values)


class FakeBoxes:
    def __init__(self, confidences: list[float]) -> None:
        self.conf = FakeTensor(confidences)


class FakeMasks:
    def __init__(self, polygons: list[np.ndarray]) -> None:
        self.xy = polygons


class FakeResult:
    def __init__(self, polygons: list[np.ndarray], confidences: list[float]) -> None:
        self.masks = FakeMasks(polygons)
        self.boxes = FakeBoxes(confidences)


class FakeModel:
    def predict(self, *args: object, **kwargs: object) -> list[FakeResult]:
        return [
            FakeResult(
                polygons=[
                    np.array([[0, 0], [40, 0], [40, 40], [0, 40]]),
                    np.array([[45, 45], [55, 45], [55, 55], [45, 55]]),
                ],
                confidences=[0.4, 0.85],
            )
        ]


class FakeBuildingOutlineService(BuildingOutlineService):
    def _load_model(self) -> FakeModel:
        return FakeModel()


class UnavailableBuildingOutlineService(BuildingOutlineService):
    def detect_outlines(self, image_path: Path):
        raise BuildingOutlineUnavailableError("vision dependency missing")


class FakeHouseDataService:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    def overhead_image_path(self, asset_id: str) -> Path:
        assert asset_id == "test-asset"
        return self.image_path


def test_building_outline_service_returns_all_yolo_masks(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)

    outlines = FakeBuildingOutlineService().detect_outlines(image_path)

    assert len(outlines) == 2
    assert outlines[0].model_id == "keremberke/yolov8m-building-segmentation"
    assert outlines[0].polygon_pixels == [[0, 0], [40, 0], [40, 40], [0, 40]]
    assert outlines[0].area_pixels == 1600
    assert outlines[0].confidence == 0.4
    assert outlines[1].polygon_pixels == [[45, 45], [55, 45], [55, 55], [45, 55]]
    assert outlines[1].area_pixels == 100
    assert outlines[1].confidence == 0.85


def test_building_outline_service_can_select_mask_nearest_image_center(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)

    outline = FakeBuildingOutlineService().detect_outline(image_path)

    assert outline is not None
    assert outline.polygon_pixels == [[45, 45], [55, 45], [55, 55], [45, 55]]


def test_roof_analysis_service_returns_roof_planes_and_outline(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    center = LatLng(latitude=52.52, longitude=13.405)
    house_data = HouseData(
        status="fetched",
        provider="google",
        location=center,
        solar_building=SolarBuildingData(
            center=center,
            roof_segments=[
                SolarRoofSegment(
                    center=center,
                    pitch_degrees=35,
                    azimuth_degrees=180,
                    area_meters2=42,
                )
            ],
        ),
        overhead_image_url="/api/house-assets/test-asset/overhead.png",
        tiles_3d=Google3DTilesData(root_url="/api/google-3d-tiles/root.json", origin=center),
    )

    analysis = RoofAnalysisService(FakeBuildingOutlineService()).analyze_house(
        house_data,
        FakeHouseDataService(image_path),
    )

    assert analysis.status == "analyzed"
    assert len(analysis.roof_outlines) == 2
    assert analysis.roof_planes[0]["pitch_degrees"] == 35
    assert analysis.roof_planes[0]["azimuth_degrees"] == 180


def test_roof_analysis_service_skips_when_outline_dependency_is_missing(tmp_path: Path) -> None:
    image_path = tmp_path / "overhead.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    center = LatLng(latitude=52.52, longitude=13.405)
    house_data = HouseData(
        status="fetched",
        provider="google",
        location=center,
        solar_building=SolarBuildingData(center=center),
        overhead_image_url="/api/house-assets/test-asset/overhead.png",
        tiles_3d=Google3DTilesData(root_url="/api/google-3d-tiles/root.json", origin=center),
    )

    analysis = RoofAnalysisService(UnavailableBuildingOutlineService()).analyze_house(
        house_data,
        FakeHouseDataService(image_path),
    )

    assert analysis.status == "skipped"
    assert analysis.roof_outlines == []
    assert analysis.warnings == ["vision dependency missing"]
