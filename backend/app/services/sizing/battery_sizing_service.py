from app.models.bom import BomLineSource, CalculationAssumption, EquipmentRole, SizedEquipment
from app.models.catalog import CatalogComponent, ComponentKind
from app.models.roof import SolarLayoutOption


BATTERY_MULTIPLIERS_BY_GOAL = {
    "lowest_upfront_cost": 0.5,
    "balanced": 0.8,
    "maximum_self_consumption": 1.0,
    "maximum_roof_usage": 0.7,
}


class BatterySizingService:
    def select_battery(
        self,
        *,
        layout: SolarLayoutOption,
        context: dict[str, object],
        catalog_components: list[CatalogComponent],
    ) -> tuple[SizedEquipment | None, list[CalculationAssumption], list[str]]:
        assumptions: list[CalculationAssumption] = []
        warnings: list[str] = []
        preference = _string_value(context.get("battery_preference"), "consider")
        if preference == "exclude":
            assumptions.append(
                CalculationAssumption(
                    field="battery",
                    value="excluded",
                    source="project_input",
                    reason="battery_preference is exclude",
                )
            )
            return None, assumptions, warnings
        if _bool_value(context.get("has_storage")):
            assumptions.append(
                CalculationAssumption(
                    field="battery",
                    value="skipped_existing_storage",
                    source="project_input",
                    reason="customer already has battery storage",
                )
            )
            return None, assumptions, warnings
        if layout.system_size_kwp <= 0:
            return None, assumptions, ["Battery sizing skipped because PV system size is zero."]

        recommendation_goal = _string_value(context.get("recommendation_goal"), "balanced")
        if preference == "consider" and recommendation_goal == "lowest_upfront_cost":
            assumptions.append(
                CalculationAssumption(
                    field="battery",
                    value="deferred",
                    source="project_input",
                    reason="lowest_upfront_cost goal keeps optional battery out of V1 BOM",
                )
            )
            return None, assumptions, warnings

        multiplier = BATTERY_MULTIPLIERS_BY_GOAL.get(recommendation_goal, 0.8)
        target_kwh = layout.system_size_kwp * multiplier
        annual_demand_kwh = _float_value(context.get("annual_electricity_demand_kwh"))
        if annual_demand_kwh is not None:
            target_kwh = min(target_kwh, annual_demand_kwh / 365.0 * 1.5)
        target_kwh = round(max(target_kwh, 0.0), 2)
        assumptions.append(
            CalculationAssumption(
                field="battery_capacity_kwh",
                value=target_kwh,
                source="industry_assumption",
                reason=(
                    f"targeted {multiplier:g} kWh per kWp for {recommendation_goal}, "
                    "capped by daily demand when available"
                ),
            )
        )

        candidates = [
            component
            for component in catalog_components
            if component.kind == ComponentKind.BATTERY
            and component.spec.battery_capacity_kwh is not None
        ]
        if not candidates:
            return None, assumptions, ["No catalog battery with parseable capacity was available."]

        selected = min(
            candidates,
            key=lambda component: (
                abs(float(component.spec.battery_capacity_kwh or 0) - target_kwh),
                -component.observed_count,
                component.component_name,
            ),
        )
        selected_kwh = float(selected.spec.battery_capacity_kwh or 0)
        if target_kwh > 0 and abs(selected_kwh - target_kwh) / target_kwh > 0.35:
            warnings.append(
                f"Selected battery capacity {selected_kwh:g} kWh differs materially from target {target_kwh:g} kWh."
            )

        return (
            SizedEquipment(
                role=EquipmentRole.BATTERY,
                component_id=selected.id,
                component_name=selected.component_name,
                component_brand=selected.component_brand,
                component_type=selected.component_type,
                kind=selected.kind,
                selected_specs={"battery_capacity_kwh": selected_kwh},
                target_specs={"battery_capacity_kwh": target_kwh},
                selection_basis="nearest_catalog_capacity_to_battery_target",
                source=BomLineSource.CATALOG,
                warnings=list(selected.warnings),
            ),
            assumptions,
            warnings,
        )


def _string_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _bool_value(value: object) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _float_value(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_battery_sizing_service() -> BatterySizingService:
    return BatterySizingService()
