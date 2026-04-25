from __future__ import annotations

from app.models.recommendation import HouseData
from app.models.roof import RoofAnalysis, RoofAnalysisStatus
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
                roof_planes=roof_planes,
                warnings=["Roof outline analysis skipped: overhead image asset was not available."],
            )

        try:
            image_path = house_data_service.overhead_image_path(asset_id)
            roof_outlines = self.building_outline_service.detect_outlines(image_path)
        except BuildingOutlineUnavailableError as exc:
            return RoofAnalysis(
                status=RoofAnalysisStatus.SKIPPED,
                roof_planes=roof_planes,
                warnings=[str(exc)],
            )

        if not roof_outlines:
            warnings.append("Roof outline analysis did not detect any building masks.")
            return RoofAnalysis(
                status=RoofAnalysisStatus.SKIPPED,
                roof_planes=roof_planes,
                warnings=warnings,
            )

        return RoofAnalysis(
            status=RoofAnalysisStatus.ANALYZED,
            roof_outlines=roof_outlines,
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


def get_roof_analysis_service() -> RoofAnalysisService:
    return RoofAnalysisService(get_building_outline_service())
