import trimesh

from app.services.model.model_geometry_service import ModelGeometryService


def test_model_geometry_service_extracts_distinct_gable_roof_planes() -> None:
    glb_bytes = _gable_roof_glb()
    service = ModelGeometryService()

    loaded = service.load_model_and_render_top_down(glb_bytes, render_size=512)
    roof_planes, warnings = service.extract_roof_planes(
        loaded.mesh,
        [[[-3, -4], [3, -4], [3, 4], [-3, 4]]],
        loaded.render_metadata,
    )

    assert warnings == []
    assert len(roof_planes) == 2
    assert {plane.source_face_count for plane in roof_planes} == {2}
    assert sorted(round(plane.tilt_degrees) for plane in roof_planes) == [45, 45]
    assert sorted(round(plane.azimuth_degrees) for plane in roof_planes) == [90, 270]
    assert all(plane.surface_area_m2 > plane.footprint_area_m2 for plane in roof_planes)
    assert all(plane.render_polygon_pixels for plane in roof_planes)


def test_model_geometry_service_filters_planes_outside_selected_footprint() -> None:
    glb_bytes = _gable_roof_glb()
    service = ModelGeometryService()
    loaded = service.load_model_and_render_top_down(glb_bytes, render_size=512)

    roof_planes, warnings = service.extract_roof_planes(
        loaded.mesh,
        [[[-3, -4], [0, -4], [0, 4], [-3, 4]]],
        loaded.render_metadata,
    )

    assert warnings == []
    assert len(roof_planes) == 1
    assert round(roof_planes[0].azimuth_degrees) == 270


def _gable_roof_glb() -> bytes:
    mesh = trimesh.Trimesh(
        vertices=[
            [-2, 0, -3],
            [-2, 0, 3],
            [2, 0, -3],
            [2, 0, 3],
            [0, 2, -3],
            [0, 2, 3],
        ],
        faces=[
            [0, 1, 5],
            [0, 5, 4],
            [2, 4, 5],
            [2, 5, 3],
        ],
        process=False,
    )
    return bytes(mesh.export(file_type="glb"))
