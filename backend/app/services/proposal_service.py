from __future__ import annotations

import json

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.models.recommendation import ProposalRequest, ProposalResponse, RecommendationValidationResponse
from app.models.roof import RoofAnalysis, RoofGeometryAnalysisRequest, RoofOutline
from app.services.house_data_service import HouseDataService
from app.services.location.google_3d_tiles_service import Google3DTilesService
from app.services.project_input_service import ProjectInputService, get_project_input_service
from app.services.pvgis_service import PvgisService, get_pvgis_service
from app.services.roof.geometry_pipeline_service import (
    RoofGeometryPipelineService,
    get_roof_geometry_pipeline_service,
)
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service


class ProposalService:
    def __init__(
        self,
        *,
        project_input_service: ProjectInputService,
        pvgis_service: PvgisService,
        roof_analysis_service: RoofAnalysisService,
        geometry_pipeline_service: RoofGeometryPipelineService,
    ) -> None:
        self.project_input_service = project_input_service
        self.pvgis_service = pvgis_service
        self.roof_analysis_service = roof_analysis_service
        self.geometry_pipeline_service = geometry_pipeline_service

    def create_proposal(
        self,
        request: ProposalRequest,
        model_file: UploadFile | None = None,
        *,
        house_data_service: HouseDataService,
        tiles_service: Google3DTilesService,
    ) -> ProposalResponse:
        recommendation = self._validated_recommendation(request, model_file)
        recommendation.house_data = house_data_service.fetch_house_data(
            request.picked_location.latitude,
            request.picked_location.longitude,
        )
        recommendation.solar_weather = self.pvgis_service.fetch_solar_weather(
            request.project.latitude,
            request.project.longitude,
        )

        roof_analysis = self.roof_analysis_service.analyze_house(
            recommendation.house_data,
            house_data_service,
        )
        selected_roof_id = self._pick_clicked_roof_id(roof_analysis, house_data_service)

        asset_id = self.roof_analysis_service.asset_id_from_overhead_url(
            recommendation.house_data.overhead_image_url
        )
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid overhead image URL.")

        self._cache_proposal_context(asset_id, request, recommendation, house_data_service)
        if model_file is not None:
            self._cache_uploaded_model(asset_id, model_file, house_data_service)

        geometry = self.geometry_pipeline_service.analyze_geometry(
            RoofGeometryAnalysisRequest(
                satellite_image_url=recommendation.house_data.overhead_image_url,
                selected_roof_outline_ids=[selected_roof_id],
                model_radius_m=request.model_radius_m,
                roof_edge_setback_m=request.roof_edge_setback_m,
                obstruction_buffer_m=request.obstruction_buffer_m,
            ),
            house_data_service=house_data_service,
            tiles_service=tiles_service,
        )

        # Do not return the detected 2D satellite candidates to the frontend in
        # the normal proposal flow. The backend has already used them internally.
        recommendation.roof_analysis = None

        warnings = [
            *recommendation.warnings,
            *recommendation.house_data.warnings,
            *roof_analysis.warnings,
            *geometry.warnings,
        ]
        return ProposalResponse(
            status="analyzed" if geometry.status == "analyzed" else "partial",
            recommendation=recommendation,
            roof_geometry=geometry,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _validated_recommendation(
        self,
        request: ProposalRequest,
        model_file: UploadFile | None,
    ) -> RecommendationValidationResponse:
        return self.project_input_service.validate_recommendation_input(
            json.dumps(request.project.model_dump(mode="json"), ensure_ascii=True),
            model_file=model_file,
        )

    def _cache_uploaded_model(
        self,
        asset_id: str,
        model_file: UploadFile,
        house_data_service: HouseDataService,
    ) -> None:
        glb_bytes = self.project_input_service._read_upload(model_file)
        model_path = house_data_service.house_model_cache_path(asset_id)
        metadata_path = house_data_service.house_model_metadata_cache_path(asset_id)
        try:
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_bytes(glb_bytes)
            metadata_path.write_text(
                json.dumps(
                    {
                        "provider": "frontend_uploaded_glb",
                        "filename": model_file.filename,
                        "glb_size_bytes": len(glb_bytes),
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            raise HTTPException(status_code=502, detail="Uploaded house model could not be cached.") from exc

    def _cache_proposal_context(
        self,
        asset_id: str,
        request: ProposalRequest,
        recommendation: RecommendationValidationResponse,
        house_data_service: HouseDataService,
    ) -> None:
        input_payload = recommendation.input.model_dump(mode="json")
        metadata: dict[str, object] = {
            "project_context": {
                **input_payload,
                "recommendation_goal": recommendation.input.recommendation_goal.value,
                "battery_preference": recommendation.input.battery_preference.value,
                "heat_pump_preference": recommendation.input.heat_pump_preference.value,
                "ev_charger_preference": recommendation.input.ev_charger_preference.value,
                "shading_level": recommendation.input.shading_level.value,
            },
            "model_anchor": request.picked_location.model_dump(mode="json"),
        }
        if request.selected_tile is not None:
            metadata["selected_3d_tile"] = request.selected_tile.model_dump(mode="json")
        house_data_service.update_house_asset_metadata(asset_id, metadata)

    def _pick_clicked_roof_id(
        self,
        roof_analysis: RoofAnalysis,
        house_data_service: HouseDataService,
    ) -> str:
        if not roof_analysis.satellite_image_url or not roof_analysis.roof_outlines:
            raise HTTPException(
                status_code=422,
                detail="No roof outlines were detected for the selected house.",
            )

        asset_id = self.roof_analysis_service.asset_id_from_overhead_url(roof_analysis.satellite_image_url)
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid satellite image URL.")

        try:
            with Image.open(house_data_service.overhead_image_path(asset_id)) as image:
                width, height = image.size
        except OSError as exc:
            raise HTTPException(status_code=422, detail="Satellite image could not be loaded.") from exc

        center_x = width / 2
        center_y = height / 2
        for outline in roof_analysis.roof_outlines:
            if self._point_in_polygon(center_x, center_y, outline.polygon_pixels):
                return outline.id

        return min(
            roof_analysis.roof_outlines,
            key=lambda outline: self._centroid_distance(center_x, center_y, outline),
        ).id

    def _centroid_distance(self, x: float, y: float, outline: RoofOutline) -> float:
        box = outline.bounding_box_pixels
        outline_x = (box.x_min + box.x_max) / 2
        outline_y = (box.y_min + box.y_max) / 2
        return ((outline_x - x) ** 2 + (outline_y - y) ** 2) ** 0.5

    def _point_in_polygon(self, x: float, y: float, polygon: list[list[int]]) -> bool:
        inside = False
        if len(polygon) < 3:
            return inside
        j = len(polygon) - 1
        for i, point in enumerate(polygon):
            xi, yi = point[0], point[1]
            xj, yj = polygon[j][0], polygon[j][1]
            intersects = (yi > y) != (yj > y) and x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
            if intersects:
                inside = not inside
            j = i
        return inside


def get_proposal_service() -> ProposalService:
    return ProposalService(
        project_input_service=get_project_input_service(),
        pvgis_service=get_pvgis_service(),
        roof_analysis_service=get_roof_analysis_service(),
        geometry_pipeline_service=get_roof_geometry_pipeline_service(),
    )
