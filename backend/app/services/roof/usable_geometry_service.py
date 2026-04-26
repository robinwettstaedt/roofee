from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from app.models.roof import (
    MappedRoofObstruction,
    RemovedRoofArea,
    RoofPlaneGeometry,
    TopDownRenderMetadata,
    UsableRoofRegion,
)


class UsableRoofGeometryService:
    def build_usable_regions(
        self,
        *,
        roof_planes: list[RoofPlaneGeometry],
        obstructions: list[MappedRoofObstruction],
        metadata: TopDownRenderMetadata,
        roof_edge_setback_m: float,
        obstruction_buffer_m: float,
    ) -> tuple[list[UsableRoofRegion], list[RemovedRoofArea], list[str]]:
        usable_regions: list[UsableRoofRegion] = []
        removed_areas: list[RemovedRoofArea] = []
        warnings: list[str] = []

        for plane in roof_planes:
            plane_polygon = self._safe_polygon(plane.footprint_polygon)
            if plane_polygon is None:
                warnings.append(f"{plane.id} did not have a valid footprint polygon.")
                continue

            inset_polygon = plane_polygon.buffer(-roof_edge_setback_m) if roof_edge_setback_m > 0 else plane_polygon
            if inset_polygon.is_empty:
                removed_areas.append(
                    self._removed_area(
                        roof_plane_id=plane.id,
                        source_type="roof_edge_setback",
                        source_id="roof-edge",
                        class_name=None,
                        geometry=plane_polygon,
                        metadata=metadata,
                    )
                )
                warnings.append(f"{plane.id} has no usable area after roof-edge setback.")
                continue

            removed_edge = plane_polygon.difference(inset_polygon)
            if not removed_edge.is_empty:
                removed_areas.extend(
                    self._removed_areas_from_geometry(
                        roof_plane_id=plane.id,
                        source_type="roof_edge_setback",
                        source_id="roof-edge",
                        class_name=None,
                        geometry=removed_edge,
                        metadata=metadata,
                    )
                )

            obstruction_shapes = []
            for obstruction in obstructions:
                shape = self._safe_polygon(obstruction.model_polygon)
                if shape is None:
                    continue
                buffered = shape.buffer(obstruction_buffer_m) if obstruction_buffer_m > 0 else shape
                overlap = inset_polygon.intersection(buffered)
                if overlap.is_empty:
                    continue
                obstruction_shapes.append(overlap)
                removed_areas.extend(
                    self._removed_areas_from_geometry(
                        roof_plane_id=plane.id,
                        source_type="obstruction",
                        source_id=obstruction.id,
                        class_name=obstruction.class_name,
                        geometry=overlap,
                        metadata=metadata,
                    )
                )

            free_geometry = inset_polygon
            if obstruction_shapes:
                free_geometry = inset_polygon.difference(unary_union(obstruction_shapes))
            for polygon in self._polygons(free_geometry):
                if polygon.area <= 0:
                    continue
                exterior = self._exterior(polygon)
                usable_regions.append(
                    UsableRoofRegion(
                        id=f"usable-region-{len(usable_regions) + 1:03d}",
                        roof_plane_id=plane.id,
                        polygon=exterior,
                        render_polygon_pixels=[self._model_point_to_render_pixel(point, metadata) for point in exterior],
                        area_m2=round(float(polygon.area), 3),
                    )
                )

        for index, removed_area in enumerate(removed_areas, start=1):
            removed_area.id = f"removed-area-{index:03d}"
        return usable_regions, removed_areas, warnings

    def _removed_areas_from_geometry(
        self,
        *,
        roof_plane_id: str,
        source_type: str,
        source_id: str,
        class_name: str | None,
        geometry: Polygon | MultiPolygon,
        metadata: TopDownRenderMetadata,
    ) -> list[RemovedRoofArea]:
        return [
            self._removed_area(
                roof_plane_id=roof_plane_id,
                source_type=source_type,
                source_id=source_id,
                class_name=class_name,
                geometry=polygon,
                metadata=metadata,
            )
            for polygon in self._polygons(geometry)
            if polygon.area > 0
        ]

    def _removed_area(
        self,
        *,
        roof_plane_id: str,
        source_type: str,
        source_id: str,
        class_name: str | None,
        geometry: Polygon,
        metadata: TopDownRenderMetadata,
    ) -> RemovedRoofArea:
        exterior = self._exterior(geometry)
        return RemovedRoofArea(
            id="removed-area-pending",
            roof_plane_id=roof_plane_id,
            source_type=source_type,
            source_id=source_id,
            class_name=class_name,
            polygon=exterior,
            area_m2=round(float(geometry.area), 3),
        )

    def _model_point_to_render_pixel(
        self,
        point: list[float],
        metadata: TopDownRenderMetadata,
    ) -> list[int]:
        bounds = metadata.orthographic_world_bounds
        x = float(point[0])
        z = float(point[1])
        x_pixel = (x - bounds.x_min) / (bounds.x_max - bounds.x_min) * metadata.render_width
        y_pixel = (bounds.z_max - z) / (bounds.z_max - bounds.z_min) * metadata.render_height
        return [int(round(x_pixel)), int(round(y_pixel))]

    def _safe_polygon(self, coordinates: list[list[float]]) -> Polygon | None:
        try:
            polygon = Polygon(coordinates)
        except (TypeError, ValueError):
            return None
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.area <= 0:
            return None
        if isinstance(polygon, MultiPolygon):
            return max(polygon.geoms, key=lambda item: item.area)
        return polygon if isinstance(polygon, Polygon) else None

    def _polygons(self, geometry: Polygon | MultiPolygon) -> list[Polygon]:
        if isinstance(geometry, Polygon):
            return [geometry]
        if isinstance(geometry, MultiPolygon):
            return list(geometry.geoms)
        return []

    def _exterior(self, polygon: Polygon) -> list[list[float]]:
        coordinates = list(polygon.exterior.coords)
        if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
            coordinates = coordinates[:-1]
        return [[round(float(x), 4), round(float(y), 4)] for x, y in coordinates]


def get_usable_roof_geometry_service() -> UsableRoofGeometryService:
    return UsableRoofGeometryService()
