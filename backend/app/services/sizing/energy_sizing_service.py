from app.models.bom import (
    BomLineSource,
    BomSummary,
    CalculationAssumption,
    EquipmentRole,
    SizedEquipment,
    SystemRecommendationOption,
)
from app.models.catalog import CatalogComponent, ComponentKind
from app.models.roof import SolarLayoutOption
from app.services.bom.bom_service import BomService, get_bom_service
from app.services.catalog_service import CatalogService, get_catalog_service
from app.services.sizing.battery_sizing_service import (
    BatterySizingService,
    get_battery_sizing_service,
)
from app.services.sizing.heat_pump_sizing_service import (
    HeatPumpSizingService,
    get_heat_pump_sizing_service,
)


TARGET_DC_AC_RATIO = 1.15
MIN_DC_AC_RATIO = 1.0
MAX_DC_AC_RATIO = 1.35


class EnergySizingService:
    def __init__(
        self,
        *,
        catalog_service: CatalogService,
        bom_service: BomService,
        battery_sizing_service: BatterySizingService,
        heat_pump_sizing_service: HeatPumpSizingService,
    ) -> None:
        self.catalog_service = catalog_service
        self.bom_service = bom_service
        self.battery_sizing_service = battery_sizing_service
        self.heat_pump_sizing_service = heat_pump_sizing_service

    def build_system_options(
        self,
        *,
        layouts: list[SolarLayoutOption],
        project_context: dict[str, object],
    ) -> tuple[list[SystemRecommendationOption], list[str]]:
        if not layouts:
            return [], ["System sizing skipped because no solar layout options were available."]

        catalog = self.catalog_service.build_catalog()
        options: list[SystemRecommendationOption] = []
        pipeline_warnings: list[str] = []
        for layout in layouts:
            equipment, assumptions, warnings = self._size_equipment(
                layout=layout,
                project_context=project_context,
                catalog_components=catalog.components,
            )
            bom, bom_warnings = self.bom_service.build_bom(
                layout=layout,
                equipment=equipment,
                catalog_components=catalog.components,
            )
            warnings.extend(bom_warnings)
            summary = self._summary(
                layout=layout,
                equipment=equipment,
                line_item_count=len(bom),
                warnings=warnings,
            )
            options.append(
                SystemRecommendationOption(
                    id=f"system-{layout.id}",
                    layout_option_id=layout.id,
                    strategy=layout.strategy,
                    panel_count=layout.panel_count,
                    system_size_kwp=layout.system_size_kwp,
                    estimated_annual_production_kwh=layout.estimated_annual_production_kwh,
                    annual_demand_kwh=layout.annual_demand_kwh,
                    demand_coverage_ratio=layout.demand_coverage_ratio,
                    equipment=equipment,
                    bom=bom,
                    summary=summary,
                    assumptions=assumptions,
                    warnings=warnings,
                )
            )
        return options, pipeline_warnings

    def _size_equipment(
        self,
        *,
        layout: SolarLayoutOption,
        project_context: dict[str, object],
        catalog_components: list[CatalogComponent],
    ) -> tuple[list[SizedEquipment], list[CalculationAssumption], list[str]]:
        equipment = [self._pv_module_equipment(layout)]
        assumptions = [
            CalculationAssumption(
                field="pv_layout",
                value=layout.id,
                source="roof_geometry",
                reason="PV panel count and system size come from the physically feasible roof layout",
            )
        ]
        warnings = list(layout.warnings)

        inverter, inverter_assumptions, inverter_warnings = self._select_inverter(
            layout=layout,
            catalog_components=catalog_components,
        )
        assumptions.extend(inverter_assumptions)
        warnings.extend(inverter_warnings)
        if inverter is not None:
            equipment.append(inverter)

        battery, battery_assumptions, battery_warnings = self.battery_sizing_service.select_battery(
            layout=layout,
            context=project_context,
            catalog_components=catalog_components,
        )
        assumptions.extend(battery_assumptions)
        warnings.extend(battery_warnings)
        if battery is not None:
            equipment.append(battery)

        heat_pump, heat_pump_assumptions, heat_pump_warnings = (
            self.heat_pump_sizing_service.select_heat_pump(
                context=project_context,
                catalog_components=catalog_components,
            )
        )
        assumptions.extend(heat_pump_assumptions)
        warnings.extend(heat_pump_warnings)
        if heat_pump is not None:
            equipment.append(heat_pump)

        wallbox, wallbox_assumptions, wallbox_warnings = self._select_wallbox(
            context=project_context,
            catalog_components=catalog_components,
        )
        assumptions.extend(wallbox_assumptions)
        warnings.extend(wallbox_warnings)
        if wallbox is not None:
            equipment.append(wallbox)

        return equipment, assumptions, warnings

    def _pv_module_equipment(self, layout: SolarLayoutOption) -> SizedEquipment:
        module = layout.module
        return SizedEquipment(
            role=EquipmentRole.PV_MODULE,
            component_name=f"{module.label} ({module.model})",
            component_brand=module.brand,
            component_type="PanelPreset",
            kind=ComponentKind.PV_MODULE,
            quantity=layout.panel_count,
            selected_specs={
                "module_watt_peak": module.watt_peak,
                "length_m": module.length_m,
                "width_m": module.width_m,
                "thickness_m": module.thickness_m,
            },
            target_specs={"panel_count": float(layout.panel_count), "system_size_kwp": layout.system_size_kwp},
            selection_basis="dimensioned_panel_preset_used_by_solar_layout",
            source=BomLineSource.PANEL_PRESET,
        )

    def _select_inverter(
        self,
        *,
        layout: SolarLayoutOption,
        catalog_components: list[CatalogComponent],
    ) -> tuple[SizedEquipment | None, list[CalculationAssumption], list[str]]:
        if layout.system_size_kwp <= 0:
            return None, [], ["Inverter sizing skipped because PV system size is zero."]
        target_kw = round(layout.system_size_kwp / TARGET_DC_AC_RATIO, 2)
        assumptions = [
            CalculationAssumption(
                field="inverter_power_kw",
                value=target_kw,
                source="industry_assumption",
                reason=f"target DC/AC ratio is {TARGET_DC_AC_RATIO:g}",
            )
        ]
        candidates = [
            component
            for component in catalog_components
            if component.kind == ComponentKind.INVERTER
            and component.spec.inverter_power_kw is not None
        ]
        if not candidates:
            return None, assumptions, ["No catalog inverter with parseable AC power was available."]

        in_range = [
            component
            for component in candidates
            if MIN_DC_AC_RATIO
            <= layout.system_size_kwp / float(component.spec.inverter_power_kw or 1)
            <= MAX_DC_AC_RATIO
        ]
        pool = in_range or candidates
        selected = min(
            pool,
            key=lambda component: (
                abs(float(component.spec.inverter_power_kw or 0) - target_kw),
                -component.observed_count,
                component.component_name,
            ),
        )
        selected_kw = float(selected.spec.inverter_power_kw or 0)
        dc_ac_ratio = round(layout.system_size_kwp / selected_kw, 3) if selected_kw else 0
        warnings = []
        if not (MIN_DC_AC_RATIO <= dc_ac_ratio <= MAX_DC_AC_RATIO):
            warnings.append(
                f"Selected inverter creates DC/AC ratio {dc_ac_ratio:g}, outside V1 target range "
                f"{MIN_DC_AC_RATIO:g}-{MAX_DC_AC_RATIO:g}."
            )

        return (
            SizedEquipment(
                role=EquipmentRole.INVERTER,
                component_id=selected.id,
                component_name=selected.component_name,
                component_brand=selected.component_brand,
                component_type=selected.component_type,
                kind=selected.kind,
                selected_specs={"inverter_power_kw": selected_kw, "dc_ac_ratio": dc_ac_ratio},
                target_specs={"inverter_power_kw": target_kw, "dc_ac_ratio": TARGET_DC_AC_RATIO},
                selection_basis="catalog_inverter_closest_to_target_dc_ac_ratio",
                source=BomLineSource.CATALOG,
                warnings=list(selected.warnings),
            ),
            assumptions,
            warnings,
        )

    def _select_wallbox(
        self,
        *,
        context: dict[str, object],
        catalog_components: list[CatalogComponent],
    ) -> tuple[SizedEquipment | None, list[CalculationAssumption], list[str]]:
        assumptions: list[CalculationAssumption] = []
        preference = _string_value(context.get("ev_charger_preference"), "consider")
        if preference == "exclude":
            assumptions.append(
                CalculationAssumption(
                    field="wallbox",
                    value="excluded",
                    source="project_input",
                    reason="ev_charger_preference is exclude",
                )
            )
            return None, assumptions, []
        if _bool_value(context.get("has_wallbox")):
            assumptions.append(
                CalculationAssumption(
                    field="wallbox",
                    value="skipped_existing_wallbox",
                    source="project_input",
                    reason="customer already has a wallbox",
                )
            )
            return None, assumptions, []
        if preference == "consider" and not _bool_value(context.get("has_ev")):
            assumptions.append(
                CalculationAssumption(
                    field="wallbox",
                    value="deferred",
                    source="project_input",
                    reason="wallbox is optional and no EV usage was provided",
                )
            )
            return None, assumptions, []

        requested_kw = _float_value(context.get("wallbox_charge_speed_kw"))
        target_kw = 22.0 if requested_kw is not None and requested_kw >= 22 else 11.0
        assumptions.append(
            CalculationAssumption(
                field="wallbox_charging_power_kw",
                value=target_kw,
                source="project_input" if requested_kw else "industry_assumption",
                reason="uses explicit requested wallbox speed when provided, otherwise defaults to 11 kW",
            )
        )
        candidates = [
            component
            for component in catalog_components
            if component.kind == ComponentKind.WALLBOX
            and component.spec.wallbox_charging_power_kw is not None
        ]
        if not candidates:
            return None, assumptions, ["No catalog wallbox with parseable charging power was available."]
        selected = min(
            candidates,
            key=lambda component: (
                abs(float(component.spec.wallbox_charging_power_kw or 0) - target_kw),
                -component.observed_count,
                component.component_name,
            ),
        )
        selected_kw = float(selected.spec.wallbox_charging_power_kw or 0)
        return (
            SizedEquipment(
                role=EquipmentRole.WALLBOX,
                component_id=selected.id,
                component_name=selected.component_name,
                component_brand=selected.component_brand,
                component_type=selected.component_type,
                kind=selected.kind,
                selected_specs={"wallbox_charging_power_kw": selected_kw},
                target_specs={"wallbox_charging_power_kw": target_kw},
                selection_basis="nearest_catalog_wallbox_to_requested_or_default_power",
                source=BomLineSource.CATALOG,
                warnings=list(selected.warnings),
            ),
            assumptions,
            [],
        )

    def _summary(
        self,
        *,
        layout: SolarLayoutOption,
        equipment: list[SizedEquipment],
        line_item_count: int,
        warnings: list[str],
    ) -> BomSummary:
        return BomSummary(
            line_item_count=line_item_count,
            panel_count=layout.panel_count,
            system_size_kwp=layout.system_size_kwp,
            inverter_power_kw=_spec(equipment, EquipmentRole.INVERTER, "inverter_power_kw"),
            battery_capacity_kwh=_spec(equipment, EquipmentRole.BATTERY, "battery_capacity_kwh"),
            heatpump_nominal_power_kw=_spec(
                equipment,
                EquipmentRole.HEAT_PUMP,
                "heatpump_nominal_power_kw",
            ),
            wallbox_charging_power_kw=_spec(
                equipment,
                EquipmentRole.WALLBOX,
                "wallbox_charging_power_kw",
            ),
            warnings=warnings,
        )


def _spec(equipment: list[SizedEquipment], role: EquipmentRole, key: str) -> float | None:
    item = next((entry for entry in equipment if entry.role == role), None)
    return item.selected_specs.get(key) if item is not None else None


def _string_value(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _bool_value(value: object) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _float_value(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_energy_sizing_service() -> EnergySizingService:
    return EnergySizingService(
        catalog_service=get_catalog_service(),
        bom_service=get_bom_service(),
        battery_sizing_service=get_battery_sizing_service(),
        heat_pump_sizing_service=get_heat_pump_sizing_service(),
    )
