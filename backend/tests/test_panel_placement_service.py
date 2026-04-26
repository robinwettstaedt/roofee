import math

from app.models.roof import PanelPlacement, RoofPlaneGeometry, SolarLayoutOption, SolarModulePreset
from app.services.model.panel_placement_service import PanelPlacementService


def test_panel_placement_lifts_footprint_onto_sloped_plane() -> None:
    service = PanelPlacementService()
    normal = _unit([0.5, math.sqrt(3) / 2, 0])
    plane = _plane(normal=normal, plane_offset=3.0)
    layout = _layout(
        PanelPlacement(
            id="panel-001",
            roof_plane_id=plane.id,
            usable_region_id="usable-region-001",
            orientation="portrait",
            model_polygon=[[0, 0], [2, 0], [2, 1], [0, 1]],
            render_polygon_pixels=[[0, 0], [20, 0], [20, 10], [0, 10]],
        )
    )

    layouts, warnings = service.enrich_layout_options(layouts=[layout], roof_planes=[plane], clearance_m=0.04)

    assert warnings == []
    placement = layouts[0].panel_placements[0]
    assert len(placement.surface_polygon_3d) == 4
    for x, y, z in placement.surface_polygon_3d:
        assert math.isclose((normal[0] * x) + (normal[1] * y) + (normal[2] * z), plane.plane_offset, abs_tol=1e-4)

    assert math.isclose(_length(placement.normal_model), 1, abs_tol=1e-5)
    assert math.isclose(_length(placement.length_axis_model), 1, abs_tol=1e-5)
    assert math.isclose(_length(placement.width_axis_model), 1, abs_tol=1e-5)
    assert math.isclose(_dot(placement.length_axis_model, placement.width_axis_model), 0, abs_tol=1e-5)
    assert math.isclose(_dot(placement.length_axis_model, placement.normal_model), 0, abs_tol=1e-5)
    assert math.isclose(_dot(placement.width_axis_model, placement.normal_model), 0, abs_tol=1e-5)


def test_panel_center_is_lifted_by_clearance_and_half_thickness() -> None:
    service = PanelPlacementService()
    plane = _plane(normal=[0, 1, 0], plane_offset=6.0)
    layout = _layout(
        PanelPlacement(
            id="panel-001",
            roof_plane_id=plane.id,
            usable_region_id="usable-region-001",
            orientation="landscape",
            model_polygon=[[0, 0], [2, 0], [2, 1], [0, 1]],
            render_polygon_pixels=[[0, 0], [20, 0], [20, 10], [0, 10]],
        ),
        thickness_m=0.05,
    )

    layouts, warnings = service.enrich_layout_options(layouts=[layout], roof_planes=[plane], clearance_m=0.04)

    assert warnings == []
    placement = layouts[0].panel_placements[0]
    assert placement.surface_polygon_3d[0][1] == 6.0
    assert math.isclose(placement.center_model[1], 6.0 + 0.04 + 0.025, abs_tol=1e-5)
    assert placement.clearance_m == 0.04
    assert placement.thickness_m == 0.05


def _plane(*, normal: list[float], plane_offset: float) -> RoofPlaneGeometry:
    return RoofPlaneGeometry(
        id="roof-plane-001",
        normal=normal,
        plane_offset=plane_offset,
        centroid_model=[0, plane_offset, 0],
        tilt_degrees=30,
        azimuth_degrees=180,
        surface_area_m2=20,
        footprint_area_m2=18,
        footprint_polygon=[[0, 0], [5, 0], [5, 5], [0, 5]],
        render_polygon_pixels=[[0, 50], [50, 50], [50, 0], [0, 0]],
        source_face_count=2,
        suitability_score=0.9,
    )


def _layout(placement: PanelPlacement, *, thickness_m: float = 0.04) -> SolarLayoutOption:
    return SolarLayoutOption(
        id="better",
        strategy="demand_match",
        module=SolarModulePreset(
            id="standard",
            label="Standard module",
            brand="Sunpro",
            model="SPDG480-N108R12",
            watt_peak=480,
            length_m=2,
            width_m=1,
            thickness_m=thickness_m,
            source_url="https://example.test/module.pdf",
        ),
        panel_count=1,
        system_size_kwp=0.48,
        panel_placements=[placement],
    )


def _unit(vector: list[float]) -> list[float]:
    length = _length(vector)
    return [value / length for value in vector]


def _length(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _dot(first: list[float], second: list[float]) -> float:
    return sum(first[index] * second[index] for index in range(3))
