// Mirror of backend/app/models/recommendation.py — keep in sync.
// String literal unions stand in for the backend StrEnums.

import type { RoofAnalysis } from "./roof";

export type RecommendationGoal =
  | "balanced"
  | "lowest_upfront_cost"
  | "maximum_self_consumption"
  | "maximum_roof_usage";

export type InclusionPreference = "include" | "exclude" | "consider";

export type ShadingLevel = "none" | "low" | "medium" | "high" | "unknown";

export type RecommendationRequest = {
  // Required
  address: string;
  latitude: number;
  longitude: number;
  google_place_id?: string | null;
  annual_electricity_demand_kwh: number;
  electricity_price_per_kwh: number;
  load_profile: string;
  num_inhabitants: number;
  house_size_sqm: number;
  heating_existing_type: string;
  has_ev: boolean;
  has_solar: boolean;
  has_storage: boolean;
  has_wallbox: boolean;
  recommendation_goal: RecommendationGoal;
  battery_preference: InclusionPreference;
  heat_pump_preference: InclusionPreference;
  ev_charger_preference: InclusionPreference;

  // Optional long tail
  energy_price_increase?: number | null;
  energy_price_with_flexible_tariff_per_kwh?: number | null;
  base_price_per_month?: number | null;
  base_price_increase?: number | null;
  ev_annual_drive_distance_km?: number | null;
  solar_size_kwp?: number | null;
  solar_angle?: number | null;
  solar_orientation?: number | null;
  solar_built_year?: number | null;
  solar_feedin_renumeration?: number | null;
  solar_feedin_renumeration_post_eeg?: number | null;
  storage_size_kwh?: number | null;
  storage_built_year?: number | null;
  wallbox_charge_speed_kw?: number | null;
  heating_existing_cost_per_year?: number | null;
  heating_existing_cost_increase_per_year?: number | null;
  heating_existing_electricity_demand_kwh?: number | null;
  heating_existing_heating_demand_kwh?: number | null;
  house_built_year?: number | null;
  renovation_standard?: string | null;
  roof_covering_type?: string | null;
  electrical_panel_status?: string | null;
  preferred_brands?: string[];
  excluded_brands?: string[];
  budget_range?: string | null;
  shading_level?: ShadingLevel;
  obstruction_notes?: string | null;
  usable_roof_area_sqm?: number | null;
  roof_tilt?: number | null;
  roof_azimuth?: number | null;
};

export type EstimatedInput = {
  field: string;
  value: unknown;
  reason: string;
};

export type ModelFileValidation = {
  provided: boolean;
  filename?: string | null;
  size_bytes?: number | null;
  format?: string | null;
  version?: number | null;
};

export type MonthlySolarWeather = {
  month: number; // 1..12
  horizontal_irradiation_kwh_per_m2: number;
  optimal_irradiation_kwh_per_m2: number;
  average_temperature_c: number;
};

export type SolarWeatherMetadata = {
  provider: string;
  api_version: string;
  latitude: number;
  longitude: number;
  source_url: string;
  request_params: Record<string, string | number>;
  annual_horizontal_irradiation_kwh_per_m2: number;
  annual_optimal_irradiation_kwh_per_m2: number;
  average_temperature_c: number;
  monthly: MonthlySolarWeather[];
};

export type LatLng = {
  latitude: number;
  longitude: number;
};

export type LatLngBox = {
  southwest: LatLng;
  northeast: LatLng;
};

export type GoogleSolarDate = {
  year?: number | null;
  month?: number | null;
  day?: number | null;
};

export type SolarRoofSegment = {
  center?: LatLng | null;
  bounding_box?: LatLngBox | null;
  pitch_degrees?: number | null;
  azimuth_degrees?: number | null;
  plane_height_at_center_meters?: number | null;
  area_meters2?: number | null;
  sunshine_quantiles?: number[];
};

export type SolarBuildingData = {
  name?: string | null;
  center: LatLng;
  bounding_box?: LatLngBox | null;
  imagery_date?: GoogleSolarDate | null;
  imagery_processed_date?: GoogleSolarDate | null;
  imagery_quality?: string | null;
  region_code?: string | null;
  postal_code?: string | null;
  administrative_area?: string | null;
  roof_segments: SolarRoofSegment[];
};

export type Google3DTilesData = {
  root_url: string;
  origin: LatLng;
};

export type HouseData = {
  status: string;
  provider: string;
  location: LatLng;
  solar_building: SolarBuildingData;
  overhead_image_url: string;
  tiles_3d: Google3DTilesData;
  warnings: string[];
};

export type RecommendationValidationResponse = {
  status: string;
  input: RecommendationRequest;
  present_inputs: string[];
  missing_required_inputs: string[];
  estimated_inputs: EstimatedInput[];
  warnings: string[];
  model_file: ModelFileValidation;
  solar_weather?: SolarWeatherMetadata | null;
  house_data?: HouseData | null;
  roof_analysis?: RoofAnalysis | null;
};

// Metadata from POST /api/location/house-model — emitted in `Roofee-Metadata`
// response header, parse with JSON.parse.
export type GeocodingMetadata = {
  source: string;
  formatted_address?: string | null;
  place_id?: string | null;
  location_type?: string | null;
};

export type TileSelection = {
  uri: string;
  geometric_error: number;
  bounding_sphere_radius_m: number;
  center_distance_m: number;
  transform: number[];
};

export type HouseModelMetadata = {
  anchor_latitude: number;
  anchor_longitude: number;
  radius_m: number;
  geocoding: GeocodingMetadata;
  tile: TileSelection;
  candidate_tile_count: number;
  copyright?: string | null;
  glb_size_bytes: number;
};
