from enum import StrEnum

from pydantic import BaseModel, Field


class ComponentCategory(StrEnum):
    CORE_EQUIPMENT = "core_equipment"
    ACCESSORY = "accessory"
    FEE = "fee"
    SERVICE = "service"
    MOUNTING = "mounting"
    PACKAGE = "package"
    OTHER = "other"


class ComponentKind(StrEnum):
    PV_MODULE = "pv_module"
    INVERTER = "inverter"
    BATTERY = "battery"
    HEAT_PUMP = "heat_pump"
    WALLBOX = "wallbox"
    ACCESSORY = "accessory"
    INSTALLATION_FEE = "installation_fee"
    SERVICE_FEE = "service_fee"
    MOUNTING = "mounting"
    PACKAGE = "package"
    OTHER = "other"


class ComponentSpec(BaseModel):
    module_watt_peak: float | None = None
    inverter_power_kw: float | None = None
    battery_capacity_kwh: float | None = None
    wallbox_charging_power_kw: float | None = None
    heatpump_nominal_power_kw: float | None = None


class CatalogComponent(BaseModel):
    id: str
    component_type: str
    component_name: str
    component_brand: str | None = None
    technology: str | None = None
    category: ComponentCategory
    kind: ComponentKind
    spec: ComponentSpec = Field(default_factory=ComponentSpec)
    source_datasets: list[str]
    observed_count: int
    warnings: list[str] = Field(default_factory=list)


class CatalogSummary(BaseModel):
    component_count: int
    source_datasets: list[str]
    counts_by_category: dict[str, int]
    counts_by_kind: dict[str, int]
    warning_count: int


class ComponentCatalog(BaseModel):
    summary: CatalogSummary
    components: list[CatalogComponent]
