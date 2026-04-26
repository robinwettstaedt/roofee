from fastapi.testclient import TestClient

from app.main import app
from app.models.bom import BomLineItem, BomLineSource, BomSummary, EquipmentRole, SystemRecommendationOption
from app.models.catalog import ComponentCategory, ComponentKind
from app.models.roof import (
    BoundingBoxPixels,
    OrthographicWorldBounds,
    PanelPlacement,
    RegistrationQualityMetrics,
    RoofGeometryAnalysisRequest,
    RoofGeometryAnalysisResponse,
    RoofOutline,
    RoofRegistrationResponse,
    SolarLayoutOption,
    SolarModulePreset,
    SelectedRoof,
    SimilarityTransform,
    TopDownRenderMetadata,
)
from app.services.house_data_service import get_house_data_service
from app.services.location.google_3d_tiles_service import get_google_3d_tiles_service
from app.services.roof.geometry_pipeline_service import get_roof_geometry_pipeline_service


class FakeRoofGeometryPipelineService:
    def analyze_geometry(
        self,
        request: RoofGeometryAnalysisRequest,
        *,
        house_data_service: object,
        tiles_service: object,
    ) -> RoofGeometryAnalysisResponse:
        assert request.selected_roof_outline_ids == ["roof-003"]
        assert request.model_radius_m == 50
        selected_roof = _selected_roof(request)
        metadata = _metadata()
        registration = RoofRegistrationResponse(
            status="registered",
            selected_roof=selected_roof,
            transform=SimilarityTransform(
                matrix=[[1, 0, 0], [0, 1, 0]],
                scale=1,
                rotation_degrees=0,
                translation_pixels=[0, 0],
                algorithm="orb",
            ),
            mapped_roof_polygon_pixels=[[4, 5], [20, 5], [20, 30], [4, 30]],
            render_metadata=metadata,
            quality=RegistrationQualityMetrics(confidence=0.9),
        )
        return RoofGeometryAnalysisResponse(
            status="analyzed",
            selected_roof=selected_roof,
            registration=registration,
            solar_layout_options=[
                SolarLayoutOption(
                    id="better",
                    strategy="demand_match",
                    module=SolarModulePreset(
                        id="standard",
                        label="Standard 480 W glass-glass module",
                        brand="Sunpro",
                        model="SPDG480-N108R12",
                        watt_peak=480,
                        length_m=1.96,
                        width_m=1.134,
                        thickness_m=0.03,
                        source_url="https://example.test/module.pdf",
                    ),
                    panel_count=12,
                    system_size_kwp=5.76,
                    estimated_annual_production_kwh=5200,
                    annual_demand_kwh=5000,
                    demand_coverage_ratio=1.04,
                    panel_placements=[
                        PanelPlacement(
                            id="panel-001",
                            roof_plane_id="roof-plane-001",
                            usable_region_id="usable-region-001",
                            orientation="portrait",
                            model_polygon=[[1, 1], [3, 1], [3, 2], [1, 2]],
                            render_polygon_pixels=[[10, 90], [30, 90], [30, 80], [10, 80]],
                            surface_polygon_3d=[[1, 6, 1], [3, 6, 1], [3, 6, 2], [1, 6, 2]],
                            center_model=[2, 6.05, 1.5],
                            normal_model=[0, 1, 0],
                            length_axis_model=[1, 0, 0],
                            width_axis_model=[0, 0, 1],
                            clearance_m=0.035,
                            thickness_m=0.03,
                        )
                    ],
                )
            ],
            recommended_layout_option_id="better",
            system_options=[
                SystemRecommendationOption(
                    id="system-better",
                    layout_option_id="better",
                    strategy="demand_match",
                    panel_count=12,
                    system_size_kwp=5.76,
                    estimated_annual_production_kwh=5200,
                    annual_demand_kwh=5000,
                    demand_coverage_ratio=1.04,
                    bom=[
                        BomLineItem(
                            id="panel-line",
                            role=EquipmentRole.PV_MODULE,
                            component_name="Standard 480 W glass-glass module",
                            component_brand="Sunpro",
                            component_type="PanelPreset",
                            category=ComponentCategory.CORE_EQUIPMENT,
                            kind=ComponentKind.PV_MODULE,
                            quantity=12,
                            quantity_units="Item",
                            source=BomLineSource.PANEL_PRESET,
                        )
                    ],
                    summary=BomSummary(
                        line_item_count=1,
                        panel_count=12,
                        system_size_kwp=5.76,
                    ),
                )
            ],
            render_metadata=metadata,
            warnings=[],
        )


def test_roof_geometry_route_runs_from_selected_roof_ids_without_frontend_render() -> None:
    app.dependency_overrides[get_house_data_service] = lambda: object()
    app.dependency_overrides[get_google_3d_tiles_service] = lambda: object()
    app.dependency_overrides[get_roof_geometry_pipeline_service] = lambda: FakeRoofGeometryPipelineService()
    try:
        response = TestClient(app).post(
            "/api/roof/geometry",
            json={
                "satellite_image_url": "/api/house-assets/test-asset/overhead.png",
                "selected_roof_outline_ids": ["roof-003"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "analyzed"
    assert payload["selected_roof"]["selected_roof_outline_ids"] == ["roof-003"]
    assert payload["registration"]["status"] == "registered"
    assert payload["recommended_layout_option_id"] == "better"
    assert payload["solar_layout_options"][0]["module"]["id"] == "standard"
    placement = payload["solar_layout_options"][0]["panel_placements"][0]
    assert placement["surface_polygon_3d"] == [[1, 6, 1], [3, 6, 1], [3, 6, 2], [1, 6, 2]]
    assert placement["center_model"] == [2, 6.05, 1.5]
    assert placement["normal_model"] == [0, 1, 0]
    assert payload["system_options"][0]["layout_option_id"] == "better"
    assert payload["system_options"][0]["bom"][0]["source"] == "panel_preset"


def _selected_roof(request: RoofGeometryAnalysisRequest) -> SelectedRoof:
    outline = RoofOutline(
        id=request.selected_roof_outline_ids[0],
        source="test",
        model_id="test-building-outline",
        bounding_box_pixels=BoundingBoxPixels(x_min=4, y_min=5, x_max=20, y_max=30),
        polygon_pixels=[[4, 5], [20, 5], [20, 30], [4, 30]],
        area_pixels=400,
        confidence=0.9,
    )
    return SelectedRoof(
        satellite_image_url=request.satellite_image_url,
        selected_roof_outline_ids=request.selected_roof_outline_ids,
        selected_roof_outlines=[outline],
        bounding_box_pixels=outline.bounding_box_pixels,
        area_pixels=outline.area_pixels,
    )


def _metadata() -> TopDownRenderMetadata:
    return TopDownRenderMetadata(
        render_width=100,
        render_height=100,
        orthographic_world_bounds=OrthographicWorldBounds(x_min=0, x_max=10, z_min=0, z_max=10),
        model_orientation={"up_axis": "y"},
    )
