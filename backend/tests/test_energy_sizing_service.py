from app.models.bom import EquipmentRole
from app.models.catalog import (
    CatalogComponent,
    CatalogSummary,
    ComponentCatalog,
    ComponentCategory,
    ComponentKind,
    ComponentSpec,
)
from app.models.roof import SolarLayoutOption
from app.services.bom.bom_service import BomService
from app.services.roof.solar_layout_service import MODULE_PRESETS
from app.services.sizing.battery_sizing_service import BatterySizingService
from app.services.sizing.energy_sizing_service import EnergySizingService
from app.services.sizing.heat_pump_sizing_service import HeatPumpSizingService


class FakeCatalogService:
    def build_catalog(self) -> ComponentCatalog:
        components = [
            _component(
                "inv-5",
                ComponentKind.INVERTER,
                ComponentCategory.CORE_EQUIPMENT,
                "Inverter",
                "Sigenergy Hybrid Inverter 5kW",
                "Sigenergy",
                inverter_power_kw=5,
            ),
            _component(
                "inv-10",
                ComponentKind.INVERTER,
                ComponentCategory.CORE_EQUIPMENT,
                "Inverter",
                "Sigenergy Hybrid Inverter 10kW",
                "Sigenergy",
                inverter_power_kw=10,
            ),
            _component(
                "bat-5",
                ComponentKind.BATTERY,
                ComponentCategory.CORE_EQUIPMENT,
                "BatteryStorage",
                "Huawei Battery 5kWh",
                "Huawei",
                battery_capacity_kwh=5,
            ),
            _component(
                "bat-10",
                ComponentKind.BATTERY,
                ComponentCategory.CORE_EQUIPMENT,
                "BatteryStorage",
                "Huawei Battery 10kWh",
                "Huawei",
                battery_capacity_kwh=10,
            ),
            _component(
                "hp-5",
                ComponentKind.HEAT_PUMP,
                ComponentCategory.CORE_EQUIPMENT,
                "Heatpump",
                "Vaillant Heat Pump 5.5kW 230V",
                "Vaillant",
                heatpump_nominal_power_kw=5.5,
            ),
            _component(
                "hp-10",
                ComponentKind.HEAT_PUMP,
                ComponentCategory.CORE_EQUIPMENT,
                "Heatpump",
                "Vaillant Heat Pump 10.5kW 400V",
                "Vaillant",
                heatpump_nominal_power_kw=10.5,
            ),
            _component(
                "wallbox-11",
                ComponentKind.WALLBOX,
                ComponentCategory.CORE_EQUIPMENT,
                "Wallbox",
                "EcoFlow Wallbox 11kW",
                "EcoFlow",
                wallbox_charging_power_kw=11,
            ),
            _component(
                "wallbox-22",
                ComponentKind.WALLBOX,
                ComponentCategory.CORE_EQUIPMENT,
                "Wallbox",
                "EcoFlow Wallbox 22kW",
                "EcoFlow",
                wallbox_charging_power_kw=22,
            ),
            _component(
                "mount-1",
                ComponentKind.MOUNTING,
                ComponentCategory.MOUNTING,
                "ModuleFrameConstruction",
                "Substructure Concrete Tile Roof",
                None,
            ),
            _component(
                "mount-2",
                ComponentKind.MOUNTING,
                ComponentCategory.MOUNTING,
                "ModuleFrameConstruction",
                "Scaffolding Setup & Removal",
                None,
            ),
            _component(
                "optimizer",
                ComponentKind.ACCESSORY,
                ComponentCategory.ACCESSORY,
                "AccessoryToModule",
                "Power Optimizer 600W",
                "Huawei",
            ),
            _component(
                "planning",
                ComponentKind.INSTALLATION_FEE,
                ComponentCategory.FEE,
                "InstallationFee",
                "Planning & Consulting",
                None,
            ),
            _component(
                "grid",
                ComponentKind.SERVICE_FEE,
                ComponentCategory.SERVICE,
                "ServiceFee",
                "Grid Registration",
                None,
            ),
            _component(
                "travel",
                ComponentKind.SERVICE_FEE,
                ComponentCategory.SERVICE,
                "ServiceFee",
                "Travel & Logistics Flat Rate",
                None,
            ),
            _component(
                "install-inverter",
                ComponentKind.INSTALLATION_FEE,
                ComponentCategory.FEE,
                "InstallationFee",
                "Install Inverter",
                None,
            ),
            _component(
                "install-battery",
                ComponentKind.INSTALLATION_FEE,
                ComponentCategory.FEE,
                "InstallationFee",
                "Install Battery Storage",
                None,
            ),
            _component(
                "install-wallbox",
                ComponentKind.INSTALLATION_FEE,
                ComponentCategory.FEE,
                "InstallationFee",
                "Install Wallbox",
                None,
            ),
            _component(
                "install-heatpump",
                ComponentKind.INSTALLATION_FEE,
                ComponentCategory.FEE,
                "InstallationFee",
                "Heat Pump Installation Compact",
                "Vaillant",
            ),
        ]
        return ComponentCatalog(
            summary=CatalogSummary(
                component_count=len(components),
                source_datasets=["test"],
                counts_by_category={},
                counts_by_kind={},
                warning_count=0,
            ),
            components=components,
        )


def test_energy_sizing_builds_catalog_backed_full_system_bom() -> None:
    service = _service()

    options, warnings = service.build_system_options(
        layouts=[_layout(panel_count=12, system_size_kwp=5.76)],
        project_context={
            "annual_electricity_demand_kwh": 4500,
            "recommendation_goal": "balanced",
            "battery_preference": "consider",
            "heat_pump_preference": "consider",
            "ev_charger_preference": "consider",
            "has_storage": False,
            "has_wallbox": False,
            "has_ev": True,
            "heating_existing_type": "gas",
            "heating_existing_heating_demand_kwh": 12000,
            "house_size_sqm": 140,
        },
    )

    assert warnings == []
    option = options[0]
    roles = {item.role for item in option.equipment}
    assert {
        EquipmentRole.PV_MODULE,
        EquipmentRole.INVERTER,
        EquipmentRole.BATTERY,
        EquipmentRole.HEAT_PUMP,
        EquipmentRole.WALLBOX,
    }.issubset(roles)
    assert option.summary.inverter_power_kw == 5
    assert option.summary.battery_capacity_kwh == 5
    assert option.summary.heatpump_nominal_power_kw == 5.5
    assert option.summary.wallbox_charging_power_kw == 11
    panel_line = next(line for line in option.bom if line.role == EquipmentRole.PV_MODULE)
    assert panel_line.quantity == 12
    assert panel_line.source == "panel_preset"
    assert panel_line.selected_specs["length_m"] == MODULE_PRESETS["standard"].length_m
    assert any(line.component_name == "Power Optimizer 600W" and line.quantity == 12 for line in option.bom)


def test_energy_sizing_respects_exclusions_and_existing_equipment() -> None:
    service = _service()

    options, _ = service.build_system_options(
        layouts=[_layout(panel_count=8, system_size_kwp=3.84)],
        project_context={
            "recommendation_goal": "lowest_upfront_cost",
            "battery_preference": "exclude",
            "heat_pump_preference": "exclude",
            "ev_charger_preference": "consider",
            "has_storage": True,
            "has_wallbox": False,
            "has_ev": False,
            "heating_existing_type": "heat pump",
            "house_size_sqm": 120,
        },
    )

    roles = {item.role for item in options[0].equipment}
    assert EquipmentRole.BATTERY not in roles
    assert EquipmentRole.HEAT_PUMP not in roles
    assert EquipmentRole.WALLBOX not in roles
    assert EquipmentRole.INVERTER in roles
    assert any(assumption.field == "battery" for assumption in options[0].assumptions)


def test_energy_sizing_warns_for_heat_pump_fallback_estimate() -> None:
    service = _service()

    options, _ = service.build_system_options(
        layouts=[_layout(panel_count=20, system_size_kwp=9.6)],
        project_context={
            "recommendation_goal": "maximum_self_consumption",
            "battery_preference": "include",
            "heat_pump_preference": "include",
            "ev_charger_preference": "exclude",
            "has_storage": False,
            "has_wallbox": False,
            "has_ev": False,
            "heating_existing_type": "oil",
            "house_size_sqm": 160,
            "house_built_year": 1970,
        },
    )

    option = options[0]
    assert option.summary.battery_capacity_kwh == 10
    assert option.summary.heatpump_nominal_power_kw == 10.5
    assert any("DIN EN 12831" in warning for warning in option.warnings)
    assert any(assumption.field == "heatpump_nominal_power_kw" for assumption in option.assumptions)


def _service() -> EnergySizingService:
    return EnergySizingService(
        catalog_service=FakeCatalogService(),
        bom_service=BomService(),
        battery_sizing_service=BatterySizingService(),
        heat_pump_sizing_service=HeatPumpSizingService(),
    )


def _layout(panel_count: int, system_size_kwp: float) -> SolarLayoutOption:
    return SolarLayoutOption(
        id="better",
        strategy="demand_match",
        module=MODULE_PRESETS["standard"],
        panel_count=panel_count,
        system_size_kwp=system_size_kwp,
        estimated_annual_production_kwh=system_size_kwp * 950,
        annual_demand_kwh=4500,
        demand_coverage_ratio=round(system_size_kwp * 950 / 4500, 3),
    )


def _component(
    component_id: str,
    kind: ComponentKind,
    category: ComponentCategory,
    component_type: str,
    component_name: str,
    component_brand: str | None,
    *,
    inverter_power_kw: float | None = None,
    battery_capacity_kwh: float | None = None,
    wallbox_charging_power_kw: float | None = None,
    heatpump_nominal_power_kw: float | None = None,
) -> CatalogComponent:
    return CatalogComponent(
        id=component_id,
        component_type=component_type,
        component_name=component_name,
        component_brand=component_brand,
        technology="solar",
        category=category,
        kind=kind,
        spec=ComponentSpec(
            inverter_power_kw=inverter_power_kw,
            battery_capacity_kwh=battery_capacity_kwh,
            wallbox_charging_power_kw=wallbox_charging_power_kw,
            heatpump_nominal_power_kw=heatpump_nominal_power_kw,
        ),
        source_datasets=["test"],
        observed_count=10,
    )
