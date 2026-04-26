from __future__ import annotations

import math

from app.models.roof import PanelPlacement, RoofPlaneGeometry, SolarLayoutOption


PANEL_CLEARANCE_M = 0.035


class PanelPlacementService:
    def enrich_layout_options(
        self,
        *,
        layouts: list[SolarLayoutOption],
        roof_planes: list[RoofPlaneGeometry],
        clearance_m: float = PANEL_CLEARANCE_M,
    ) -> tuple[list[SolarLayoutOption], list[str]]:
        plane_by_id = {plane.id: plane for plane in roof_planes}
        warnings: list[str] = []
        enriched_layouts: list[SolarLayoutOption] = []

        for layout in layouts:
            enriched_layout = layout.model_copy(deep=True)
            enriched_placements: list[PanelPlacement] = []
            for placement in enriched_layout.panel_placements:
                plane = plane_by_id.get(placement.roof_plane_id)
                if plane is None:
                    warnings.append(f"Panel placement skipped for {placement.id}: roof plane not found.")
                    enriched_placements.append(placement)
                    continue
                enriched_placements.append(
                    self._enrich_placement(
                        placement=placement,
                        plane=plane,
                        thickness_m=layout.module.thickness_m,
                        clearance_m=clearance_m,
                    )
                )
            enriched_layout.panel_placements = enriched_placements
            enriched_layouts.append(enriched_layout)

        return enriched_layouts, warnings

    def _enrich_placement(
        self,
        *,
        placement: PanelPlacement,
        plane: RoofPlaneGeometry,
        thickness_m: float,
        clearance_m: float,
    ) -> PanelPlacement:
        normal = self._unit3(plane.normal)
        if normal is None or abs(normal[1]) < 1e-6:
            return placement

        surface_polygon = [self._surface_point(point, normal, plane.plane_offset) for point in placement.model_polygon]
        if len(surface_polygon) < 3:
            return placement

        center_surface = [
            sum(point[index] for point in surface_polygon) / len(surface_polygon)
            for index in range(3)
        ]
        center_lift = clearance_m + (thickness_m / 2.0)
        center_model = [
            center_surface[index] + normal[index] * center_lift
            for index in range(3)
        ]
        length_axis, width_axis = self._panel_axes(surface_polygon, normal)

        return placement.model_copy(
            update={
                "surface_polygon_3d": [self._round3(point) for point in surface_polygon],
                "center_model": self._round3(center_model),
                "normal_model": self._round3(normal),
                "length_axis_model": self._round3(length_axis),
                "width_axis_model": self._round3(width_axis),
                "clearance_m": round(clearance_m, 4),
                "thickness_m": round(thickness_m, 4),
            }
        )

    def _surface_point(
        self,
        point: list[float],
        normal: list[float],
        plane_offset: float,
    ) -> list[float]:
        x = float(point[0])
        z = float(point[1])
        y = (float(plane_offset) - normal[0] * x - normal[2] * z) / normal[1]
        return [x, y, z]

    def _panel_axes(
        self,
        surface_polygon: list[list[float]],
        normal: list[float],
    ) -> tuple[list[float], list[float]]:
        edges = []
        for index, first in enumerate(surface_polygon):
            second = surface_polygon[(index + 1) % len(surface_polygon)]
            vector = [second[axis] - first[axis] for axis in range(3)]
            length = self._length(vector)
            if length > 1e-9:
                edges.append((length, vector, index))

        if not edges:
            return [1, 0, 0], [0, 0, 1]

        _, long_edge, long_index = max(edges, key=lambda item: item[0])
        length_axis = self._unit3(long_edge) or [1, 0, 0]

        adjacent_edges = [
            item
            for item in edges
            if item[2] in {(long_index - 1) % len(surface_polygon), (long_index + 1) % len(surface_polygon)}
        ]
        if adjacent_edges:
            _, width_edge, _ = max(adjacent_edges, key=lambda item: item[0])
            width_axis = self._orthogonalized_unit(width_edge, length_axis) or self._cross(normal, length_axis)
        else:
            width_axis = self._cross(normal, length_axis)

        width_axis = self._unit3(width_axis) or [0, 0, 1]
        if self._dot(self._cross(length_axis, width_axis), normal) < 0:
            width_axis = [-value for value in width_axis]
        return length_axis, width_axis

    def _orthogonalized_unit(self, vector: list[float], basis: list[float]) -> list[float] | None:
        projection = self._dot(vector, basis)
        orthogonal = [vector[index] - projection * basis[index] for index in range(3)]
        return self._unit3(orthogonal)

    def _unit3(self, vector: list[float]) -> list[float] | None:
        if len(vector) != 3:
            return None
        length = self._length(vector)
        if length <= 1e-9:
            return None
        return [float(value) / length for value in vector]

    def _length(self, vector: list[float]) -> float:
        return math.sqrt(sum(float(value) * float(value) for value in vector))

    def _dot(self, first: list[float], second: list[float]) -> float:
        return sum(first[index] * second[index] for index in range(3))

    def _cross(self, first: list[float], second: list[float]) -> list[float]:
        return [
            first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0],
        ]

    def _round3(self, values: list[float]) -> list[float]:
        return [round(float(value), 5) for value in values]


def get_panel_placement_service() -> PanelPlacementService:
    return PanelPlacementService()
