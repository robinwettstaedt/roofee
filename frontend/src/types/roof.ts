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
