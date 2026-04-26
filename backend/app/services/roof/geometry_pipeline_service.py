from __future__ import annotations

import cv2
import numpy as np
from fastapi import HTTPException
from shapely.geometry import Polygon

from app.models.roof import (
    MappedRoofObstruction,
    RoofGeometryAnalysisRequest,
    RoofGeometryAnalysisResponse,
    RoofObstruction,
    RoofObstructionRequest,
    RoofRegistrationRequest,
    TopDownRenderMetadata,
)
from app.services.house_data_service import HouseDataService
from app.services.location.google_3d_tiles_service import Google3DTilesService
from app.services.model.model_asset_service import ModelAssetService, get_model_asset_service
from app.services.model.model_geometry_service import ModelGeometryService, get_model_geometry_service
from app.services.roof.obstruction_service import RoofObstructionService, get_roof_obstruction_service
from app.services.roof.registration_service import RoofRegistrationService, get_roof_registration_service
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service
from app.services.roof.usable_geometry_service import (
    UsableRoofGeometryService,
    get_usable_roof_geometry_service,
)


class RoofGeometryPipelineService:
    def __init__(
        self,
        *,
        roof_analysis_service: RoofAnalysisService,
        obstruction_service: RoofObstructionService,
        registration_service: RoofRegistrationService,
        model_asset_service: ModelAssetService,
        model_geometry_service: ModelGeometryService,
        usable_geometry_service: UsableRoofGeometryService,
    ) -> None:
        self.roof_analysis_service = roof_analysis_service
        self.obstruction_service = obstruction_service
        self.registration_service = registration_service
        self.model_asset_service = model_asset_service
        self.model_geometry_service = model_geometry_service
        self.usable_geometry_service = usable_geometry_service

    def analyze_geometry(
        self,
        request: RoofGeometryAnalysisRequest,
        *,
        house_data_service: HouseDataService,
        tiles_service: Google3DTilesService,
    ) -> RoofGeometryAnalysisResponse:
        selection = self.roof_analysis_service.select_roof(request, house_data_service)
        asset_id = self.roof_analysis_service.asset_id_from_overhead_url(request.satellite_image_url)
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid satellite image URL.")

        glb_bytes = self.model_asset_service.load_or_fetch_model(
            asset_id=asset_id,
            radius_m=request.model_radius_m,
            house_data_service=house_data_service,
            tiles_service=tiles_service,
        )
        loaded_model = self.model_geometry_service.load_model_and_render_top_down(glb_bytes)
        registration_request = RoofRegistrationRequest(
            satellite_image_url=request.satellite_image_url,
            selected_roof_outline_ids=request.selected_roof_outline_ids,
            top_down_render_metadata=loaded_model.render_metadata,
        )
        registration = self.registration_service.register_roof(
            registration_request,
            loaded_model.top_down_render_png,
            house_data_service,
        )

        warnings = list(registration.warnings)
        if registration.status != "registered" or registration.transform is None:
            return RoofGeometryAnalysisResponse(
                status="registration_failed",
                selected_roof=selection.selected_roof,
                registration=registration,
                render_metadata=loaded_model.render_metadata,
                warnings=warnings,
            )

        obstruction_analysis = self.obstruction_service.analyze_obstructions(
            RoofObstructionRequest(
                satellite_image_url=request.satellite_image_url,
                selected_roof_outline_ids=request.selected_roof_outline_ids,
            ),
            house_data_service,
        )
        warnings.extend(obstruction_analysis.warnings)
        mapped_obstructions = [
            self._mapped_obstruction(obstruction, registration.transform.matrix, loaded_model.render_metadata)
            for obstruction in obstruction_analysis.obstructions
        ]

        roof_planes, plane_warnings = self.model_geometry_service.extract_roof_planes(
            loaded_model.mesh,
            [outline.model_polygon for outline in registration.mapped_roof_outlines],
            loaded_model.render_metadata,
        )
        warnings.extend(plane_warnings)
        usable_regions, removed_areas, usable_warnings = self.usable_geometry_service.build_usable_regions(
            roof_planes=roof_planes,
            obstructions=mapped_obstructions,
            metadata=loaded_model.render_metadata,
            roof_edge_setback_m=request.roof_edge_setback_m,
            obstruction_buffer_m=request.obstruction_buffer_m,
        )
        warnings.extend(usable_warnings)

        return RoofGeometryAnalysisResponse(
            status="analyzed" if roof_planes else "partial",
            selected_roof=selection.selected_roof,
            registration=registration,
            mapped_roof_outlines=registration.mapped_roof_outlines,
            mapped_obstructions=mapped_obstructions,
            roof_planes=roof_planes,
            usable_regions=usable_regions,
            removed_areas=removed_areas,
            render_metadata=loaded_model.render_metadata,
            warnings=warnings,
        )

    def _mapped_obstruction(
        self,
        obstruction: RoofObstruction,
        matrix: list[list[float]],
        metadata: TopDownRenderMetadata,
    ) -> MappedRoofObstruction:
        render_polygon = self._map_polygon(obstruction.polygon_pixels, matrix)
        model_polygon = [
            self.registration_service.render_pixel_to_model_point(point, metadata) for point in render_polygon
        ]
        return MappedRoofObstruction(
            id=obstruction.id,
            class_name=obstruction.class_name,
            source_polygon_pixels=obstruction.polygon_pixels,
            render_polygon_pixels=render_polygon,
            model_polygon=model_polygon,
            area_m2=round(float(Polygon(model_polygon).area), 3) if len(model_polygon) >= 3 else 0,
        )

    def _map_polygon(self, polygon: list[list[int]], matrix: list[list[float]]) -> list[list[int]]:
        matrix_np = np.asarray(matrix, dtype=np.float32)
        points = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
        mapped = cv2.transform(points, matrix_np).reshape(-1, 2)
        return [[int(round(float(x))), int(round(float(y)))] for x, y in mapped]


def get_roof_geometry_pipeline_service() -> RoofGeometryPipelineService:
    return RoofGeometryPipelineService(
        roof_analysis_service=get_roof_analysis_service(),
        obstruction_service=get_roof_obstruction_service(),
        registration_service=get_roof_registration_service(),
        model_asset_service=get_model_asset_service(),
        model_geometry_service=get_model_geometry_service(),
        usable_geometry_service=get_usable_roof_geometry_service(),
    )
