from __future__ import annotations

from fastapi import HTTPException

from app.models.recommendation import HouseData
from app.models.roof import (
    BoundingBoxPixels,
    RoofAnalysis,
    RoofAnalysisStatus,
    RoofOutline,
    RoofSelectionRequest,
    RoofSelectionResponse,
    SelectedRoof,
)
from app.services.house_data_service import HouseDataService
from app.services.roof.building_outline_service import (
    BuildingOutlineService,
    BuildingOutlineUnavailableError,
    get_building_outline_service,
)


class RoofAnalysisService:
    def __init__(self, building_outline_service: BuildingOutlineService) -> None:
        self.building_outline_service = building_outline_service

    def analyze_house(self, house_data: HouseData, house_data_service: HouseDataService) -> RoofAnalysis:
        roof_planes = [segment.model_dump(mode="json") for segment in house_data.solar_building.roof_segments]
        warnings: list[str] = []

        asset_id = self._asset_id_from_overhead_url(house_data.overhead_image_url)
        if asset_id is None:
            return RoofAnalysis(
                status=RoofAnalysisStatus.SKIPPED,
                satellite_image_url=house_data.overhead_image_url,
                roof_planes=roof_planes,
                warnings=["Roof outline analysis skipped: overhead image asset was not available."],
            )

        try:
            image_path = house_data_service.overhead_image_path(asset_id)
            roof_outlines = self.building_outline_service.detect_outlines(image_path)
        except BuildingOutlineUnavailableError as exc:
            return RoofAnalysis(
                status=RoofAnalysisStatus.SKIPPED,
                satellite_image_url=house_data.overhead_image_url,
                roof_planes=roof_planes,
                warnings=[str(exc)],
            )

        if not roof_outlines:
            warnings.append("Roof outline analysis did not detect any building masks.")
            return RoofAnalysis(
                status=RoofAnalysisStatus.SKIPPED,
                satellite_image_url=house_data.overhead_image_url,
                roof_planes=roof_planes,
                warnings=warnings,
            )

        return RoofAnalysis(
            status=RoofAnalysisStatus.ANALYZED,
            satellite_image_url=house_data.overhead_image_url,
            roof_outlines=self._assign_stable_outline_ids(roof_outlines),
            roof_planes=roof_planes,
            warnings=warnings,
        )

    def _asset_id_from_overhead_url(self, overhead_image_url: str) -> str | None:
        parts = overhead_image_url.strip("/").split("/")
        if len(parts) != 4:
            return None
        if parts[0] != "api" or parts[1] != "house-assets" or parts[3] != "overhead.png":
            return None
        return parts[2] or None

    def select_roof(
        self,
        request: RoofSelectionRequest,
        house_data_service: HouseDataService,
    ) -> RoofSelectionResponse:
        asset_id = self._asset_id_from_overhead_url(request.satellite_image_url)
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid satellite image URL.")

        try:
            image_path = house_data_service.overhead_image_path(asset_id)
            roof_outlines = self._assign_stable_outline_ids(
                self.building_outline_service.detect_outlines(image_path)
            )
        except BuildingOutlineUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        outlines_by_id = {outline.id: outline for outline in roof_outlines}
        selected_ids = list(dict.fromkeys(request.selected_roof_outline_ids))
        missing_ids = [outline_id for outline_id in selected_ids if outline_id not in outlines_by_id]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Selected roof outline IDs were not found: {', '.join(missing_ids)}.",
            )

        selected_outlines = [outlines_by_id[outline_id] for outline_id in selected_ids]
        if len(selected_outlines) > 1 and not self._bounding_boxes_are_connected(selected_outlines):
            raise HTTPException(
                status_code=400,
                detail="Selected roof outline bounding boxes must touch or overlap.",
            )

        combined_box = self._combined_bounding_box(selected_outlines)
        return RoofSelectionResponse(
            status="selected",
            selected_roof=SelectedRoof(
                satellite_image_url=request.satellite_image_url,
                selected_roof_outline_ids=selected_ids,
                selected_roof_outlines=selected_outlines,
                bounding_box_pixels=combined_box,
                area_pixels=sum(outline.area_pixels for outline in selected_outlines),
            ),
            warnings=[],
        )

    def _assign_stable_outline_ids(self, roof_outlines: list[RoofOutline]) -> list[RoofOutline]:
        sorted_outlines = sorted(
            roof_outlines,
            key=lambda outline: (
                outline.bounding_box_pixels.y_min,
                outline.bounding_box_pixels.x_min,
                outline.bounding_box_pixels.y_max,
                outline.bounding_box_pixels.x_max,
            ),
        )
        for index, outline in enumerate(sorted_outlines, start=1):
            outline.id = f"roof-{index:03d}"
        return sorted_outlines

    def _bounding_boxes_are_connected(
        self,
        roof_outlines: list[RoofOutline],
        touch_tolerance_pixels: int = 2,
    ) -> bool:
        visited = {0}
        queue = [0]
        while queue:
            current_index = queue.pop(0)
            current_box = roof_outlines[current_index].bounding_box_pixels
            for candidate_index, candidate in enumerate(roof_outlines):
                if candidate_index in visited:
                    continue
                if self._bounding_boxes_touch(
                    current_box,
                    candidate.bounding_box_pixels,
                    tolerance=touch_tolerance_pixels,
                ):
                    visited.add(candidate_index)
                    queue.append(candidate_index)
        return len(visited) == len(roof_outlines)

    def _bounding_boxes_touch(
        self,
        first: BoundingBoxPixels,
        second: BoundingBoxPixels,
        *,
        tolerance: int,
    ) -> bool:
        return not (
            first.x_max + tolerance < second.x_min
            or second.x_max + tolerance < first.x_min
            or first.y_max + tolerance < second.y_min
            or second.y_max + tolerance < first.y_min
        )

    def _combined_bounding_box(self, roof_outlines: list[RoofOutline]) -> BoundingBoxPixels:
        return BoundingBoxPixels(
            x_min=min(outline.bounding_box_pixels.x_min for outline in roof_outlines),
            y_min=min(outline.bounding_box_pixels.y_min for outline in roof_outlines),
            x_max=max(outline.bounding_box_pixels.x_max for outline in roof_outlines),
            y_max=max(outline.bounding_box_pixels.y_max for outline in roof_outlines),
        )


def get_roof_analysis_service() -> RoofAnalysisService:
    return RoofAnalysisService(get_building_outline_service())
