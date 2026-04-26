from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings
from app.models.roof import BoundingBoxPixels, RoofOutline


DEFAULT_BUILDING_OUTLINE_MODEL_ID = "keremberke/yolov8m-building-segmentation"
DEFAULT_BUILDING_OUTLINE_MODEL_FILE = "best.pt"


class BuildingOutlineUnavailableError(RuntimeError):
    pass


class BuildingOutlineService:
    def __init__(
        self,
        model_id: str = DEFAULT_BUILDING_OUTLINE_MODEL_ID,
        model_filename: str = DEFAULT_BUILDING_OUTLINE_MODEL_FILE,
        local_model_path: Path | None = None,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        max_detections: int = 1000,
    ) -> None:
        self.model_id = model_id
        self.model_filename = model_filename
        self.local_model_path = local_model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self._model: Any | None = None

    def detect_outline(self, image_path: Path) -> RoofOutline | None:
        outlines = self.detect_outlines(image_path)
        return self._outline_nearest_image_center(outlines, image_path)

    def detect_outlines(self, image_path: Path) -> list[RoofOutline]:
        if not image_path.is_file():
            raise BuildingOutlineUnavailableError(f"Roof overhead image not found: {image_path}")

        with Image.open(image_path) as image:
            width, height = image.size

        return self._detect_outlines(str(image_path), width=width, height=height)

    def detect_outlines_from_image(self, image: Any) -> list[RoofOutline]:
        height, width = image.shape[:2]
        return self._detect_outlines(image, width=width, height=height)

    def _detect_outlines(self, image: Any, *, width: int, height: int) -> list[RoofOutline]:
        model = self._load_model()
        results = model.predict(
            image,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            max_det=self.max_detections,
            verbose=False,
        )
        if not results:
            return []

        return self._outlines_from_result(results[0], width=width, height=height)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from huggingface_hub import hf_hub_download
            from ultralytics import YOLO
        except ImportError as exc:
            raise BuildingOutlineUnavailableError(
                "Roof outline analysis requires the backend vision extra: "
                'pip install -e ".[vision]".'
            ) from exc

        weights_path = (
            str(self.local_model_path)
            if self.local_model_path is not None and self.local_model_path.is_file()
            else hf_hub_download(repo_id=self.model_id, filename=self.model_filename)
        )
        self._model = YOLO(weights_path)
        return self._model

    def _outlines_from_result(
        self,
        result: Any,
        *,
        width: int,
        height: int,
    ) -> list[RoofOutline]:
        masks = getattr(result, "masks", None)
        polygons = getattr(masks, "xy", None)
        if not polygons:
            return []

        confidences = self._box_confidences(result)
        outlines: list[RoofOutline] = []
        for index, raw_polygon in enumerate(polygons):
            polygon = self._normalize_polygon(raw_polygon, width=width, height=height)
            if len(polygon) < 3:
                continue

            area_pixels = self._polygon_area(polygon)
            if area_pixels <= 0:
                continue

            confidence = confidences[index] if index < len(confidences) else None
            outline = RoofOutline(
                id=f"detected-roof-{index + 1}",
                source="huggingface_yolov8",
                model_id=self.model_id,
                bounding_box_pixels=self._bounding_box(polygon),
                polygon_pixels=polygon,
                area_pixels=area_pixels,
                confidence=confidence,
            )
            outlines.append(outline)

        return outlines

    def _outline_nearest_image_center(
        self,
        outlines: list[RoofOutline],
        image_path: Path,
    ) -> RoofOutline | None:
        if not outlines:
            return None

        with Image.open(image_path) as image:
            width, height = image.size
        target_pixel = (width / 2, height / 2)
        return min(
            outlines,
            key=lambda outline: self._centroid_distance(outline.polygon_pixels, target_pixel),
        )

    def _box_confidences(self, result: Any) -> list[float]:
        boxes = getattr(result, "boxes", None)
        raw_confidences = getattr(boxes, "conf", None)
        if raw_confidences is None:
            return []

        try:
            values = raw_confidences.detach().cpu().numpy().tolist()
        except AttributeError:
            try:
                values = raw_confidences.cpu().numpy().tolist()
            except AttributeError:
                values = list(raw_confidences)

        return [round(float(value), 3) for value in values]

    def _normalize_polygon(self, raw_polygon: Any, *, width: int, height: int) -> list[list[int]]:
        try:
            points = raw_polygon.tolist()
        except AttributeError:
            points = raw_polygon

        polygon: list[list[int]] = []
        for point in points:
            if len(point) < 2:
                continue
            x = min(max(int(round(float(point[0]))), 0), width - 1)
            y = min(max(int(round(float(point[1]))), 0), height - 1)
            if not polygon or polygon[-1] != [x, y]:
                polygon.append([x, y])

        if len(polygon) > 1 and polygon[0] == polygon[-1]:
            polygon.pop()
        return polygon

    def _polygon_area(self, polygon: list[list[int]]) -> float:
        area = 0.0
        for index, point in enumerate(polygon):
            next_point = polygon[(index + 1) % len(polygon)]
            area += point[0] * next_point[1] - next_point[0] * point[1]
        return round(abs(area) / 2.0, 2)

    def _bounding_box(self, polygon: list[list[int]]) -> BoundingBoxPixels:
        x_values = [point[0] for point in polygon]
        y_values = [point[1] for point in polygon]
        return BoundingBoxPixels(
            x_min=min(x_values),
            y_min=min(y_values),
            x_max=max(x_values),
            y_max=max(y_values),
        )

    def _centroid_distance(
        self,
        polygon: list[list[int]],
        target_pixel: tuple[float, float],
    ) -> float:
        centroid_x = sum(point[0] for point in polygon) / len(polygon)
        centroid_y = sum(point[1] for point in polygon) / len(polygon)
        return ((centroid_x - target_pixel[0]) ** 2 + (centroid_y - target_pixel[1]) ** 2) ** 0.5


def get_building_outline_service() -> BuildingOutlineService:
    return BuildingOutlineService(
        model_id=settings.building_outline_model_id,
        model_filename=settings.building_outline_model_file,
        local_model_path=settings.building_outline_model_path,
    )
