from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.catalog import ComponentCategory, ComponentKind


class EquipmentRole(StrEnum):
    PV_MODULE = "pv_module"
    INVERTER = "inverter"
    BATTERY = "battery"
    HEAT_PUMP = "heat_pump"
    WALLBOX = "wallbox"
    MOUNTING = "mounting"
    ACCESSORY = "accessory"
    INSTALLATION = "installation"
    SERVICE = "service"


class BomLineSource(StrEnum):
    PANEL_PRESET = "panel_preset"
    CATALOG = "catalog"


class CalculationAssumption(BaseModel):
    field: str
    value: Any
    source: str
    reason: str


class SizedEquipment(BaseModel):
    role: EquipmentRole
    component_id: str | None = None
    component_name: str
    component_brand: str | None = None
    component_type: str | None = None
    kind: ComponentKind | None = None
    quantity: float = Field(default=1, ge=0)
    quantity_units: str = "Item"
    selected_specs: dict[str, float] = Field(default_factory=dict)
    target_specs: dict[str, float] = Field(default_factory=dict)
    selection_basis: str
    source: BomLineSource
    warnings: list[str] = Field(default_factory=list)


class BomLineItem(BaseModel):
    id: str
    role: EquipmentRole
    component_id: str | None = None
    component_name: str
    component_brand: str | None = None
    component_type: str | None = None
    category: ComponentCategory | None = None
    kind: ComponentKind | None = None
    quantity: float = Field(ge=0)
    quantity_units: str = "Item"
    source: BomLineSource
    selected_specs: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BomSummary(BaseModel):
    line_item_count: int = Field(ge=0)
    panel_count: int = Field(ge=0)
    system_size_kwp: float = Field(ge=0)
    inverter_power_kw: float | None = Field(default=None, ge=0)
    battery_capacity_kwh: float | None = Field(default=None, ge=0)
    heatpump_nominal_power_kw: float | None = Field(default=None, ge=0)
    wallbox_charging_power_kw: float | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)


class SystemRecommendationOption(BaseModel):
    id: str
    layout_option_id: str
    strategy: str
    panel_count: int = Field(ge=0)
    system_size_kwp: float = Field(ge=0)
    estimated_annual_production_kwh: float | None = Field(default=None, ge=0)
    annual_demand_kwh: float | None = Field(default=None, gt=0)
    demand_coverage_ratio: float | None = Field(default=None, ge=0)
    equipment: list[SizedEquipment] = Field(default_factory=list)
    bom: list[BomLineItem] = Field(default_factory=list)
    summary: BomSummary
    assumptions: list[CalculationAssumption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
