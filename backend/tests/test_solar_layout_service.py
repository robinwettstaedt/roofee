from app.models.roof import (
    OrthographicWorldBounds,
    RoofPlaneGeometry,
    TopDownRenderMetadata,
    UsableRoofRegion,
)
from fastapi import HTTPException

from app.services.roof.solar_layout_service import MODULE_PRESETS, SolarLayoutService


class FakePvgisService:
    def fetch_annual_pv_yield_per_kwp(
        self,
        *,
        latitude: float,
        longitude: float,
        tilt_degrees: float,
        azimuth_degrees: float,
    ) -> float:
        assert latitude == 52.5
        assert longitude == 13.4
        return 1000 if azimuth_degrees == 180 else 650


class PartiallyFailingPvgisService:
    def fetch_annual_pv_yield_per_kwp(
        self,
        *,
        latitude: float,
        longitude: float,
        tilt_degrees: float,
        azimuth_degrees: float,
    ) -> float:
        if azimuth_degrees == 0:
            raise HTTPException(status_code=502, detail="PVGIS request timed out.")
        return 1000


def test_solar_layout_service_returns_three_demand_aware_options() -> None:
    service = SolarLayoutService(pvgis_service=FakePvgisService())

    options, recommended, warnings = service.build_layout_options(
        roof_planes=[
            _plane("roof-plane-001", azimuth=180, area=60, suitability=0.95),
            _plane("roof-plane-002", azimuth=0, area=60, suitability=0.2),
        ],
        usable_regions=[
            _region("usable-region-001", "roof-plane-001", [[0, 0], [8, 0], [8, 8], [0, 8]]),
            _region("usable-region-002", "roof-plane-002", [[10, 0], [18, 0], [18, 8], [10, 8]]),
        ],
        metadata=_metadata(),
        latitude=52.5,
        longitude=13.4,
        annual_demand_kwh=5000,
    )

    assert [option.id for option in options] == ["good", "better", "best"]
    assert recommended == "better"
    assert warnings == []
    assert options[0].module.id == "compact"
    assert options[1].module.id == "standard"
    assert options[2].module.id == "large"
    assert options[0].estimated_annual_production_kwh >= 3500
    assert options[1].estimated_annual_production_kwh >= 5000
    assert options[2].panel_count >= options[1].panel_count
    assert options[0].panel_placements[0].roof_plane_id == "roof-plane-001"
    assert all(placement.model_polygon for option in options for placement in option.panel_placements)
    assert all(placement.render_polygon_pixels for option in options for placement in option.panel_placements)


def test_solar_layout_service_falls_back_to_density_options_without_yield() -> None:
    service = SolarLayoutService(pvgis_service=FakePvgisService())

    options, recommended, warnings = service.build_layout_options(
        roof_planes=[_plane("roof-plane-001", azimuth=180, area=40, suitability=0.95)],
        usable_regions=[_region("usable-region-001", "roof-plane-001", [[0, 0], [8, 0], [8, 8], [0, 8]])],
        metadata=_metadata(),
        latitude=None,
        longitude=None,
        annual_demand_kwh=5000,
    )

    assert recommended == "better"
    assert warnings == ["PV yield skipped because project coordinates were unavailable."]
    assert options[0].estimated_annual_production_kwh is None
    assert options[0].panel_count > 0
    assert options[0].panel_count < options[2].panel_count


def test_solar_layout_service_does_not_return_partial_yield_estimates() -> None:
    service = SolarLayoutService(pvgis_service=PartiallyFailingPvgisService())

    options, recommended, warnings = service.build_layout_options(
        roof_planes=[
            _plane("roof-plane-001", azimuth=180, area=60, suitability=0.95),
            _plane("roof-plane-002", azimuth=0, area=60, suitability=0.2),
        ],
        usable_regions=[
            _region("usable-region-001", "roof-plane-001", [[0, 0], [8, 0], [8, 8], [0, 8]]),
            _region("usable-region-002", "roof-plane-002", [[10, 0], [18, 0], [18, 8], [10, 8]]),
        ],
        metadata=_metadata(),
        latitude=52.5,
        longitude=13.4,
        annual_demand_kwh=5000,
    )

    assert recommended == "better"
    assert warnings == ["PVGIS yield unavailable for roof-plane-002: PVGIS request timed out."]
    assert all(option.estimated_annual_production_kwh is None for option in options)


def test_module_presets_have_real_physical_dimensions() -> None:
    assert MODULE_PRESETS["compact"].length_m == 1.762
    assert MODULE_PRESETS["standard"].length_m == 1.96
    assert MODULE_PRESETS["large"].length_m == 2.279
    assert all(module.source_url.startswith("https://") for module in MODULE_PRESETS.values())


def test_panel_dimensions_are_projected_onto_tilted_roof_plane() -> None:
    service = SolarLayoutService(pvgis_service=FakePvgisService())
    tilted_plane = _plane("roof-plane-001", azimuth=90, area=40, suitability=0.8)
    tilted_plane.normal = [0.70711, 0.70711, 0]

    projected = service._horizontal_projection_m(2.0, 0, tilted_plane)

    assert round(projected, 3) == 1.414


def _plane(
    plane_id: str,
    *,
    azimuth: float,
    area: float,
    suitability: float,
) -> RoofPlaneGeometry:
    return RoofPlaneGeometry(
        id=plane_id,
        normal=[0, 1, 0],
        tilt_degrees=30,
        azimuth_degrees=azimuth,
        surface_area_m2=area,
        footprint_area_m2=area,
        footprint_polygon=[[0, 0], [8, 0], [8, 8], [0, 8]],
        render_polygon_pixels=[[0, 100], [80, 100], [80, 20], [0, 20]],
        source_face_count=2,
        suitability_score=suitability,
    )


def _region(region_id: str, plane_id: str, polygon: list[list[float]]) -> UsableRoofRegion:
    return UsableRoofRegion(
        id=region_id,
        roof_plane_id=plane_id,
        polygon=polygon,
        render_polygon_pixels=[],
        area_m2=64,
    )


def _metadata() -> TopDownRenderMetadata:
    return TopDownRenderMetadata(
        render_width=200,
        render_height=200,
        orthographic_world_bounds=OrthographicWorldBounds(x_min=0, x_max=20, z_min=0, z_max=20),
        model_orientation={"up_axis": "y"},
    )
