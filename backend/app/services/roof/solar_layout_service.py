from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box

from app.models.roof import (
    PanelPlacement,
    RoofPlaneGeometry,
    SolarLayoutOption,
    SolarModulePreset,
    TopDownRenderMetadata,
    UsableRoofRegion,
)
from app.services.pvgis_service import PvgisService, get_pvgis_service


PANEL_GAP_M = 0.03
OVERSIZE_WARNING_THRESHOLD = 1.2

MODULE_PRESETS = {
    "compact": SolarModulePreset(
        id="compact",
        label="Compact 450 W glass-glass module",
        brand="Sunpro",
        model="SPDG450-N96R12",
        watt_peak=450,
        length_m=1.762,
        width_m=1.134,
        thickness_m=0.03,
        source_url=(
            "https://www.sunpropower.com/sunpropower/2024/07/22/"
            "%E3%80%90topcon%E3%80%91spdgxxx-n96r12%EF%BC%88425-450w%EF%BC%89"
            "%E5%8F%8C%E7%8E%BB%E5%85%A8%E9%80%8F.pdf"
        ),
    ),
    "standard": SolarModulePreset(
        id="standard",
        label="Standard 480 W glass-glass module",
        brand="Sunpro",
        model="SPDG480-N108R12",
        watt_peak=480,
        length_m=1.96,
        width_m=1.134,
        thickness_m=0.03,
        source_url=(
            "https://www.sunpropower.com/product/topcon/"
            "topcon-spdgxxxn108r12-480505w-shuang-bo-hei-kuang-quan-tou-30mm.html"
        ),
    ),
    "large": SolarModulePreset(
        id="large",
        label="Large 580 W glass-glass module",
        brand="Sunpro",
        model="SPDG580-N144M10",
        watt_peak=580,
        length_m=2.279,
        width_m=1.134,
        thickness_m=0.035,
        source_url=(
            "https://www.sunpropower.com/sunpropower/2025/02/11/"
            "%E3%80%90topcon%E3%80%91spdgxxx-n144m10%EF%BC%88550-590w%EF%BC%89"
            "%E5%8F%8C%E7%8E%BB%E5%85%A8%E9%80%8F%E9%BB%91%E6%A1%86.pdf"
        ),
    ),
}


@dataclass(frozen=True)
class _CandidatePlacement:
    roof_plane_id: str
    usable_region_id: str
    orientation: str
    model_polygon: list[list[float]]
    render_polygon_pixels: list[list[int]]


class SolarLayoutService:
    def __init__(self, pvgis_service: PvgisService) -> None:
        self.pvgis_service = pvgis_service

    def build_layout_options(
        self,
        *,
        roof_planes: list[RoofPlaneGeometry],
        usable_regions: list[UsableRoofRegion],
        metadata: TopDownRenderMetadata,
        latitude: float | None,
        longitude: float | None,
        annual_demand_kwh: float | None,
    ) -> tuple[list[SolarLayoutOption], str | None, list[str]]:
        if not roof_planes or not usable_regions:
            return [], None, ["Solar layout skipped because no usable roof regions were available."]

        plane_yields, yield_warnings = self._plane_yields(
            roof_planes=roof_planes,
            latitude=latitude,
            longitude=longitude,
        )
        option_specs = [
            ("good", "conservative", MODULE_PRESETS["compact"], 0.7),
            ("better", "demand_match", MODULE_PRESETS["standard"], 1.0),
            ("best", "maximum_sun_side_fill", MODULE_PRESETS["large"], None),
        ]

        options: list[SolarLayoutOption] = []
        for option_id, strategy, module, demand_fraction in option_specs:
            candidates = self._candidate_placements(
                module=module,
                roof_planes=roof_planes,
                usable_regions=usable_regions,
                metadata=metadata,
                latitude=latitude,
            )
            placements = self._select_placements(
                candidates=candidates,
                module=module,
                plane_yields=plane_yields,
                annual_demand_kwh=annual_demand_kwh,
                demand_fraction=demand_fraction,
            )
            option_warnings = []
            if not candidates:
                option_warnings.append(f"No {module.label} panels fit in the usable roof regions.")

            estimated_production = self._estimated_production_kwh(
                placements=placements,
                module=module,
                plane_yields=plane_yields,
            )
            coverage = (
                round(estimated_production / annual_demand_kwh, 3)
                if estimated_production is not None and annual_demand_kwh
                else None
            )
            if option_id == "best" and coverage is not None and coverage > OVERSIZE_WARNING_THRESHOLD:
                option_warnings.append(
                    "Max-fill layout materially exceeds annual demand; use it only if the seller wants maximum roof usage."
                )

            options.append(
                SolarLayoutOption(
                    id=option_id,
                    strategy=strategy,
                    module=module,
                    panel_count=len(placements),
                    system_size_kwp=round(len(placements) * module.watt_peak / 1000.0, 3),
                    estimated_annual_production_kwh=estimated_production,
                    annual_demand_kwh=annual_demand_kwh,
                    demand_coverage_ratio=coverage,
                    panel_placements=[
                        PanelPlacement(
                            id=f"panel-{index:03d}",
                            roof_plane_id=placement.roof_plane_id,
                            usable_region_id=placement.usable_region_id,
                            orientation=placement.orientation,
                            model_polygon=placement.model_polygon,
                            render_polygon_pixels=placement.render_polygon_pixels,
                        )
                        for index, placement in enumerate(placements, start=1)
                    ],
                    warnings=option_warnings,
                )
            )

        recommended = self._recommended_option_id(options, annual_demand_kwh)
        return options, recommended, yield_warnings

    def _candidate_placements(
        self,
        *,
        module: SolarModulePreset,
        roof_planes: list[RoofPlaneGeometry],
        usable_regions: list[UsableRoofRegion],
        metadata: TopDownRenderMetadata,
        latitude: float | None,
    ) -> list[_CandidatePlacement]:
        plane_rank = {
            plane.id: index
            for index, plane in enumerate(
                sorted(
                    roof_planes,
                    key=lambda plane: self._plane_sort_key(plane, latitude),
                    reverse=True,
                )
            )
        }
        regions = sorted(
            usable_regions,
            key=lambda region: (
                plane_rank.get(region.roof_plane_id, len(plane_rank)),
                -region.area_m2,
                region.id,
            ),
        )
        plane_by_id = {plane.id: plane for plane in roof_planes}

        candidates: list[_CandidatePlacement] = []
        for region in regions:
            plane = plane_by_id.get(region.roof_plane_id)
            if plane is None:
                continue
            polygon = self._safe_polygon(region.polygon)
            if polygon is None:
                continue
            orientation_candidates = [
                self._pack_region(
                    region=region,
                    polygon=polygon,
                    module=module,
                    plane=plane,
                    orientation="portrait",
                    panel_width_m=module.width_m,
                    panel_length_m=module.length_m,
                    metadata=metadata,
                ),
                self._pack_region(
                    region=region,
                    polygon=polygon,
                    module=module,
                    plane=plane,
                    orientation="landscape",
                    panel_width_m=module.length_m,
                    panel_length_m=module.width_m,
                    metadata=metadata,
                ),
            ]
            best_region_candidates = max(
                orientation_candidates,
                key=lambda items: (len(items), items[0].orientation if items else ""),
            )
            candidates.extend(best_region_candidates)
        return candidates

    def _pack_region(
        self,
        *,
        region: UsableRoofRegion,
        polygon: Polygon,
        module: SolarModulePreset,
        plane: RoofPlaneGeometry,
        orientation: str,
        panel_width_m: float,
        panel_length_m: float,
        metadata: TopDownRenderMetadata,
    ) -> list[_CandidatePlacement]:
        del module
        origin = polygon.centroid
        angle_degrees = self._region_angle_degrees(polygon)
        panel_width_m = self._horizontal_projection_m(panel_width_m, angle_degrees, plane)
        panel_length_m = self._horizontal_projection_m(panel_length_m, angle_degrees + 90.0, plane)
        aligned = affinity.rotate(polygon, -angle_degrees, origin=origin)
        min_x, min_y, max_x, max_y = aligned.bounds
        placements: list[_CandidatePlacement] = []
        y = min_y
        while y + panel_length_m <= max_y + 1e-9:
            x = min_x
            while x + panel_width_m <= max_x + 1e-9:
                panel = box(x, y, x + panel_width_m, y + panel_length_m)
                if aligned.covers(panel):
                    model_polygon = affinity.rotate(panel, angle_degrees, origin=origin)
                    exterior = self._exterior(model_polygon)
                    placements.append(
                        _CandidatePlacement(
                            roof_plane_id=region.roof_plane_id,
                            usable_region_id=region.id,
                            orientation=orientation,
                            model_polygon=exterior,
                            render_polygon_pixels=[
                                self._model_point_to_render_pixel(point, metadata) for point in exterior
                            ],
                        )
                    )
                x += panel_width_m + PANEL_GAP_M
            y += panel_length_m + PANEL_GAP_M
        return placements

    def _select_placements(
        self,
        *,
        candidates: list[_CandidatePlacement],
        module: SolarModulePreset,
        plane_yields: dict[str, float],
        annual_demand_kwh: float | None,
        demand_fraction: float | None,
    ) -> list[_CandidatePlacement]:
        if demand_fraction is None:
            return candidates
        if not candidates:
            return []
        if not annual_demand_kwh or not plane_yields:
            fallback_fraction = 0.5 if demand_fraction <= 0.7 else 0.75
            count = max(1, math.ceil(len(candidates) * fallback_fraction))
            return candidates[:count]

        target_kwh = annual_demand_kwh * demand_fraction
        selected: list[_CandidatePlacement] = []
        production = 0.0
        for candidate in candidates:
            selected.append(candidate)
            production += (module.watt_peak / 1000.0) * plane_yields.get(candidate.roof_plane_id, 0)
            if production >= target_kwh:
                break
        return selected

    def _estimated_production_kwh(
        self,
        *,
        placements: list[_CandidatePlacement],
        module: SolarModulePreset,
        plane_yields: dict[str, float],
    ) -> float | None:
        if not placements or not plane_yields:
            return None
        total = sum(
            (module.watt_peak / 1000.0) * plane_yields.get(placement.roof_plane_id, 0)
            for placement in placements
        )
        return round(total, 1)

    def _plane_yields(
        self,
        *,
        roof_planes: list[RoofPlaneGeometry],
        latitude: float | None,
        longitude: float | None,
    ) -> tuple[dict[str, float], list[str]]:
        if latitude is None or longitude is None:
            return {}, ["PV yield skipped because project coordinates were unavailable."]

        yields: dict[str, float] = {}
        warnings: list[str] = []
        for plane in roof_planes:
            try:
                yields[plane.id] = self.pvgis_service.fetch_annual_pv_yield_per_kwp(
                    latitude=latitude,
                    longitude=longitude,
                    tilt_degrees=plane.tilt_degrees,
                    azimuth_degrees=plane.azimuth_degrees,
                )
            except HTTPException as exc:
                warnings.append(f"PVGIS yield unavailable for {plane.id}: {exc.detail}")
        if warnings:
            return {}, warnings
        return yields, warnings

    def _recommended_option_id(
        self,
        options: list[SolarLayoutOption],
        annual_demand_kwh: float | None,
    ) -> str | None:
        populated = [option for option in options if option.panel_count > 0]
        if not populated:
            return None
        better = next((option for option in populated if option.id == "better"), None)
        if better is not None:
            return better.id
        return populated[-1].id if annual_demand_kwh else populated[0].id

    def _plane_sort_key(self, plane: RoofPlaneGeometry, latitude: float | None) -> tuple[float, float, float]:
        ideal_azimuth = 0.0 if latitude is not None and latitude < 0 else 180.0
        azimuth_delta = abs(((plane.azimuth_degrees - ideal_azimuth + 180.0) % 360.0) - 180.0)
        orientation_score = max(0.0, math.cos(math.radians(azimuth_delta)))
        return (
            0.65 * orientation_score + 0.35 * plane.suitability_score,
            plane.surface_area_m2,
            -azimuth_delta,
        )

    def _region_angle_degrees(self, polygon: Polygon) -> float:
        coordinates = list(polygon.exterior.coords)
        edges = []
        for first, second in zip(coordinates, coordinates[1:], strict=False):
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            edges.append((dx * dx + dy * dy, dx, dy))
        _, dx, dy = max(edges, key=lambda edge: edge[0])
        return math.degrees(math.atan2(dy, dx))

    def _horizontal_projection_m(
        self,
        surface_length_m: float,
        axis_angle_degrees: float,
        plane: RoofPlaneGeometry,
    ) -> float:
        normal_x, normal_y, normal_z = [float(value) for value in plane.normal]
        if abs(normal_y) < 1e-6:
            return surface_length_m
        axis_x = math.cos(math.radians(axis_angle_degrees))
        axis_z = math.sin(math.radians(axis_angle_degrees))
        vertical_per_horizontal = (normal_x * axis_x + normal_z * axis_z) / normal_y
        surface_per_horizontal = math.sqrt(1.0 + vertical_per_horizontal * vertical_per_horizontal)
        return surface_length_m / surface_per_horizontal

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

    def _exterior(self, polygon: Polygon) -> list[list[float]]:
        coordinates = list(polygon.exterior.coords)
        if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
            coordinates = coordinates[:-1]
        return [[round(float(x), 4), round(float(y), 4)] for x, y in coordinates]

    def _model_point_to_render_pixel(
        self,
        point: Iterable[float],
        metadata: TopDownRenderMetadata,
    ) -> list[int]:
        bounds = metadata.orthographic_world_bounds
        x, z = [float(value) for value in point]
        x_pixel = (x - bounds.x_min) / (bounds.x_max - bounds.x_min) * metadata.render_width
        y_pixel = (bounds.z_max - z) / (bounds.z_max - bounds.z_min) * metadata.render_height
        return [int(round(x_pixel)), int(round(y_pixel))]


def get_solar_layout_service() -> SolarLayoutService:
    return SolarLayoutService(pvgis_service=get_pvgis_service())
