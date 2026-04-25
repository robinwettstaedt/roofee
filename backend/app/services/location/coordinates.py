from __future__ import annotations

from math import cos, radians, sin, sqrt
from typing import Any


Vector3 = tuple[float, float, float]
Matrix4 = tuple[float, ...]

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
IDENTITY_MATRIX4: Matrix4 = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def lla_to_ecef(latitude: float, longitude: float, altitude_m: float = 0.0) -> Vector3:
    lat = radians(latitude)
    lon = radians(longitude)
    sin_lat = sin(lat)
    cos_lat = cos(lat)
    prime_vertical_radius = WGS84_A / sqrt(1 - WGS84_E2 * sin_lat * sin_lat)

    x = (prime_vertical_radius + altitude_m) * cos_lat * cos(lon)
    y = (prime_vertical_radius + altitude_m) * cos_lat * sin(lon)
    z = (prime_vertical_radius * (1 - WGS84_E2) + altitude_m) * sin_lat
    return (x, y, z)


def euclidean_distance(a: Vector3, b: Vector3) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def sphere_intersects(center_a: Vector3, radius_a: float, center_b: Vector3, radius_b: float) -> bool:
    return euclidean_distance(center_a, center_b) <= radius_a + radius_b


def to_matrix4(value: Any) -> Matrix4:
    if not isinstance(value, list) or len(value) != 16:
        return IDENTITY_MATRIX4
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return IDENTITY_MATRIX4


def matmul4(a: Matrix4, b: Matrix4) -> Matrix4:
    values: list[float] = []
    for column in range(4):
        for row in range(4):
            values.append(sum(a[k * 4 + row] * b[column * 4 + k] for k in range(4)))
    return tuple(values)


def transform_point(matrix: Matrix4, point: Vector3) -> Vector3:
    x, y, z = point
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def bounding_sphere(bounding_volume: dict[str, Any], world_transform: Matrix4) -> tuple[Vector3, float]:
    if "box" in bounding_volume:
        box = _float_list(bounding_volume["box"], expected_length=12)
        center = transform_point(world_transform, (box[0], box[1], box[2]))
        radius = sqrt(
            _vector_length_squared((box[3], box[4], box[5]))
            + _vector_length_squared((box[6], box[7], box[8]))
            + _vector_length_squared((box[9], box[10], box[11]))
        )
        return center, radius * _max_transform_scale(world_transform)

    if "sphere" in bounding_volume:
        sphere = _float_list(bounding_volume["sphere"], expected_length=4)
        center = transform_point(world_transform, (sphere[0], sphere[1], sphere[2]))
        return center, abs(sphere[3]) * _max_transform_scale(world_transform)

    if "region" in bounding_volume:
        region = _float_list(bounding_volume["region"], expected_length=6)
        return _region_bounding_sphere(region)

    raise ValueError("Unsupported 3D Tiles bounding volume.")


def _region_bounding_sphere(region: list[float]) -> tuple[Vector3, float]:
    west, south, east, north, min_height, max_height = region
    corners = [
        lla_to_ecef(latitude=lat * 180.0 / 3.141592653589793, longitude=lon * 180.0 / 3.141592653589793, altitude_m=height)
        for lon in (west, east)
        for lat in (south, north)
        for height in (min_height, max_height)
    ]
    center = (
        sum(point[0] for point in corners) / len(corners),
        sum(point[1] for point in corners) / len(corners),
        sum(point[2] for point in corners) / len(corners),
    )
    return center, max(euclidean_distance(center, point) for point in corners)


def _max_transform_scale(matrix: Matrix4) -> float:
    return max(
        sqrt(matrix[0] ** 2 + matrix[1] ** 2 + matrix[2] ** 2),
        sqrt(matrix[4] ** 2 + matrix[5] ** 2 + matrix[6] ** 2),
        sqrt(matrix[8] ** 2 + matrix[9] ** 2 + matrix[10] ** 2),
    )


def _vector_length_squared(vector: Vector3) -> float:
    return vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2


def _float_list(value: Any, expected_length: int) -> list[float]:
    if not isinstance(value, list) or len(value) != expected_length:
        raise ValueError("Malformed 3D Tiles bounding volume.")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed 3D Tiles bounding volume.") from exc
