import numpy as np
import pytest

from app.services.roof.rid_detector import (
    RID_CLASSES,
    RoofObstructionRuntimeError,
    detections_from_probabilities,
)


def test_detections_from_probabilities_returns_scaled_obstruction_polygons() -> None:
    probs = np.zeros((8, 8, len(RID_CLASSES)), dtype=np.float32)
    probs[..., RID_CLASSES.index("background")] = 1.0

    chimney_idx = RID_CLASSES.index("chimney")
    probs[1:5, 2:6, RID_CLASSES.index("background")] = 0.05
    probs[1:5, 2:6, chimney_idx] = 0.9

    shadow_idx = RID_CLASSES.index("shadow")
    probs[5:7, 5:7, RID_CLASSES.index("background")] = 0.05
    probs[5:7, 5:7, shadow_idx] = 0.95

    detections = detections_from_probabilities(
        probs,
        original_width=80,
        original_height=40,
        min_polygon_area_pixels=1,
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_name == "chimney"
    assert detection.confidence == 0.9
    assert detection.area_pixels == 450
    assert min(point[0] for point in detection.polygon_pixels) == 20
    assert max(point[0] for point in detection.polygon_pixels) == 50
    assert min(point[1] for point in detection.polygon_pixels) == 5
    assert max(point[1] for point in detection.polygon_pixels) == 20


def test_detections_from_probabilities_filters_tiny_polygons() -> None:
    probs = np.zeros((8, 8, len(RID_CLASSES)), dtype=np.float32)
    probs[..., RID_CLASSES.index("background")] = 1.0
    probs[1:3, 1:3, RID_CLASSES.index("background")] = 0.05
    probs[1:3, 1:3, RID_CLASSES.index("window")] = 0.9

    detections = detections_from_probabilities(
        probs,
        original_width=80,
        original_height=80,
        min_polygon_area_pixels=2,
    )

    assert detections == []


def test_detections_from_probabilities_rejects_malformed_model_output() -> None:
    with pytest.raises(RoofObstructionRuntimeError):
        detections_from_probabilities(
            np.zeros((8, 8, 3), dtype=np.float32),
            original_width=80,
            original_height=80,
            min_polygon_area_pixels=1,
        )
