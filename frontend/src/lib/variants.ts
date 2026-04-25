// derived: backend should return packages[]; for now we synthesize three
// linearly-scaled variants from a single design so the package switcher
// has something to compare. Each variant scales pv kWp / panel count and
// linearly recomputes dependent metrics + BOM line quantities.

import type { BomLine, Design } from "@/types/api";

export type VariantId = "modest" | "standard" | "maximum";

export type Variant = {
  id: VariantId;
  label: string;
  scale: number; // multiplier on panel count
  design: Design;
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
  }));
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
