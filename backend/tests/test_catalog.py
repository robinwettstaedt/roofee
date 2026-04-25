import csv

from fastapi.testclient import TestClient

from app.main import app
from app.models.catalog import ComponentCategory, ComponentKind
from app.services.catalog_service import (
    CatalogService,
    classify_component,
    parse_component_specs,
)


def test_parse_component_specs_from_names() -> None:
    module_spec, module_fields = parse_component_specs("PV Module 475W", "Module")
    battery_spec, battery_fields = parse_component_specs("Battery 10kWh", "BatteryStorage")
    inverter_spec, inverter_fields = parse_component_specs("Hybrid Inverter 10kW", "Inverter")
    heatpump_spec, heatpump_fields = parse_component_specs("Heat Pump 10.5kW", "Heatpump")

    assert module_spec.module_watt_peak == 475
    assert module_fields == {"module_watt_peak"}
    assert battery_spec.battery_capacity_kwh == 10
    assert battery_fields == {"battery_capacity_kwh"}
    assert inverter_spec.inverter_power_kw == 10
    assert inverter_fields == {"inverter_power_kw"}
    assert heatpump_spec.heatpump_nominal_power_kw == 10.5
    assert heatpump_fields == {"heatpump_nominal_power_kw"}


def test_classify_core_accessory_fee_service_mounting_and_package() -> None:
    assert classify_component("Module", "PV Module 475W") == (
        ComponentCategory.CORE_EQUIPMENT,
        ComponentKind.PV_MODULE,
    )
    assert classify_component("BatteryStorage", "AC Coupling Module") == (
        ComponentCategory.ACCESSORY,
        ComponentKind.ACCESSORY,
    )
    assert classify_component("AccessoryToModule", "Power Optimizer 600W") == (
        ComponentCategory.ACCESSORY,
        ComponentKind.ACCESSORY,
    )
    assert classify_component("InstallationFee", "Install Inverter") == (
        ComponentCategory.FEE,
        ComponentKind.INSTALLATION_FEE,
    )
    assert classify_component("ServiceFee", "Grid Registration") == (
        ComponentCategory.SERVICE,
        ComponentKind.SERVICE_FEE,
    )
    assert classify_component("ModuleFrameConstruction", "Substructure Flat Roof") == (
        ComponentCategory.MOUNTING,
        ComponentKind.MOUNTING,
    )
    assert classify_component("Other", "Complete Package 2 Sigenergy 10.8kWp + 9kWh") == (
        ComponentCategory.PACKAGE,
        ComponentKind.PACKAGE,
    )


def test_catalog_loader_dedupes_and_prefers_name_specs(tmp_path) -> None:
    dataset_dir = tmp_path / "snapshot"
    dataset_dir.mkdir()
    csv_path = dataset_dir / "project_options_parts.csv"
    fieldnames = [
        "project_id",
        "option_id",
        "option_number",
        "technology",
        "line_item_function",
        "component_type",
        "component_name",
        "component_brand",
        "quantity",
        "quantity_units",
        "module_watt_peak",
        "inverter_power_kw",
        "battery_capacity_kwh",
        "wb_charging_speed_kw",
        "heatpump_nominal_power_kw",
    ]
    rows = [
        {
            "project_id": "p1",
            "option_id": "o1",
            "option_number": "1",
            "technology": "solar",
            "line_item_function": "default",
            "component_type": "Module",
            "component_name": "PV Module 480W TOPCon",
            "component_brand": "Sunpro",
            "quantity": "1",
            "quantity_units": "Item",
            "module_watt_peak": "475",
            "inverter_power_kw": "",
            "battery_capacity_kwh": "",
            "wb_charging_speed_kw": "",
            "heatpump_nominal_power_kw": "",
        },
        {
            "project_id": "p2",
            "option_id": "o2",
            "option_number": "1",
            "technology": "solar",
            "line_item_function": "default",
            "component_type": "Module",
            "component_name": "PV Module 480W TOPCon",
            "component_brand": "Sunpro",
            "quantity": "2",
            "quantity_units": "Item",
            "module_watt_peak": "475",
            "inverter_power_kw": "",
            "battery_capacity_kwh": "",
            "wb_charging_speed_kw": "",
            "heatpump_nominal_power_kw": "",
        },
        {
            "project_id": "p3",
            "option_id": "o3",
            "option_number": "1",
            "technology": "ses",
            "line_item_function": "default",
            "component_type": "BatteryStorage",
            "component_name": "Battery 10kWh",
            "component_brand": "",
            "quantity": "1",
            "quantity_units": "Item",
            "module_watt_peak": "",
            "inverter_power_kw": "10000",
            "battery_capacity_kwh": "",
            "wb_charging_speed_kw": "",
            "heatpump_nominal_power_kw": "",
        },
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    catalog = CatalogService(tmp_path).build_catalog()

    assert catalog.summary.component_count == 2
    module = next(component for component in catalog.components if component.kind == "pv_module")
    battery = next(component for component in catalog.components if component.kind == "battery")

    assert module.observed_count == 2
    assert module.spec.module_watt_peak == 480
    assert "module_watt_peak_parsed_from_name" in module.warnings
    assert "module_watt_peak_csv_spec_disagrees" in module.warnings
    assert battery.spec.battery_capacity_kwh == 10
    assert "missing_brand" in battery.warnings


def test_catalog_endpoint_lists_components() -> None:
    client = TestClient(app)

    response = client.get("/api/catalog/components?kind=pv_module")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["component_count"] >= 1
    assert all(component["kind"] == "pv_module" for component in payload["components"])
