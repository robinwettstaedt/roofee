import hashlib

from app.models.bom import BomLineItem, BomLineSource, EquipmentRole, SizedEquipment
from app.models.catalog import CatalogComponent, ComponentCategory, ComponentKind
from app.models.roof import SolarLayoutOption


class BomService:
    def build_bom(
        self,
        *,
        layout: SolarLayoutOption,
        equipment: list[SizedEquipment],
        catalog_components: list[CatalogComponent],
    ) -> tuple[list[BomLineItem], list[str]]:
        warnings: list[str] = []
        lines: list[BomLineItem] = []

        if layout.panel_count > 0:
            lines.append(self._panel_line(layout))

        for item in equipment:
            if item.role == EquipmentRole.PV_MODULE:
                continue
            lines.append(self._equipment_line(item))

        lines.extend(
            self._solar_support_lines(
                panel_count=layout.panel_count,
                catalog_components=catalog_components,
            )
        )
        equipment_roles = {item.role for item in equipment}
        lines.extend(
            self._equipment_support_lines(
                equipment_roles=equipment_roles,
                catalog_components=catalog_components,
            )
        )
        if layout.panel_count > 0 and not any(line.role == EquipmentRole.MOUNTING for line in lines):
            warnings.append("No catalog mounting component was available for the PV layout.")

        return _dedupe_lines(lines), warnings

    def _panel_line(self, layout: SolarLayoutOption) -> BomLineItem:
        module = layout.module
        return BomLineItem(
            id=_line_id("panel_preset", module.id),
            role=EquipmentRole.PV_MODULE,
            component_name=f"{module.label} ({module.model})",
            component_brand=module.brand,
            component_type="PanelPreset",
            category=ComponentCategory.CORE_EQUIPMENT,
            kind=ComponentKind.PV_MODULE,
            quantity=layout.panel_count,
            quantity_units="Item",
            source=BomLineSource.PANEL_PRESET,
            selected_specs={
                "module_watt_peak": module.watt_peak,
                "length_m": module.length_m,
                "width_m": module.width_m,
                "thickness_m": module.thickness_m,
            },
            notes=[
                "Panel preset is used because CSV module rows do not include reliable physical dimensions."
            ],
        )

    def _equipment_line(self, equipment: SizedEquipment) -> BomLineItem:
        return BomLineItem(
            id=_line_id(equipment.source.value, equipment.role.value, equipment.component_id or equipment.component_name),
            role=equipment.role,
            component_id=equipment.component_id,
            component_name=equipment.component_name,
            component_brand=equipment.component_brand,
            component_type=equipment.component_type,
            category=ComponentCategory.CORE_EQUIPMENT,
            kind=equipment.kind,
            quantity=equipment.quantity,
            quantity_units=equipment.quantity_units,
            source=equipment.source,
            selected_specs=equipment.selected_specs,
            notes=[equipment.selection_basis],
            warnings=equipment.warnings,
        )

    def _solar_support_lines(
        self,
        *,
        panel_count: int,
        catalog_components: list[CatalogComponent],
    ) -> list[BomLineItem]:
        if panel_count <= 0:
            return []

        lines: list[BomLineItem] = []
        substructure = _pick_component(
            catalog_components,
            kind=ComponentKind.MOUNTING,
            include=("substructure",),
            exclude=("8.8", "15kwp", "6-8", "discount"),
        )
        if substructure is not None:
            lines.append(_catalog_line(substructure, EquipmentRole.MOUNTING, panel_count, "Item"))

        scaffolding = _pick_component(
            catalog_components,
            kind=ComponentKind.MOUNTING,
            include=("scaffolding",),
        )
        if scaffolding is not None:
            lines.append(_catalog_line(scaffolding, EquipmentRole.MOUNTING, 1, "Item"))

        optimizer = _pick_component(
            catalog_components,
            kind=ComponentKind.ACCESSORY,
            include=("optimizer",),
        )
        if optimizer is not None:
            lines.append(_catalog_line(optimizer, EquipmentRole.ACCESSORY, panel_count, "Item"))

        dc_install = _pick_component(
            catalog_components,
            kind=ComponentKind.ACCESSORY,
            include=("dc install",),
        )
        if dc_install is not None:
            lines.append(_catalog_line(dc_install, EquipmentRole.ACCESSORY, panel_count, "Item"))

        for include in (
            ("planning", "consulting"),
            ("grid registration",),
            ("travel", "logistics"),
            ("install inverter",),
        ):
            component = _pick_component(
                catalog_components,
                include=include,
                exclude=("all-inclusive", "optional", "extension"),
            )
            if component is not None:
                role = (
                    EquipmentRole.SERVICE
                    if component.kind == ComponentKind.SERVICE_FEE
                    else EquipmentRole.INSTALLATION
                )
                lines.append(_catalog_line(component, role, 1, "Item"))

        return lines

    def _equipment_support_lines(
        self,
        *,
        equipment_roles: set[EquipmentRole],
        catalog_components: list[CatalogComponent],
    ) -> list[BomLineItem]:
        lines: list[BomLineItem] = []
        role_specs = {
            EquipmentRole.BATTERY: [
                (("install battery",), EquipmentRole.INSTALLATION),
                (("smart guard",), EquipmentRole.ACCESSORY),
            ],
            EquipmentRole.WALLBOX: [
                (("install wallbox",), EquipmentRole.INSTALLATION),
                (("charging cable",), EquipmentRole.ACCESSORY),
            ],
            EquipmentRole.HEAT_PUMP: [
                (("heat pump installation",), EquipmentRole.INSTALLATION),
                (("hydraulic station",), EquipmentRole.ACCESSORY),
                (("heating controller",), EquipmentRole.ACCESSORY),
            ],
        }
        for role, specs in role_specs.items():
            if role not in equipment_roles:
                continue
            for include, line_role in specs:
                component = _pick_component(catalog_components, include=include)
                if component is not None:
                    lines.append(_catalog_line(component, line_role, 1, "Item"))
        return lines


def _pick_component(
    components: list[CatalogComponent],
    *,
    kind: ComponentKind | None = None,
    include: tuple[str, ...],
    exclude: tuple[str, ...] = (),
) -> CatalogComponent | None:
    matches = []
    for component in components:
        normalized_name = component.component_name.casefold()
        if kind is not None and component.kind != kind:
            continue
        if not all(token in normalized_name for token in include):
            continue
        if any(token in normalized_name for token in exclude):
            continue
        if component.kind == ComponentKind.PACKAGE:
            continue
        matches.append(component)
    if not matches:
        return None
    return max(matches, key=lambda component: (component.observed_count, component.component_name))


def _catalog_line(
    component: CatalogComponent,
    role: EquipmentRole,
    quantity: float,
    quantity_units: str,
) -> BomLineItem:
    return BomLineItem(
        id=_line_id("catalog", component.id, role.value),
        role=role,
        component_id=component.id,
        component_name=component.component_name,
        component_brand=component.component_brand,
        component_type=component.component_type,
        category=component.category,
        kind=component.kind,
        quantity=quantity,
        quantity_units=quantity_units,
        source=BomLineSource.CATALOG,
        selected_specs={
            key: value
            for key, value in component.spec.model_dump().items()
            if value is not None
        },
        warnings=list(component.warnings),
    )


def _dedupe_lines(lines: list[BomLineItem]) -> list[BomLineItem]:
    deduped: dict[tuple[str | None, str, str], BomLineItem] = {}
    for line in lines:
        key = (line.component_id, line.component_name, line.role.value)
        if key in deduped:
            deduped[key].quantity += line.quantity
        else:
            deduped[key] = line
    return list(deduped.values())


def _line_id(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def get_bom_service() -> BomService:
    return BomService()
