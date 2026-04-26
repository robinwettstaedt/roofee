from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.roof import RoofAnalysis
from app.models.roof import RoofGeometryAnalysisResponse


class RecommendationGoal(StrEnum):
    BALANCED = "balanced"
    LOWEST_UPFRONT_COST = "lowest_upfront_cost"
    MAXIMUM_SELF_CONSUMPTION = "maximum_self_consumption"
    MAXIMUM_ROOF_USAGE = "maximum_roof_usage"


class InclusionPreference(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    CONSIDER = "consider"


class ShadingLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    google_place_id: str | None = None
    annual_electricity_demand_kwh: float = Field(gt=0)
    electricity_price_per_kwh: float = Field(ge=0)
    load_profile: str = Field(default="H0", min_length=1)
    num_inhabitants: int = Field(ge=1)
    house_size_sqm: float = Field(gt=0)
    heating_existing_type: str = Field(min_length=1)
    has_ev: bool
    has_solar: bool
    has_storage: bool
    has_wallbox: bool
    recommendation_goal: RecommendationGoal
    battery_preference: InclusionPreference
    heat_pump_preference: InclusionPreference
    ev_charger_preference: InclusionPreference

    energy_price_increase: float | None = Field(default=None, ge=0)
    energy_price_with_flexible_tariff_per_kwh: float | None = Field(default=None, ge=0)
    base_price_per_month: float | None = Field(default=None, ge=0)
    base_price_increase: float | None = Field(default=None, ge=0)
    ev_annual_drive_distance_km: float | None = Field(default=None, ge=0)
    solar_size_kwp: float | None = Field(default=None, gt=0)
    solar_angle: float | None = Field(default=None, ge=0, le=90)
    solar_orientation: float | None = Field(default=None, ge=0, lt=360)
    solar_built_year: int | None = Field(default=None, ge=1900, le=2100)
    solar_feedin_renumeration: float | None = Field(default=None, ge=0)
    solar_feedin_renumeration_post_eeg: float | None = Field(default=None, ge=0)
    storage_size_kwh: float | None = Field(default=None, gt=0)
    storage_built_year: int | None = Field(default=None, ge=1900, le=2100)
    wallbox_charge_speed_kw: float | None = Field(default=None, gt=0)
    heating_existing_cost_per_year: float | None = Field(default=None, ge=0)
    heating_existing_cost_increase_per_year: float | None = Field(default=None, ge=0)
    heating_existing_electricity_demand_kwh: float | None = Field(default=None, ge=0)
    heating_existing_heating_demand_kwh: float | None = Field(default=None, ge=0)
    house_built_year: int | None = Field(default=None, ge=1800, le=2100)
    renovation_standard: str | None = None
    roof_covering_type: str | None = None
    electrical_panel_status: str | None = None
    preferred_brands: list[str] = Field(default_factory=list)
    excluded_brands: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    shading_level: ShadingLevel = ShadingLevel.UNKNOWN
    obstruction_notes: str | None = None
    usable_roof_area_sqm: float | None = Field(default=None, gt=0)
    roof_tilt: float | None = Field(default=None, ge=0, le=90)
    roof_azimuth: float | None = Field(default=None, ge=0, lt=360)


class EstimatedInput(BaseModel):
    field: str
    value: Any
    reason: str


class ModelFileValidation(BaseModel):
    provided: bool
    filename: str | None = None
    size_bytes: int | None = None
    format: str | None = None
    version: int | None = None


class MonthlySolarWeather(BaseModel):
    month: int = Field(ge=1, le=12)
    horizontal_irradiation_kwh_per_m2: float
    optimal_irradiation_kwh_per_m2: float
    average_temperature_c: float


class SolarWeatherMetadata(BaseModel):
    provider: str
    api_version: str
    latitude: float
    longitude: float
    source_url: str
    request_params: dict[str, str | float | int]
    annual_horizontal_irradiation_kwh_per_m2: float
    annual_optimal_irradiation_kwh_per_m2: float
    average_temperature_c: float
    monthly: list[MonthlySolarWeather]


class LatLng(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LatLngBox(BaseModel):
    southwest: LatLng
    northeast: LatLng


class GoogleSolarDate(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None


class SolarRoofSegment(BaseModel):
    center: LatLng | None = None
    bounding_box: LatLngBox | None = None
    pitch_degrees: float | None = None
    azimuth_degrees: float | None = None
    plane_height_at_center_meters: float | None = None
    area_meters2: float | None = None
    sunshine_quantiles: list[float] = Field(default_factory=list)


class SolarBuildingData(BaseModel):
    name: str | None = None
    center: LatLng
    bounding_box: LatLngBox | None = None
    imagery_date: GoogleSolarDate | None = None
    imagery_processed_date: GoogleSolarDate | None = None
    imagery_quality: str | None = None
    region_code: str | None = None
    postal_code: str | None = None
    administrative_area: str | None = None
    roof_segments: list[SolarRoofSegment] = Field(default_factory=list)


class Google3DTilesData(BaseModel):
    root_url: str
    origin: LatLng


class HouseData(BaseModel):
    status: str
    provider: str
    location: LatLng
    solar_building: SolarBuildingData
    overhead_image_url: str
    tiles_3d: Google3DTilesData
    warnings: list[str] = Field(default_factory=list)


class RecommendationValidationResponse(BaseModel):
    status: str
    input: RecommendationRequest
    present_inputs: list[str]
    missing_required_inputs: list[str]
    estimated_inputs: list[EstimatedInput]
    warnings: list[str]
    model_file: ModelFileValidation
    solar_weather: SolarWeatherMetadata | None = None
    house_data: HouseData | None = None
    roof_analysis: RoofAnalysis | None = None


class SelectedGoogle3DTile(BaseModel):
    uri: str | None = None
    geometric_error: float | None = Field(default=None, ge=0)
    transform: list[float] = Field(default_factory=list)


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: RecommendationRequest
    picked_location: LatLng
    selected_tile: SelectedGoogle3DTile | None = None
    model_radius_m: float = Field(default=50.0, gt=0, le=200)
    roof_edge_setback_m: float = Field(default=0.35, ge=0)
    obstruction_buffer_m: float = Field(default=0.25, ge=0)


class ProposalResponse(BaseModel):
    status: str
    recommendation: RecommendationValidationResponse
    roof_geometry: RoofGeometryAnalysisResponse
    warnings: list[str] = Field(default_factory=list)
