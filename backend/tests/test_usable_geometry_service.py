from app.models.roof import (
    MappedRoofObstruction,
    OrthographicWorldBounds,
    RoofPlaneGeometry,
    TopDownRenderMetadata,
)
from app.services.roof.usable_geometry_service import UsableRoofGeometryService


def test_usable_geometry_service_subtracts_obstruction_and_preserves_split_regions() -> None:
    service = UsableRoofGeometryService()
    plane = RoofPlaneGeometry(
        id="roof-plane-001",
        normal=[0, 1, 0],
        tilt_degrees=0,
        azimuth_degrees=180,
        surface_area_m2=24,
        footprint_area_m2=24,
        footprint_polygon=[[0, 0], [6, 0], [6, 4], [0, 4]],
        render_polygon_pixels=[],
        source_face_count=2,
        suitability_score=0.8,
    )
    obstruction = MappedRoofObstruction(
        id="obstruction-001",
        class_name="chimney",
        source_polygon_pixels=[],
        render_polygon_pixels=[],
        model_polygon=[[2.8, 0], [3.2, 0], [3.2, 4], [2.8, 4]],
        area_m2=1.6,
    )

    usable_regions, removed_areas, warnings = service.build_usable_regions(
        roof_planes=[plane],
        obstructions=[obstruction],
        metadata=_metadata(),
        roof_edge_setback_m=0,
        obstruction_buffer_m=0,
    )

    assert warnings == []
    assert len(usable_regions) == 2
    assert sorted(region.area_m2 for region in usable_regions) == [11.2, 11.2]
    assert len(removed_areas) == 1
    assert removed_areas[0].id == "removed-area-001"
    assert removed_areas[0].source_id == "obstruction-001"
    assert removed_areas[0].class_name == "chimney"
    assert removed_areas[0].area_m2 == 1.6


def test_usable_geometry_service_reports_plane_consumed_by_setback() -> None:
    service = UsableRoofGeometryService()
    plane = RoofPlaneGeometry(
        id="roof-plane-001",
        normal=[0, 1, 0],
        tilt_degrees=0,
        azimuth_degrees=180,
        surface_area_m2=1,
        footprint_area_m2=1,
        footprint_polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
        render_polygon_pixels=[],
        source_face_count=2,
        suitability_score=0.2,
    )

    usable_regions, removed_areas, warnings = service.build_usable_regions(
        roof_planes=[plane],
        obstructions=[],
        metadata=_metadata(),
        roof_edge_setback_m=0.6,
        obstruction_buffer_m=0,
    )

    assert usable_regions == []
    assert removed_areas[0].source_type == "roof_edge_setback"
    assert warnings == ["roof-plane-001 has no usable area after roof-edge setback."]


def _metadata() -> TopDownRenderMetadata:
    return TopDownRenderMetadata(
        render_width=600,
        render_height=400,
        orthographic_world_bounds=OrthographicWorldBounds(x_min=0, x_max=6, z_min=0, z_max=4),
        model_orientation={"up_axis": "y"},
    )
