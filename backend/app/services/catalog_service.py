import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.models.catalog import (
    CatalogComponent,
    CatalogSummary,
    ComponentCatalog,
    ComponentCategory,
    ComponentKind,
    ComponentSpec,
)


SPEC_COLUMNS = (
    "module_watt_peak",
    "inverter_power_kw",
    "battery_capacity_kwh",
    "wb_charging_speed_kw",
    "heatpump_nominal_power_kw",
)


@dataclass
class _CatalogAccumulator:
    component_type: str
    component_name: str
    component_brand: str | None
    technologies: Counter[str] = field(default_factory=Counter)
    source_datasets: set[str] = field(default_factory=set)
    observed_count: int = 0
    numeric_specs: dict[str, list[float]] = field(default_factory=lambda: {key: [] for key in SPEC_COLUMNS})


class CatalogService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def build_catalog(self) -> ComponentCatalog:
        accumulators = self._load_components()
        components = [self._build_component(acc) for acc in accumulators.values()]
        components.sort(
            key=lambda item: (
                item.category.value,
                item.kind.value,
                item.component_brand or "",
                item.component_name.lower(),
            )
        )

        counts_by_category = Counter(component.category.value for component in components)
        counts_by_kind = Counter(component.kind.value for component in components)
        source_datasets = sorted(
            {dataset for component in components for dataset in component.source_datasets}
        )

        return ComponentCatalog(
            summary=CatalogSummary(
                component_count=len(components),
                source_datasets=source_datasets,
                counts_by_category=dict(sorted(counts_by_category.items())),
                counts_by_kind=dict(sorted(counts_by_kind.items())),
                warning_count=sum(1 for component in components if component.warnings),
            ),
            components=components,
        )

    def _load_components(self) -> dict[tuple[str, str, str], _CatalogAccumulator]:
        if not self.data_dir.exists():
            return {}

        components: dict[tuple[str, str, str], _CatalogAccumulator] = {}
        for csv_path in sorted(self.data_dir.glob("*/project_options_parts.csv")):
            dataset_name = csv_path.parent.name
            with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    component_name = row.get("component_name", "").strip()
                    component_type = row.get("component_type", "").strip()
                    if not component_name or not component_type:
                        continue

                    component_brand = row.get("component_brand", "").strip() or None
                    key = (component_type, component_brand or "", component_name)
                    accumulator = components.setdefault(
                        key,
                        _CatalogAccumulator(
                            component_type=component_type,
                            component_name=component_name,
                            component_brand=component_brand,
                        ),
                    )
                    accumulator.observed_count += 1
                    accumulator.source_datasets.add(dataset_name)

                    technology = row.get("technology", "").strip()
                    if technology:
                        accumulator.technologies[technology] += 1

                    for column in SPEC_COLUMNS:
                        value = _parse_float(row.get(column, ""))
                        if value is not None:
                            accumulator.numeric_specs[column].append(value)

        return components

    def _build_component(self, accumulator: _CatalogAccumulator) -> CatalogComponent:
        category, kind = classify_component(
            accumulator.component_type,
            accumulator.component_name,
        )
        parsed_spec, parsed_fields = parse_component_specs(
            accumulator.component_name,
            accumulator.component_type,
            kind,
        )
        spec = _merge_specs(parsed_spec, accumulator.numeric_specs, kind)
        warnings = _build_warnings(
            component_brand=accumulator.component_brand,
            category=category,
            kind=kind,
            parsed_spec=parsed_spec,
            parsed_fields=parsed_fields,
            numeric_specs=accumulator.numeric_specs,
            merged_spec=spec,
        )

        return CatalogComponent(
            id=_component_id(
                accumulator.component_type,
                accumulator.component_brand,
                accumulator.component_name,
            ),
            component_type=accumulator.component_type,
            component_name=accumulator.component_name,
            component_brand=accumulator.component_brand,
            technology=accumulator.technologies.most_common(1)[0][0]
            if accumulator.technologies
            else None,
            category=category,
            kind=kind,
            spec=spec,
            source_datasets=sorted(accumulator.source_datasets),
            observed_count=accumulator.observed_count,
            warnings=warnings,
        )


def get_catalog_service() -> CatalogService:
    return CatalogService(settings.data_dir)


def classify_component(
    component_type: str,
    component_name: str,
) -> tuple[ComponentCategory, ComponentKind]:
    normalized_name = component_name.casefold()

    if component_type == "Module":
        return ComponentCategory.CORE_EQUIPMENT, ComponentKind.PV_MODULE
    if component_type == "Inverter":
        return ComponentCategory.CORE_EQUIPMENT, ComponentKind.INVERTER
    if component_type == "BatteryStorage" and (
        "battery" in normalized_name or "storage" in normalized_name or "kwh" in normalized_name
    ):
        return ComponentCategory.CORE_EQUIPMENT, ComponentKind.BATTERY
    if component_type == "BatteryStorage":
        return ComponentCategory.ACCESSORY, ComponentKind.ACCESSORY
    if component_type == "Heatpump":
        return ComponentCategory.CORE_EQUIPMENT, ComponentKind.HEAT_PUMP
    if component_type == "Wallbox":
        return ComponentCategory.CORE_EQUIPMENT, ComponentKind.WALLBOX
    if component_type.startswith("AccessoryTo"):
        return ComponentCategory.ACCESSORY, ComponentKind.ACCESSORY
    if component_type == "InstallationFee":
        return ComponentCategory.FEE, ComponentKind.INSTALLATION_FEE
    if component_type == "ServiceFee":
        return ComponentCategory.SERVICE, ComponentKind.SERVICE_FEE
    if component_type == "ModuleFrameConstruction":
        return ComponentCategory.MOUNTING, ComponentKind.MOUNTING
    if "complete package" in normalized_name:
        return ComponentCategory.PACKAGE, ComponentKind.PACKAGE

    return ComponentCategory.OTHER, ComponentKind.OTHER


def parse_component_specs(
    component_name: str,
    component_type: str,
    kind: ComponentKind | None = None,
) -> tuple[ComponentSpec, set[str]]:
    if kind is None:
        _, kind = classify_component(component_type, component_name)

    spec = ComponentSpec()
    parsed_fields: set[str] = set()

    if kind == ComponentKind.PV_MODULE:
        value = _find_first_number_before_unit(component_name, "w")
        if value is not None:
            spec.module_watt_peak = value
            parsed_fields.add("module_watt_peak")
    elif kind == ComponentKind.INVERTER:
        value = _find_first_number_before_unit(component_name, "kw")
        if value is not None:
            spec.inverter_power_kw = value
            parsed_fields.add("inverter_power_kw")
    elif kind == ComponentKind.BATTERY:
        value = _find_first_number_before_unit(component_name, "kwh")
        if value is not None:
            spec.battery_capacity_kwh = value
            parsed_fields.add("battery_capacity_kwh")
    elif kind == ComponentKind.WALLBOX:
        value = _find_first_number_before_unit(component_name, "kw")
        if value is not None:
            spec.wallbox_charging_power_kw = value
            parsed_fields.add("wallbox_charging_power_kw")
    elif kind == ComponentKind.HEAT_PUMP:
        value = _find_first_number_before_unit(component_name, "kw")
        if value is not None:
            spec.heatpump_nominal_power_kw = value
            parsed_fields.add("heatpump_nominal_power_kw")
    elif kind == ComponentKind.PACKAGE:
        kwp = _find_first_number_before_unit(component_name, "kwp")
        kwh = _find_first_number_before_unit(component_name, "kwh")
        if kwp is not None:
            spec.module_watt_peak = kwp * 1000
            parsed_fields.add("module_watt_peak")
        if kwh is not None:
            spec.battery_capacity_kwh = kwh
            parsed_fields.add("battery_capacity_kwh")

    return spec, parsed_fields


def _merge_specs(
    parsed_spec: ComponentSpec,
    numeric_specs: dict[str, list[float]],
    kind: ComponentKind,
) -> ComponentSpec:
    spec = parsed_spec.model_copy()

    if spec.module_watt_peak is None:
        spec.module_watt_peak = _mode(numeric_specs["module_watt_peak"])
    if spec.inverter_power_kw is None:
        spec.inverter_power_kw = _csv_kw_value(numeric_specs["inverter_power_kw"])
    if spec.battery_capacity_kwh is None:
        spec.battery_capacity_kwh = _csv_kwh_value(numeric_specs["battery_capacity_kwh"])
    if spec.wallbox_charging_power_kw is None:
        spec.wallbox_charging_power_kw = _csv_kw_value(numeric_specs["wb_charging_speed_kw"])
    if spec.heatpump_nominal_power_kw is None:
        spec.heatpump_nominal_power_kw = _csv_kw_value(numeric_specs["heatpump_nominal_power_kw"])

    # Some exported rows shifted equipment specs into the wrong numeric column.
    if kind == ComponentKind.INVERTER and spec.inverter_power_kw is None:
        spec.inverter_power_kw = _csv_kw_value(numeric_specs["battery_capacity_kwh"])
    if kind == ComponentKind.BATTERY and spec.battery_capacity_kwh is None:
        spec.battery_capacity_kwh = _csv_kwh_value(numeric_specs["inverter_power_kw"])

    return spec


def _build_warnings(
    *,
    component_brand: str | None,
    category: ComponentCategory,
    kind: ComponentKind,
    parsed_spec: ComponentSpec,
    parsed_fields: set[str],
    numeric_specs: dict[str, list[float]],
    merged_spec: ComponentSpec,
) -> list[str]:
    warnings: list[str] = []
    if component_brand is None and category == ComponentCategory.CORE_EQUIPMENT:
        warnings.append("missing_brand")
    for field_name in sorted(parsed_fields):
        warnings.append(f"{field_name}_parsed_from_name")

    csv_field_by_spec = {
        "module_watt_peak": "module_watt_peak",
        "inverter_power_kw": "inverter_power_kw",
        "battery_capacity_kwh": "battery_capacity_kwh",
        "wallbox_charging_power_kw": "wb_charging_speed_kw",
        "heatpump_nominal_power_kw": "heatpump_nominal_power_kw",
    }
    for spec_field, csv_field in csv_field_by_spec.items():
        parsed_value = getattr(parsed_spec, spec_field)
        csv_value = _mode(numeric_specs[csv_field])
        if parsed_value is None or csv_value is None:
            continue
        comparable_csv_value = _normalize_exported_power_value(csv_value)
        if abs(parsed_value - comparable_csv_value) > 0.01:
            warnings.append(f"{spec_field}_csv_spec_disagrees")

    if kind == ComponentKind.PACKAGE:
        warnings.append("ambiguous_package")
    if category == ComponentCategory.OTHER and not any(
        value is not None for value in merged_spec.model_dump().values()
    ):
        warnings.append("unclassified_component")

    return warnings


def _find_first_number_before_unit(text: str, unit: str) -> float | None:
    match = re.search(rf"(?<!\w)(\d+(?:[.,]\d+)?)\s*{re.escape(unit)}\b", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _mode(values: list[float]) -> float | None:
    if not values:
        return None
    counts = Counter(values)
    return counts.most_common(1)[0][0]


def _csv_kw_value(values: list[float]) -> float | None:
    value = _mode(values)
    if value is None:
        return None
    return _normalize_exported_power_value(value)


def _csv_kwh_value(values: list[float]) -> float | None:
    value = _mode(values)
    if value is None:
        return None
    return _normalize_exported_power_value(value)


def _normalize_exported_power_value(value: float) -> float:
    return value / 1000 if value >= 1000 else value


def _component_id(component_type: str, component_brand: str | None, component_name: str) -> str:
    raw_id = "\x1f".join([component_type, component_brand or "", component_name])
    return hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
