from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Protocol

from fastapi import HTTPException
from PIL import Image

from app.core.config import settings
from app.models.roof import (
    BoundingBoxPixels,
    RoofObstruction,
    RoofObstructionAnalysis,
    RoofObstructionRequest,
    RoofSelectionResponse,
    SelectedRoof,
)
from app.services.house_data_service import HouseDataService
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service


RID_OBSTRUCTION_CLASSES = {"pvmodule", "dormer", "window", "ladder", "chimney"}
RID_OBSTRUCTION_MODEL_ID = "rid_unet_resnet34_best"
RID_OBSTRUCTION_SOURCE = "rid_unet"


class RoofObstructionRuntimeError(RuntimeError):
    pass


class ObstructionRuntime(Protocol):
    def detect_obstructions(self, image_path: Path) -> list[dict[str, Any]]:
        pass


class RidSubprocessRuntime:
    def __init__(
        self,
        python_executable: str,
        timeout_seconds: float,
        script_path: Path | None = None,
    ) -> None:
        self.python_executable = python_executable
        self.timeout_seconds = timeout_seconds
        self.script_path = script_path or Path(__file__).with_name("rid_runtime_cli.py")

    def detect_obstructions(self, image_path: Path) -> list[dict[str, Any]]:
        try:
            completed = subprocess.run(
                [self.python_executable, str(self.script_path), str(image_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RoofObstructionRuntimeError(
                f"RID runtime Python executable was not found: {self.python_executable}."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RoofObstructionRuntimeError("RID obstruction detection timed out.") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown runtime error"
            raise RoofObstructionRuntimeError(f"RID obstruction detection failed: {detail}")

        json_line = self._last_json_line(completed.stdout)
        if json_line is None:
            raise RoofObstructionRuntimeError("RID obstruction detection returned malformed JSON.")

        try:
            payload = json.loads(json_line)
        except ValueError as exc:
            raise RoofObstructionRuntimeError("RID obstruction detection returned malformed JSON.") from exc

        obstructions = payload.get("obstructions")
        if not isinstance(obstructions, list):
            raise RoofObstructionRuntimeError("RID obstruction detection returned malformed data.")
        return [item for item in obstructions if isinstance(item, dict)]

    def _last_json_line(self, output: str) -> str | None:
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
        return None


class RoofObstructionService:
    def __init__(
        self,
        roof_analysis_service: RoofAnalysisService,
        runtime: ObstructionRuntime,
        *,
        crop_padding_pixels: int = 8,
        min_confidence: float = 0.5,
        min_area_pixels: float = 50.0,
    ) -> None:
        self.roof_analysis_service = roof_analysis_service
        self.runtime = runtime
        self.crop_padding_pixels = crop_padding_pixels
        self.min_confidence = min_confidence
        self.min_area_pixels = min_area_pixels

    def analyze_obstructions(
        self,
        request: RoofObstructionRequest,
        house_data_service: HouseDataService,
    ) -> RoofObstructionAnalysis:
        selection = self.roof_analysis_service.select_roof(request, house_data_service)
        asset_id = self.roof_analysis_service.asset_id_from_overhead_url(request.satellite_image_url)
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid satellite image URL.")

        image_path = house_data_service.overhead_image_path(asset_id)
        crop = self._crop_selected_roof(image_path, selection)

        try:
            raw_obstructions = self.runtime.detect_obstructions(crop.path)
        except RoofObstructionRuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        obstructions = self._map_and_filter_obstructions(
            raw_obstructions,
            selected_roof=selection.selected_roof,
            offset_x=crop.offset_x,
            offset_y=crop.offset_y,
            crop_width=crop.width,
            crop_height=crop.height,
        )

        return RoofObstructionAnalysis(
            status="analyzed",
            selected_roof=selection.selected_roof,
            obstructions=obstructions,
            warnings=[],
        )

    def _crop_selected_roof(
        self,
        image_path: Path,
        selection: RoofSelectionResponse,
    ) -> "_RoofCrop":
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                box = selection.selected_roof.bounding_box_pixels
                left = max(box.x_min - self.crop_padding_pixels, 0)
                top = max(box.y_min - self.crop_padding_pixels, 0)
                right = min(box.x_max + self.crop_padding_pixels + 1, width)
                bottom = min(box.y_max + self.crop_padding_pixels + 1, height)
                if right <= left or bottom <= top:
                    raise ValueError("Selected roof crop has no pixel area.")

                crop_image = image.crop((left, top, right, bottom)).convert("RGB")
                crop_dir = image_path.parent / "roof_obstruction_crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                selected_ids = "-".join(selection.selected_roof.selected_roof_outline_ids)
                crop_path = crop_dir / f"{selected_ids}_{left}_{top}_{right}_{bottom}.png"
                crop_image.save(crop_path, format="PNG")
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Selected roof image could not be cropped.") from exc

        return _RoofCrop(
            path=crop_path,
            offset_x=left,
            offset_y=top,
            width=right - left,
            height=bottom - top,
        )

    def _map_and_filter_obstructions(
        self,
        raw_obstructions: list[dict[str, Any]],
        *,
        selected_roof: SelectedRoof,
        offset_x: int,
        offset_y: int,
        crop_width: int,
        crop_height: int,
    ) -> list[RoofObstruction]:
        obstructions: list[RoofObstruction] = []
        for raw in raw_obstructions:
            class_name = raw.get("class_name") or raw.get("class")
            if class_name not in RID_OBSTRUCTION_CLASSES:
                continue

            confidence = self._optional_float(raw.get("confidence"))
            if confidence is not None and confidence < self.min_confidence:
                continue

            crop_polygon = self._normalize_crop_polygon(
                raw.get("polygon_pixels"),
                width=crop_width,
                height=crop_height,
            )
            if len(crop_polygon) < 3:
                continue

            full_polygon = [[x + offset_x, y + offset_y] for x, y in crop_polygon]
            area_pixels = self._optional_float(raw.get("area_pixels"))
            if area_pixels is None:
                area_pixels = self._polygon_area(full_polygon)
            if area_pixels < self.min_area_pixels:
                continue
            if not self._polygon_centroid_is_in_selected_roof(full_polygon, selected_roof):
                continue

            obstructions.append(
                RoofObstruction(
                    id=f"obstruction-{len(obstructions) + 1:03d}",
                    class_name=str(class_name),
                    polygon_pixels=full_polygon,
                    bounding_box_pixels=self._bounding_box(full_polygon),
                    area_pixels=area_pixels,
                    confidence=confidence,
                    source=RID_OBSTRUCTION_SOURCE,
                    model_id=RID_OBSTRUCTION_MODEL_ID,
                )
            )

        return obstructions

    def _normalize_crop_polygon(
        self,
        raw_polygon: Any,
        *,
        width: int,
        height: int,
    ) -> list[list[int]]:
        if not isinstance(raw_polygon, list):
            return []

        polygon: list[list[int]] = []
        for point in raw_polygon:
            if not isinstance(point, list | tuple) or len(point) < 2:
                continue
            try:
                x = min(max(int(round(float(point[0]))), 0), width - 1)
                y = min(max(int(round(float(point[1]))), 0), height - 1)
            except (TypeError, ValueError):
                continue
            if not polygon or polygon[-1] != [x, y]:
                polygon.append([x, y])

        if len(polygon) > 1 and polygon[0] == polygon[-1]:
            polygon.pop()
        return polygon

    def _polygon_centroid_is_in_selected_roof(
        self,
        polygon: list[list[int]],
        selected_roof: SelectedRoof,
    ) -> bool:
        centroid = self._centroid(polygon)
        return any(
            self._point_in_polygon(centroid, outline.polygon_pixels)
            for outline in selected_roof.selected_roof_outlines
        )

    def _point_in_polygon(self, point: tuple[float, float], polygon: list[list[int]]) -> bool:
        x, y = point
        inside = False
        previous = polygon[-1]
        for current in polygon:
            xi, yi = current
            xj, yj = previous
            intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi
            if intersects:
                inside = not inside
            previous = current
        return inside

    def _centroid(self, polygon: list[list[int]]) -> tuple[float, float]:
        return (
            sum(point[0] for point in polygon) / len(polygon),
            sum(point[1] for point in polygon) / len(polygon),
        )

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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


class _RoofCrop:
    def __init__(self, path: Path, offset_x: int, offset_y: int, width: int, height: int) -> None:
        self.path = path
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.width = width
        self.height = height


def get_roof_obstruction_service() -> RoofObstructionService:
    runtime = RidSubprocessRuntime(
        python_executable=settings.rid_runtime_python,
        timeout_seconds=settings.rid_runtime_timeout_seconds,
    )
    return RoofObstructionService(
        get_roof_analysis_service(),
        runtime,
        crop_padding_pixels=settings.roof_obstruction_crop_padding_pixels,
        min_confidence=settings.roof_obstruction_min_confidence,
        min_area_pixels=settings.roof_obstruction_min_area_pixels,
    )
