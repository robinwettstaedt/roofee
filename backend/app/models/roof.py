from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RoofAnalysisStatus(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"


class BoundingBoxPixels(BaseModel):
    x_min: int = Field(ge=0)
    y_min: int = Field(ge=0)
    x_max: int = Field(ge=0)
    y_max: int = Field(ge=0)


class RoofOutline(BaseModel):
    id: str
    source: str
    model_id: str
    class_name: str = "Building"
    bounding_box_pixels: BoundingBoxPixels
    polygon_pixels: list[list[int]]
    area_pixels: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RoofAnalysis(BaseModel):
    status: RoofAnalysisStatus
    satellite_image_url: str | None = None
    roof_outlines: list[RoofOutline] = Field(default_factory=list)
    roof_planes: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RoofSelectionRequest(BaseModel):
    satellite_image_url: str = Field(pattern=r"^/api/house-assets/[^/]+/overhead\.png$")
    selected_roof_outline_ids: list[str] = Field(min_length=1)


class SelectedRoof(BaseModel):
    satellite_image_url: str
    selected_roof_outline_ids: list[str]
    selected_roof_outlines: list[RoofOutline]
    bounding_box_pixels: BoundingBoxPixels
    area_pixels: float = Field(ge=0)


class RoofSelectionResponse(BaseModel):
    status: str
    selected_roof: SelectedRoof
    warnings: list[str] = Field(default_factory=list)


class RoofObstructionRequest(RoofSelectionRequest):
    pass


class RoofObstruction(BaseModel):
    id: str
    class_name: str
    polygon_pixels: list[list[int]]
    bounding_box_pixels: BoundingBoxPixels
    area_pixels: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str
    model_id: str


class RoofObstructionAnalysis(BaseModel):
    status: str
    selected_roof: SelectedRoof
    obstructions: list[RoofObstruction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OrthographicWorldBounds(BaseModel):
    x_min: float
    x_max: float
    z_min: float
    z_max: float
    y_min: float | None = None
    y_max: float | None = None


class TopDownRenderMetadata(BaseModel):
    render_width: int = Field(gt=0)
    render_height: int = Field(gt=0)
    orthographic_world_bounds: OrthographicWorldBounds
    model_orientation: dict[str, Any] = Field(default_factory=dict)


class RoofRegistrationRequest(RoofSelectionRequest):
    top_down_render_metadata: TopDownRenderMetadata


class SimilarityTransform(BaseModel):
    matrix: list[list[float]]
    scale: float
    rotation_degrees: float
    translation_pixels: list[float]
    algorithm: str


class MappedRoofOutline(BaseModel):
    id: str
    source_polygon_pixels: list[list[int]]
    render_polygon_pixels: list[list[int]]
    model_polygon: list[list[float]] = Field(default_factory=list)


class RegistrationQualityMetrics(BaseModel):
    algorithm: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    satellite_keypoints: int = 0
    render_keypoints: int = 0
    good_matches: int = 0
    inliers: int = 0
    inlier_ratio: float = 0
    mean_reprojection_error_pixels: float | None = None
    detected_render_roof_candidates: int | None = None
    best_render_candidate_bbox_iou: float | None = None


class RoofRegistrationResponse(BaseModel):
    status: str
    selected_roof: SelectedRoof
    transform: SimilarityTransform | None = None
    mapped_roof_outlines: list[MappedRoofOutline] = Field(default_factory=list)
    mapped_roof_polygon_pixels: list[list[int]] = Field(default_factory=list)
    render_metadata: TopDownRenderMetadata
    quality: RegistrationQualityMetrics
    warnings: list[str] = Field(default_factory=list)


class RoofGeometryAnalysisRequest(RoofSelectionRequest):
    model_radius_m: float = Field(default=50.0, gt=0, le=200)
    roof_edge_setback_m: float = Field(default=0.35, ge=0)
    obstruction_buffer_m: float = Field(default=0.25, ge=0)


class MappedRoofObstruction(BaseModel):
    id: str
    class_name: str
    source_polygon_pixels: list[list[int]]
    render_polygon_pixels: list[list[int]]
    model_polygon: list[list[float]]
    area_m2: float = Field(ge=0)


class RoofPlaneGeometry(BaseModel):
    id: str
    normal: list[float]
    tilt_degrees: float = Field(ge=0, le=90)
    azimuth_degrees: float = Field(ge=0, lt=360)
    surface_area_m2: float = Field(ge=0)
    footprint_area_m2: float = Field(ge=0)
    footprint_polygon: list[list[float]]
    render_polygon_pixels: list[list[int]]
    source_face_count: int = Field(ge=0)
    suitability_score: float = Field(ge=0, le=1)


class UsableRoofRegion(BaseModel):
    id: str
    roof_plane_id: str
    polygon: list[list[float]]
    render_polygon_pixels: list[list[int]]
    area_m2: float = Field(ge=0)


class RemovedRoofArea(BaseModel):
    id: str
    roof_plane_id: str
    source_type: str
    source_id: str
    class_name: str | None = None
    polygon: list[list[float]]
    area_m2: float = Field(ge=0)


class RoofGeometryAnalysisResponse(BaseModel):
    status: str
    selected_roof: SelectedRoof
    registration: RoofRegistrationResponse
    mapped_roof_outlines: list[MappedRoofOutline] = Field(default_factory=list)
    mapped_obstructions: list[MappedRoofObstruction] = Field(default_factory=list)
    roof_planes: list[RoofPlaneGeometry] = Field(default_factory=list)
    usable_regions: list[UsableRoofRegion] = Field(default_factory=list)
    removed_areas: list[RemovedRoofArea] = Field(default_factory=list)
    render_metadata: TopDownRenderMetadata
    warnings: list[str] = Field(default_factory=list)
