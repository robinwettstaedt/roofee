export type CatalogComponentSpec = {
  module_watt_peak?: number | null;
  inverter_power_kw?: number | null;
  battery_capacity_kwh?: number | null;
  wallbox_charging_power_kw?: number | null;
  heatpump_nominal_power_kw?: number | null;
};

export type CatalogComponent = {
  id: string;
  component_type: string;
  component_name: string;
  component_brand: string | null;
  technology: string | null;
  category: string;
  kind: string;
  spec: CatalogComponentSpec;
};

export type CatalogResponse = {
  summary: { component_count: number };
  components: CatalogComponent[];
};

export type PanelDimensions = {
  lengthMeters: number;
  widthMeters: number;
  thicknessMeters: number;
};

export const DEFAULT_PANEL: PanelDimensions = {
  lengthMeters: 1.762,
  widthMeters: 1.134,
  thicknessMeters: 0.04,
};

export function fetchPvModules(): Promise<CatalogComponent[]> {
  return fetch("/api/catalog?kind=pv_module")
    .then((r) => (r.ok ? (r.json() as Promise<CatalogResponse>) : null))
    .then((data) => data?.components ?? [])
    .catch(() => []);
}

export function pickPrimaryPanel(modules: CatalogComponent[]): CatalogComponent | null {
  if (!modules.length) return null;
  return (
    modules
      .filter((m) => (m.spec.module_watt_peak ?? 0) > 0)
      .sort(
        (a, b) => (b.spec.module_watt_peak ?? 0) - (a.spec.module_watt_peak ?? 0),
      )[0] ?? modules[0]
  );
}

export function dimensionsFor(_module: CatalogComponent | null): PanelDimensions {
  return DEFAULT_PANEL;
}
