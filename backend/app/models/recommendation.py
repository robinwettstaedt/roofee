from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RecommendationValidationResponse(BaseModel):
    status: str
    input: RecommendationRequest
    present_inputs: list[str]
    missing_required_inputs: list[str]
    estimated_inputs: list[EstimatedInput]
    warnings: list[str]
    model_file: ModelFileValidation
