from app.models.bom import BomLineSource, CalculationAssumption, EquipmentRole, SizedEquipment
from app.models.catalog import CatalogComponent, ComponentKind


FULL_LOAD_HOURS_HEAT_PUMP = 2000


class HeatPumpSizingService:
    def select_heat_pump(
        self,
        *,
        context: dict[str, object],
        catalog_components: list[CatalogComponent],
    ) -> tuple[SizedEquipment | None, list[CalculationAssumption], list[str]]:
        assumptions: list[CalculationAssumption] = []
        warnings: list[str] = []
        preference = _string_value(context.get("heat_pump_preference"), "consider")
        existing_type = _string_value(context.get("heating_existing_type"), "unknown").casefold()
        if preference == "exclude":
            assumptions.append(
                CalculationAssumption(
                    field="heat_pump",
                    value="excluded",
                    source="project_input",
                    reason="heat_pump_preference is exclude",
                )
            )
            return None, assumptions, warnings
        if any(token in existing_type for token in ("heat pump", "heatpump", "wärmepumpe", "waermepumpe")):
            assumptions.append(
                CalculationAssumption(
                    field="heat_pump",
                    value="skipped_existing_heat_pump",
                    source="project_input",
                    reason="customer already has a heat pump",
                )
            )
            return None, assumptions, warnings

        target_kw, target_assumption, target_warnings = self._target_heat_pump_kw(context)
        assumptions.append(target_assumption)
        warnings.extend(target_warnings)
        if target_kw <= 0:
            warnings.append("Heat pump sizing skipped because target output was zero.")
            return None, assumptions, warnings

        candidates = [
            component
            for component in catalog_components
            if component.kind == ComponentKind.HEAT_PUMP
            and component.spec.heatpump_nominal_power_kw is not None
        ]
        if not candidates:
            return None, assumptions, ["No catalog heat pump with parseable nominal power was available."]

        selected = min(
            candidates,
            key=lambda component: (
                _undersize_penalty(float(component.spec.heatpump_nominal_power_kw or 0), target_kw),
                abs(float(component.spec.heatpump_nominal_power_kw or 0) - target_kw),
                -component.observed_count,
                component.component_name,
            ),
        )
        selected_kw = float(selected.spec.heatpump_nominal_power_kw or 0)
        if selected_kw < target_kw * 0.9:
            warnings.append(
                f"Selected heat pump {selected_kw:g} kW is below the estimated target {target_kw:g} kW."
            )

        return (
            SizedEquipment(
                role=EquipmentRole.HEAT_PUMP,
                component_id=selected.id,
                component_name=selected.component_name,
                component_brand=selected.component_brand,
                component_type=selected.component_type,
                kind=selected.kind,
                selected_specs={"heatpump_nominal_power_kw": selected_kw},
                target_specs={"heatpump_nominal_power_kw": target_kw},
                selection_basis="nearest_catalog_nominal_power_to_heat_load_estimate",
                source=BomLineSource.CATALOG,
                warnings=list(selected.warnings),
            ),
            assumptions,
            warnings,
        )

    def _target_heat_pump_kw(
        self,
        context: dict[str, object],
    ) -> tuple[float, CalculationAssumption, list[str]]:
        known_heating_demand_kwh = _float_value(context.get("heating_existing_heating_demand_kwh"))
        if known_heating_demand_kwh is not None and known_heating_demand_kwh > 0:
            target_kw = round(known_heating_demand_kwh / FULL_LOAD_HOURS_HEAT_PUMP, 2)
            return (
                target_kw,
                CalculationAssumption(
                    field="heatpump_nominal_power_kw",
                    value=target_kw,
                    source="project_input",
                    reason="estimated from known annual heating demand using 2000 full-load hours",
                ),
                [],
            )

        house_size_sqm = _float_value(context.get("house_size_sqm")) or 0
        watts_per_sqm = _fallback_watts_per_sqm(context)
        target_kw = round(house_size_sqm * watts_per_sqm / 1000.0, 2)
        return (
            target_kw,
            CalculationAssumption(
                field="heatpump_nominal_power_kw",
                value=target_kw,
                source="industry_assumption",
                reason=f"fallback estimate uses {watts_per_sqm:g} W/m2 because heating demand is missing",
            ),
            [
                "Heat pump size is a V1 estimate, not a DIN EN 12831 heat-load calculation."
            ],
        )


def _fallback_watts_per_sqm(context: dict[str, object]) -> float:
    renovation_standard = _string_value(context.get("renovation_standard"), "").casefold()
    if any(token in renovation_standard for token in ("new", "modern", "kfw", "passive", "good")):
        return 45
    if any(token in renovation_standard for token in ("partial", "medium")):
        return 70
    if any(token in renovation_standard for token in ("old", "poor", "unrenovated")):
        return 90

    built_year = _int_value(context.get("house_built_year"))
    if built_year is None:
        return 75
    if built_year >= 2010:
        return 45
    if built_year >= 1995:
        return 55
    if built_year >= 1978:
        return 75
    return 90


def _undersize_penalty(selected_kw: float, target_kw: float) -> int:
    return 1 if selected_kw < target_kw * 0.9 else 0


def _string_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _float_value(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_heat_pump_sizing_service() -> HeatPumpSizingService:
    return HeatPumpSizingService()
