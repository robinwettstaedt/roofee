// Variant source of truth:
// - When `/api/roof/geometry` returns `solar_layout_options[]`, the variant
//   tabs are driven directly from those backend strategies — real `kwp`,
//   `panel_count`, and `estimated_annual_production_kwh`. The synth design
//   is only used as a BOM scaffold (line items, prices) until the backend
//   ships a BOM endpoint.
// - When geometry hasn't resolved yet (or registration failed), we fall
//   back to ±25% scaling around the synth design so the switcher still
//   has something to compare during the 10–30s registration window.

import type { BomLine, Design } from "@/types/api";
import type { SolarLayoutOption } from "@/types/roof";

export type VariantId = string;

export type Variant = {
  id: VariantId;
  label: string;
  scale: number; // multiplier on synth panel count, informational only
  design: Design;
  /** Real backend layout option when present; null for synth fallback variants. */
  layoutOption?: SolarLayoutOption | null;
};

const VARIANT_SCALES: { id: VariantId; label: string; scale: number }[] = [
  { id: "modest", label: "Modest", scale: 0.75 },
  { id: "standard", label: "Standard", scale: 1.0 },
  { id: "maximum", label: "Maximum", scale: 1.25 },
];

export function buildVariants(base: Design): Variant[] {
  return VARIANT_SCALES.map(({ id, label, scale }) => ({
    id,
    label,
    scale,
    design: scaleDesign(base, scale),
    layoutOption: null,
  }));
}

const STRATEGY_LABELS: Record<string, string> = {
  cost_optimized: "Cost-optimized",
  balanced: "Balanced",
  max_coverage: "Max coverage",
  maximum_coverage: "Max coverage",
  self_consumption: "Self-consumption",
  maximum_self_consumption: "Max self-consumption",
  full_roof: "Max roof",
  modest: "Modest",
  standard: "Standard",
  maximum: "Maximum",
};

function humanizeStrategy(strategy: string): string {
  if (STRATEGY_LABELS[strategy]) return STRATEGY_LABELS[strategy];
  return strategy
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Build variants directly from backend `solar_layout_options[]`. Each variant
 * keeps the synth design as a BOM/cost scaffold but overrides:
 *   - `pv.kwp` and `pv.panelCount` with real backend values
 *   - `metrics.annualGenerationKwh` with backend's `estimated_annual_production_kwh`
 *   - BOM line item quantities scaled to the real panel count
 *   - `systemCostEur`, `paybackYears`, `co2SavedKgPerYear` recomputed from the above
 *
 * `electricityPriceEurPerKwh` lets us derive payback from real bill input
 * instead of the 0.32 €/kWh hardcoded in `scaleDesign`.
 */
export function buildVariantsFromLayoutOptions(
  base: Design,
  options: SolarLayoutOption[],
  electricityPriceEurPerKwh: number = 0.32,
): Variant[] {
  const baseCount = Math.max(1, base.pv.panelCount);
  return options.map((option) => {
    const scale = option.panel_count / baseCount;
    const annualKwh =
      option.estimated_annual_production_kwh ??
      Math.round(base.metrics.annualGenerationKwh * scale);
    const yearlyValueEur = Math.max(annualKwh * electricityPriceEurPerKwh, 1);

    const bom: BomLine[] = base.bom.map((l) => {
      if (l.category === "module" || l.category === "mounting") {
        return {
          ...l,
          quantity: Math.max(1, Math.round(l.quantity * scale)),
        };
      }
      return l;
    });
    const systemCostEur = Math.round(
      bom.reduce((s, l) => s + l.quantity * l.unitPriceEur, 0),
    );
    const paybackYears = Math.round((systemCostEur / yearlyValueEur) * 10) / 10;
    const co2SavedKgPerYear = Math.round(annualKwh * 0.42);

    const design: Design = {
      ...base,
      pv: {
        kwp: Math.round(option.system_size_kwp * 10) / 10,
        panelCount: option.panel_count,
        positions: base.pv.positions.slice(0, option.panel_count),
      },
      bom,
      metrics: {
        ...base.metrics,
        annualGenerationKwh: annualKwh,
        systemCostEur,
        paybackYears,
        co2SavedKgPerYear,
      },
    };

    return {
      id: option.id,
      label: humanizeStrategy(option.strategy),
      scale,
      design,
      layoutOption: option,
    };
  });
}

/** Pick the recommended option's id when it exists; otherwise the first
 *  variant; otherwise the synth `"standard"` fallback id. */
export function defaultVariantId(
  variants: Variant[],
  recommendedId?: string | null,
): VariantId {
  if (recommendedId && variants.some((v) => v.id === recommendedId)) {
    return recommendedId;
  }
  return variants[0]?.id ?? "standard";
}

function scaleDesign(base: Design, scale: number): Design {
  if (scale === 1.0) return base;

  const panelCount = Math.max(4, Math.round(base.pv.panelCount * scale));
  const kwp = Math.round((base.pv.kwp * scale) * 10) / 10;
  const positions = base.pv.positions.slice(0, panelCount);

  const bom: BomLine[] = base.bom.map((l) => {
    if (l.category === "module" || l.category === "mounting") {
      return { ...l, quantity: Math.max(1, Math.round(l.quantity * scale)) };
    }
    return l;
  });

  const systemCostEur = Math.round(
    bom.reduce((s, l) => s + l.quantity * l.unitPriceEur, 0),
  );
  const annualGenerationKwh = Math.round(base.metrics.annualGenerationKwh * scale);
  const yearlyValueEur = Math.max(annualGenerationKwh * 0.32, 1);
  const paybackYears = Math.round((systemCostEur / yearlyValueEur) * 10) / 10;
  const co2SavedKgPerYear = Math.round(annualGenerationKwh * 0.42);

  return {
    ...base,
    pv: { kwp, panelCount, positions },
    bom,
    metrics: {
      ...base.metrics,
      annualGenerationKwh,
      systemCostEur,
      paybackYears,
      co2SavedKgPerYear,
    },
  };
}

export function variantFor(variants: Variant[], id: VariantId): Variant {
  return variants.find((v) => v.id === id) ?? variants[1];
}
