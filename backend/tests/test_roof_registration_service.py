from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from PIL import Image

from app.models.roof import (
    BoundingBoxPixels,
    OrthographicWorldBounds,
    RoofOutline,
    RoofRegistrationRequest,
    TopDownRenderMetadata,
)
from app.services.roof.registration_service import RoofRegistrationService
from app.services.roof.roof_analysis_service import RoofAnalysisService


class FakeBuildingOutlineService:
    def __init__(self, outline: RoofOutline | None = None) -> None:
        self.outline = outline or RoofOutline(
            id="detected-roof-1",
            source="test",
            model_id="test-building-outline",
            bounding_box_pixels=BoundingBoxPixels(x_min=100, y_min=120, x_max=320, y_max=300),
            polygon_pixels=[[100, 120], [300, 110], [320, 280], [90, 300]],
            area_pixels=37750,
            confidence=0.9,
        )

    def detect_outlines(self, image_path: Path) -> list[RoofOutline]:
        return [self.outline]

    def detect_outlines_from_image(self, image: np.ndarray) -> list[RoofOutline]:
        return []


class FakeHouseDataService:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    def overhead_image_path(self, asset_id: str) -> Path:
        assert asset_id == "test-asset"
        return self.image_path


class FakeMultiOutlineBuildingService:
    def detect_outlines(self, image_path: Path) -> list[RoofOutline]:
        return [
            RoofOutline(
                id="detected-roof-1",
                source="test",
                model_id="test-building-outline",
                bounding_box_pixels=BoundingBoxPixels(x_min=90, y_min=120, x_max=205, y_max=300),
                polygon_pixels=[[100, 120], [205, 115], [200, 290], [90, 300]],
                area_pixels=20000,
                confidence=0.9,
            ),
            RoofOutline(
                id="detected-roof-2",
                source="test",
                model_id="test-building-outline",
                bounding_box_pixels=BoundingBoxPixels(x_min=200, y_min=110, x_max=320, y_max=290),
                polygon_pixels=[[205, 115], [300, 110], [320, 280], [200, 290]],
                area_pixels=17750,
                confidence=0.9,
            ),
        ]

    def detect_outlines_from_image(self, image: np.ndarray) -> list[RoofOutline]:
        return []


def test_roof_registration_service_recovers_similarity_transform_and_maps_polygon(
    tmp_path: Path,
) -> None:
    satellite_image, render_image, matrix = _synthetic_registration_pair()
    satellite_path = tmp_path / "overhead.png"
    Image.fromarray(cv2.cvtColor(satellite_image, cv2.COLOR_BGR2RGB)).save(satellite_path)
    _, encoded_render = cv2.imencode(".png", render_image)

    response = RoofRegistrationService(
        RoofAnalysisService(FakeBuildingOutlineService()),
    ).register_roof(
        _registration_request(),
        bytes(encoded_render),
        FakeHouseDataService(satellite_path),
    )

    assert response.status == "registered"
    assert response.transform is not None
    assert response.transform.algorithm == "orb"
    assert response.quality.inliers >= 20
    assert response.quality.confidence > 0.7

    expected_polygon = _map_polygon(
        [[100, 120], [300, 110], [320, 280], [90, 300]],
        matrix,
    )
    for actual, expected in zip(response.mapped_roof_polygon_pixels, expected_polygon, strict=True):
        assert actual[0] == pytest.approx(expected[0], abs=3)
        assert actual[1] == pytest.approx(expected[1], abs=3)


def test_roof_registration_service_returns_failed_status_for_low_feature_images(
    tmp_path: Path,
) -> None:
    satellite_path = tmp_path / "overhead.png"
    Image.new("RGB", (256, 256), "white").save(satellite_path)
    top_down = Image.new("RGB", (512, 512), "white")
    top_down_path = tmp_path / "render.png"
    top_down.save(top_down_path)

    response = RoofRegistrationService(
        RoofAnalysisService(FakeBuildingOutlineService()),
    ).register_roof(
        _registration_request(width=512, height=512),
        top_down_path.read_bytes(),
        FakeHouseDataService(satellite_path),
    )

    assert response.status == "failed"
    assert response.transform is None
    assert response.mapped_roof_polygon_pixels == []
    assert response.quality.good_matches == 0
    assert any("too few feature matches" in warning or "descriptors" in warning for warning in response.warnings)


def test_roof_registration_service_preserves_each_selected_roof_outline(
    tmp_path: Path,
) -> None:
    satellite_image, render_image, _matrix = _synthetic_registration_pair()
    satellite_path = tmp_path / "overhead.png"
    Image.fromarray(cv2.cvtColor(satellite_image, cv2.COLOR_BGR2RGB)).save(satellite_path)
    _, encoded_render = cv2.imencode(".png", render_image)

    response = RoofRegistrationService(
        RoofAnalysisService(FakeMultiOutlineBuildingService()),
    ).register_roof(
        _registration_request(selected_ids=["roof-001", "roof-002"]),
        bytes(encoded_render),
        FakeHouseDataService(satellite_path),
    )

    assert response.status == "registered"
    assert [outline.id for outline in response.mapped_roof_outlines] == ["roof-001", "roof-002"]
    assert all(outline.render_polygon_pixels for outline in response.mapped_roof_outlines)
    assert all(outline.model_polygon for outline in response.mapped_roof_outlines)


def test_roof_registration_service_rejects_invalid_selected_roof_ids(tmp_path: Path) -> None:
    satellite_path = tmp_path / "overhead.png"
    Image.new("RGB", (256, 256), "white").save(satellite_path)
    top_down_path = tmp_path / "render.png"
    Image.new("RGB", (512, 512), "white").save(top_down_path)

    request = _registration_request(selected_ids=["roof-999"], width=512, height=512)
    with pytest.raises(HTTPException) as exc:
        RoofRegistrationService(
            RoofAnalysisService(FakeBuildingOutlineService()),
        ).register_roof(
            request,
            top_down_path.read_bytes(),
            FakeHouseDataService(satellite_path),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Selected roof outline IDs were not found: roof-999."


def _registration_request(
    *,
    selected_ids: list[str] | None = None,
    width: int = 620,
    height: int = 620,
) -> RoofRegistrationRequest:
    return RoofRegistrationRequest(
        satellite_image_url="/api/house-assets/test-asset/overhead.png",
        selected_roof_outline_ids=selected_ids or ["roof-001"],
        top_down_render_metadata=TopDownRenderMetadata(
            render_width=width,
            render_height=height,
            orthographic_world_bounds=OrthographicWorldBounds(
                x_min=-20,
                x_max=20,
                z_min=-20,
                z_max=20,
                y_min=0,
                y_max=12,
            ),
            model_orientation={
                "up_axis": "y",
                "camera_direction": [0, -1, 0],
                "camera_up": [0, 0, -1],
            },
        ),
    )


def _synthetic_registration_pair() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(123)
    satellite = np.zeros((420, 420, 3), np.uint8)
    roof_polygon = np.array([[100, 120], [300, 110], [320, 280], [90, 300]], np.int32)
    cv2.fillPoly(satellite, [roof_polygon], (80, 80, 80))
    cv2.polylines(satellite, [roof_polygon], True, (240, 240, 240), 3)

    for index in range(180):
        x = int(rng.integers(40, 380))
        y = int(rng.integers(40, 380))
        radius = int(rng.integers(2, 7))
        color = tuple(int(channel) for channel in rng.integers(100, 255, 3))
        if index % 3 == 0:
            cv2.circle(satellite, (x, y), radius, color, -1)
        elif index % 3 == 1:
            cv2.rectangle(satellite, (x - radius, y - radius), (x + radius, y + radius), color, -1)
        else:
            cv2.line(satellite, (x - radius, y), (x + radius, y), color, 2)

    angle = math.radians(13)
    scale = 1.18
    matrix = np.array(
        [
            [scale * math.cos(angle), -scale * math.sin(angle), 70],
            [scale * math.sin(angle), scale * math.cos(angle), 45],
        ],
        np.float32,
    )
    render = cv2.warpAffine(
        satellite,
        matrix,
        (620, 620),
        flags=cv2.INTER_LINEAR,
        borderValue=(0, 0, 0),
    )
    return satellite, render, matrix


def _map_polygon(polygon: list[list[int]], matrix: np.ndarray) -> list[list[float]]:
    points = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    mapped = cv2.transform(points, matrix).reshape(-1, 2)
    return [[float(x), float(y)] for x, y in mapped]
