// Mirror of backend/app/models/roof.py — keep in sync.

export type RoofAnalysisStatus = "analyzed" | "skipped";

export type BoundingBoxPixels = {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
};

export type RoofOutline = {
  id: string;
  source: string;
  model_id: string;
  class_name: string;
  bounding_box_pixels: BoundingBoxPixels;
  polygon_pixels: number[][];
  area_pixels: number;
  confidence?: number | null;
};

export type RoofAnalysis = {
  status: RoofAnalysisStatus;
  satellite_image_url?: string | null;
  roof_outlines: RoofOutline[];
  roof_planes: unknown[];
  warnings: string[];
};

export type RoofSelectionRequest = {
  satellite_image_url: string;
  selected_roof_outline_ids: string[];
};

export type SelectedRoof = {
  satellite_image_url: string;
  selected_roof_outline_ids: string[];
  selected_roof_outlines: RoofOutline[];
  bounding_box_pixels: BoundingBoxPixels;
  area_pixels: number;
};

export type RoofSelectionResponse = {
  status: string;
  selected_roof: SelectedRoof;
  warnings: string[];
};

export type RoofObstructionRequest = RoofSelectionRequest;

export type RoofObstruction = {
  id: string;
  class_name: string;
  polygon_pixels: number[][];
  bounding_box_pixels: BoundingBoxPixels;
  area_pixels: number;
  confidence?: number | null;
  source: string;
  model_id: string;
};

export type RoofObstructionAnalysis = {
  status: string;
  selected_roof: SelectedRoof;
  obstructions: RoofObstruction[];
  warnings: string[];
};

export type OrthographicWorldBounds = {
  x_min: number;
  x_max: number;
  z_min: number;
  z_max: number;
  y_min?: number | null;
  y_max?: number | null;
};

export type TopDownRenderMetadata = {
  render_width: number;
  render_height: number;
  orthographic_world_bounds: OrthographicWorldBounds;
  model_orientation: Record<string, unknown>;
};

export type SimilarityTransform = {
  matrix: number[][];
  scale: number;
  rotation_degrees: number;
  translation_pixels: number[];
  algorithm: string;
};

export type MappedRoofOutline = {
  id: string;
  source_polygon_pixels: number[][];
  render_polygon_pixels: number[][];
  model_polygon: number[][];
};

export type RegistrationQualityMetrics = {
  algorithm?: string | null;
  confidence: number;
  satellite_keypoints: number;
  render_keypoints: number;
  good_matches: number;
  inliers: number;
  inlier_ratio: number;
  mean_reprojection_error_pixels?: number | null;
  detected_render_roof_candidates?: number | null;
  best_render_candidate_bbox_iou?: number | null;
};

export type RoofRegistrationResponse = {
  status: string;
  selected_roof: SelectedRoof;
  transform?: SimilarityTransform | null;
  mapped_roof_outlines: MappedRoofOutline[];
  mapped_roof_polygon_pixels: number[][];
  render_metadata: TopDownRenderMetadata;
  quality: RegistrationQualityMetrics;
  warnings: string[];
};

export type MappedRoofObstruction = {
  id: string;
  class_name: string;
  source_polygon_pixels: number[][];
  render_polygon_pixels: number[][];
  model_polygon: number[][];
  area_m2: number;
};

export type RoofPlaneGeometry = {
  id: string;
  normal: number[];
  plane_offset: number;
  centroid_model: number[];
  tilt_degrees: number;
  azimuth_degrees: number;
  surface_area_m2: number;
  footprint_area_m2: number;
  footprint_polygon: number[][];
  render_polygon_pixels: number[][];
  source_face_count: number;
  suitability_score: number;
};

export type UsableRoofRegion = {
  id: string;
  roof_plane_id: string;
  polygon: number[][];
  render_polygon_pixels: number[][];
  area_m2: number;
};

export type RemovedRoofArea = {
  id: string;
  roof_plane_id: string;
  source_type: string;
  source_id: string;
  class_name?: string | null;
  polygon: number[][];
  area_m2: number;
};

export type SolarModulePreset = {
  id: string;
  label: string;
  brand: string;
  model: string;
  watt_peak: number;
  length_m: number;
  width_m: number;
  thickness_m: number;
  source_url: string;
};

export type PanelPlacement = {
  id: string;
  roof_plane_id: string;
  usable_region_id: string;
  orientation: string;
  model_polygon: number[][];
  render_polygon_pixels: number[][];
  surface_polygon_3d: number[][];
  center_model: number[];
  normal_model: number[];
  length_axis_model: number[];
  width_axis_model: number[];
  clearance_m: number;
  thickness_m: number;
};

export type SolarLayoutOption = {
  id: string;
  strategy: string;
  module: SolarModulePreset;
  panel_count: number;
  system_size_kwp: number;
  estimated_annual_production_kwh?: number | null;
  annual_demand_kwh?: number | null;
  demand_coverage_ratio?: number | null;
  panel_placements: PanelPlacement[];
  warnings: string[];
};

export type RoofGeometryAnalysisResponse = {
  status: string;
  selected_roof: SelectedRoof;
  registration: RoofRegistrationResponse;
  mapped_roof_outlines: MappedRoofOutline[];
  mapped_obstructions: MappedRoofObstruction[];
  roof_planes: RoofPlaneGeometry[];
  usable_regions: UsableRoofRegion[];
  removed_areas: RemovedRoofArea[];
  solar_layout_options: SolarLayoutOption[];
  recommended_layout_option_id?: string | null;
  system_options: unknown[];
  render_metadata: TopDownRenderMetadata;
  warnings: string[];
};
