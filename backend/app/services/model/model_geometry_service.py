from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import cv2
import numpy as np
import trimesh
from fastapi import HTTPException
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from app.models.roof import OrthographicWorldBounds, RoofPlaneGeometry, TopDownRenderMetadata


@dataclass(frozen=True)
class LoadedRoofModel:
    mesh: trimesh.Trimesh
    top_down_render_png: bytes
    render_metadata: TopDownRenderMetadata


class ModelGeometryService:
    def load_model_and_render_top_down(
        self,
        glb_bytes: bytes,
        *,
        render_size: int = 1024,
    ) -> LoadedRoofModel:
        mesh = self._load_mesh(glb_bytes)
        metadata = self._render_metadata(mesh, render_size)
        render = self._top_down_render(mesh, metadata)
        success, encoded = cv2.imencode(".png", render)
        if not success:
            raise HTTPException(status_code=422, detail="Top-down model render could not be encoded.")
        return LoadedRoofModel(
            mesh=mesh,
            top_down_render_png=bytes(encoded),
            render_metadata=metadata,
        )

    def extract_roof_planes(
        self,
        mesh: trimesh.Trimesh,
        selected_roof_polygons: list[list[list[float]]],
        metadata: TopDownRenderMetadata,
        *,
        min_up_normal: float = 0.2,
        max_normal_angle_degrees: float = 8.0,
        max_plane_offset_m: float = 0.35,
        min_plane_area_m2: float = 1.0,
    ) -> tuple[list[RoofPlaneGeometry], list[str]]:
        selected_area = self._selected_area(selected_roof_polygons)
        if selected_area.is_empty:
            return [], ["No valid selected roof polygon was available in model coordinates."]

        face_normals = np.asarray(mesh.face_normals, dtype=float)
        triangles = np.asarray(mesh.triangles, dtype=float)
        centroids = triangles.mean(axis=1)
        face_areas = np.asarray(mesh.area_faces, dtype=float)
        candidate_faces: set[int] = set()
        for index, normal in enumerate(face_normals):
            if normal[1] < min_up_normal:
                continue
            centroid = centroids[index]
            point = Point(float(centroid[0]), float(centroid[2]))
            if not (selected_area.contains(point) or selected_area.touches(point)):
                continue
            if face_areas[index] <= 0:
                continue
            candidate_faces.add(index)

        if not candidate_faces:
            return [], ["No upward-facing model faces were found inside the selected roof footprint."]

        adjacency = self._candidate_adjacency(mesh, candidate_faces)
        clusters = self._cluster_faces(
            candidate_faces,
            adjacency,
            face_normals,
            centroids,
            max_normal_angle_degrees=max_normal_angle_degrees,
            max_plane_offset_m=max_plane_offset_m,
        )

        planes: list[RoofPlaneGeometry] = []
        warnings: list[str] = []
        for cluster in clusters:
            surface_area = float(face_areas[cluster].sum())
            if surface_area < min_plane_area_m2:
                continue
            plane = self._roof_plane_from_cluster(
                cluster,
                triangles,
                face_normals,
                face_areas,
                centroids,
                metadata,
                plane_id=f"roof-plane-{len(planes) + 1:03d}",
            )
            if plane is None:
                warnings.append(f"Skipped roof-plane candidate {len(planes) + 1}: invalid footprint polygon.")
                continue
            planes.append(plane)

        if not planes:
            warnings.append("All model roof-plane candidates were below the minimum usable area.")
        return planes, warnings

    def _load_mesh(self, glb_bytes: bytes) -> trimesh.Trimesh:
        if not glb_bytes or glb_bytes[:4] != b"glTF":
            raise HTTPException(status_code=422, detail="House model must be a binary GLB.")
        try:
            loaded = trimesh.load(BytesIO(glb_bytes), file_type="glb", force="scene", process=False)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="House model could not be parsed as GLB.") from exc

        if isinstance(loaded, trimesh.Scene):
            geometry = loaded.to_geometry()
            if not isinstance(geometry, trimesh.Trimesh):
                raise HTTPException(status_code=422, detail="House model did not contain mesh geometry.")
            mesh = geometry
        elif isinstance(loaded, trimesh.Trimesh):
            mesh = loaded
        else:
            raise HTTPException(status_code=422, detail="House model did not contain mesh geometry.")

        if mesh.vertices.size == 0 or mesh.faces.size == 0:
            raise HTTPException(status_code=422, detail="House model did not contain mesh geometry.")
        return mesh

    def _render_metadata(self, mesh: trimesh.Trimesh, render_size: int) -> TopDownRenderMetadata:
        vertices = np.asarray(mesh.vertices, dtype=float)
        x_min = float(vertices[:, 0].min())
        x_max = float(vertices[:, 0].max())
        z_min = float(vertices[:, 2].min())
        z_max = float(vertices[:, 2].max())
        y_min = float(vertices[:, 1].min())
        y_max = float(vertices[:, 1].max())
        span = max(x_max - x_min, z_max - z_min, 1.0)
        padding = span * 0.04
        return TopDownRenderMetadata(
            render_width=render_size,
            render_height=render_size,
            orthographic_world_bounds=OrthographicWorldBounds(
                x_min=x_min - padding,
                x_max=x_max + padding,
                z_min=z_min - padding,
                z_max=z_max + padding,
                y_min=y_min,
                y_max=y_max,
            ),
            model_orientation={
                "up_axis": "y",
                "horizontal_axes": {"x": "east_model_local", "z": "north_model_local"},
                "camera_direction": [0, -1, 0],
                "camera_up": [0, 0, -1],
            },
        )

    def _top_down_render(self, mesh: trimesh.Trimesh, metadata: TopDownRenderMetadata) -> np.ndarray:
        image = np.zeros((metadata.render_height, metadata.render_width, 3), dtype=np.uint8)
        triangles = np.asarray(mesh.triangles, dtype=float)
        if triangles.size == 0:
            return image

        y_values = triangles[:, :, 1]
        y_min = float(np.min(y_values))
        y_max = float(np.max(y_values))
        y_span = max(y_max - y_min, 1.0)
        order = np.argsort(y_values.mean(axis=1))
        for face_index in order:
            triangle = triangles[face_index]
            points = np.array(
                [self.model_point_to_render_pixel([vertex[0], vertex[2]], metadata) for vertex in triangle],
                dtype=np.int32,
            )
            shade = int(80 + ((float(triangle[:, 1].mean()) - y_min) / y_span) * 155)
            cv2.fillConvexPoly(image, points, (shade, shade, shade))
            cv2.polylines(image, [points], isClosed=True, color=(245, 245, 245), thickness=1)
        return image

    def _selected_area(self, polygons: list[list[list[float]]]) -> Polygon | MultiPolygon:
        shapes = []
        for polygon in polygons:
            shape = self._safe_polygon(polygon)
            if shape is not None and not shape.is_empty:
                shapes.append(shape)
        if not shapes:
            return Polygon()
        union = unary_union(shapes)
        return union if isinstance(union, Polygon | MultiPolygon) else Polygon()

    def _candidate_adjacency(self, mesh: trimesh.Trimesh, candidate_faces: set[int]) -> dict[int, set[int]]:
        adjacency = {face: set() for face in candidate_faces}
        for first, second in np.asarray(mesh.face_adjacency, dtype=int):
            if int(first) in candidate_faces and int(second) in candidate_faces:
                adjacency[int(first)].add(int(second))
                adjacency[int(second)].add(int(first))
        return adjacency

    def _cluster_faces(
        self,
        candidate_faces: set[int],
        adjacency: dict[int, set[int]],
        face_normals: np.ndarray,
        centroids: np.ndarray,
        *,
        max_normal_angle_degrees: float,
        max_plane_offset_m: float,
    ) -> list[np.ndarray]:
        max_angle_cos = math.cos(math.radians(max_normal_angle_degrees))
        remaining = set(candidate_faces)
        clusters: list[np.ndarray] = []
        while remaining:
            seed = remaining.pop()
            cluster = {seed}
            queue = [seed]
            while queue:
                current = queue.pop(0)
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in remaining:
                        continue
                    if not self._same_plane(
                        current,
                        neighbor,
                        face_normals,
                        centroids,
                        max_angle_cos=max_angle_cos,
                        max_plane_offset_m=max_plane_offset_m,
                    ):
                        continue
                    remaining.remove(neighbor)
                    cluster.add(neighbor)
                    queue.append(neighbor)
            clusters.append(np.array(sorted(cluster), dtype=int))
        return clusters

    def _same_plane(
        self,
        first: int,
        second: int,
        face_normals: np.ndarray,
        centroids: np.ndarray,
        *,
        max_angle_cos: float,
        max_plane_offset_m: float,
    ) -> bool:
        first_normal = face_normals[first]
        second_normal = face_normals[second]
        if float(np.dot(first_normal, second_normal)) < max_angle_cos:
            return False
        first_offset = float(np.dot(first_normal, centroids[first]))
        second_offset = float(np.dot(first_normal, centroids[second]))
        return abs(first_offset - second_offset) <= max_plane_offset_m

    def _roof_plane_from_cluster(
        self,
        cluster: np.ndarray,
        triangles: np.ndarray,
        face_normals: np.ndarray,
        face_areas: np.ndarray,
        centroids: np.ndarray,
        metadata: TopDownRenderMetadata,
        *,
        plane_id: str,
    ) -> RoofPlaneGeometry | None:
        weights = face_areas[cluster]
        normal = np.average(face_normals[cluster], axis=0, weights=weights)
        normal_length = float(np.linalg.norm(normal))
        if normal_length == 0:
            return None
        normal = normal / normal_length
        if normal[1] < 0:
            normal = -normal
        centroid = np.average(centroids[cluster], axis=0, weights=weights)
        plane_offset = float(np.dot(normal, centroid))

        footprint = self._cluster_footprint(triangles[cluster])
        if footprint is None or footprint.is_empty:
            return None
        exterior = self._rounded_exterior(footprint)
        render_polygon = [self.model_point_to_render_pixel(point, metadata) for point in exterior]
        tilt = math.degrees(math.acos(max(min(float(normal[1]), 1.0), -1.0)))
        azimuth = (math.degrees(math.atan2(float(normal[0]), float(normal[2]))) + 360) % 360

        return RoofPlaneGeometry(
            id=plane_id,
            normal=[round(float(value), 5) for value in normal],
            plane_offset=round(plane_offset, 5),
            centroid_model=[round(float(value), 4) for value in centroid],
            tilt_degrees=round(tilt, 2),
            azimuth_degrees=round(azimuth, 2),
            surface_area_m2=round(float(weights.sum()), 3),
            footprint_area_m2=round(float(footprint.area), 3),
            footprint_polygon=exterior,
            render_polygon_pixels=render_polygon,
            source_face_count=int(len(cluster)),
            suitability_score=self._suitability_score(tilt, azimuth, float(weights.sum())),
        )

    def _cluster_footprint(self, triangles: np.ndarray) -> Polygon | None:
        polygons = []
        for triangle in triangles:
            shape = self._safe_polygon([[float(vertex[0]), float(vertex[2])] for vertex in triangle])
            if shape is not None and not shape.is_empty:
                polygons.append(shape)
        if not polygons:
            return None
        union = unary_union(polygons)
        if isinstance(union, MultiPolygon):
            return max(union.geoms, key=lambda item: item.area)
        if isinstance(union, Polygon):
            return union
        return None

    def _safe_polygon(self, coordinates: Iterable[Iterable[float]]) -> Polygon | None:
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

    def _rounded_exterior(self, polygon: Polygon) -> list[list[float]]:
        coordinates = list(polygon.exterior.coords)
        if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
            coordinates = coordinates[:-1]
        return [[round(float(x), 4), round(float(y), 4)] for x, y in coordinates]

    def _suitability_score(self, tilt: float, azimuth: float, area_m2: float) -> float:
        south_delta = abs(((azimuth - 180 + 180) % 360) - 180)
        orientation_score = max(0.0, math.cos(math.radians(south_delta)))
        tilt_score = max(0.0, 1.0 - abs(tilt - 35.0) / 55.0)
        area_score = min(area_m2 / 40.0, 1.0)
        return round((0.55 * orientation_score) + (0.3 * tilt_score) + (0.15 * area_score), 4)

    def model_point_to_render_pixel(
        self,
        point: list[float] | tuple[float, float],
        metadata: TopDownRenderMetadata,
    ) -> list[int]:
        bounds = metadata.orthographic_world_bounds
        x = float(point[0])
        z = float(point[1])
        x_pixel = (x - bounds.x_min) / (bounds.x_max - bounds.x_min) * metadata.render_width
        y_pixel = (bounds.z_max - z) / (bounds.z_max - bounds.z_min) * metadata.render_height
        return [int(round(x_pixel)), int(round(y_pixel))]


def get_model_geometry_service() -> ModelGeometryService:
    return ModelGeometryService()
