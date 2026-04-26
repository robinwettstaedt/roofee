"use client";
import { useState } from "react";
import type { BomLine, Design } from "@/types/api";
import type {
  EstimatedInput,
  MonthlySolarWeather,
} from "@/types/recommendation";
import type { SolarLayoutOption } from "@/types/roof";
import { eur, kwh, co2, num } from "@/lib/format";
import { useCountUp } from "@/lib/useCountUp";
import { Eyebrow } from "./primitives/Eyebrow";
import { Rule } from "./primitives/Rule";
import { SparkLine } from "./SparkLine";

const CATEGORY_LABEL: Record<BomLine["category"], string> = {
  module: "Modules",
  inverter: "Inverter",
  battery: "Battery",
  mounting: "Mounting",
  wallbox: "Wallbox",
  heatpump: "Heat pump",
  service: "Services",
};

const CATEGORY_ORDER: BomLine["category"][] = [
  "module",
  "inverter",
  "battery",
  "mounting",
  "wallbox",
  "heatpump",
  "service",
];

export function BomSidebar({
  design,
  variantLabel,
  notesCount,
  realAnnualGenerationKwh,
  monthlySolar,
  layoutOption,
  electricityPriceEurPerKwh = 0.32,
  estimatedInputs = [],
  warnings = [],
  onSendCustomer,
  onAddToInstallQueue,
  onSaveTemplate,
  onExportPdf,
}: {
  design: Design;
  variantLabel: string;
  notesCount: number;
  realAnnualGenerationKwh?: number | null;
  monthlySolar?: MonthlySolarWeather[] | null;
  layoutOption?: SolarLayoutOption | null;
  electricityPriceEurPerKwh?: number;
  estimatedInputs?: EstimatedInput[];
  warnings?: string[];
  onSendCustomer?: () => void;
  onAddToInstallQueue?: () => void;
  onSaveTemplate?: () => void;
  onExportPdf?: () => void;
}) {
  return (
    <aside className="flex h-full w-full flex-col overflow-hidden border-l border-ink/15 bg-paper">
      <div className="flex-1 overflow-y-auto">
        <Header design={design} variantLabel={variantLabel} />
        <BackendNotice
          estimatedInputs={estimatedInputs}
          warnings={warnings}
        />
        <Rule soft />
        <Metrics
          design={design}
          realAnnualGenerationKwh={realAnnualGenerationKwh}
          monthlySolar={monthlySolar}
          layoutOption={layoutOption}
          electricityPriceEurPerKwh={electricityPriceEurPerKwh}
        />
        <Rule soft />
        <SystemStrip design={design} layoutOption={layoutOption} />
        <Rule soft />
        <BomTable bom={design.bom} />
        <Rule soft />
        <CustomerOnePager
          design={design}
          notesCount={notesCount}
          onExportPdf={onExportPdf}
        />
      </div>

      <Rule />
      <FooterActions
        onSendCustomer={onSendCustomer}
        onAddToInstallQueue={onAddToInstallQueue}
        onSaveTemplate={onSaveTemplate}
      />
    </aside>
  );
}

function MockedChip() {
  return (
    <span
      className="ml-1.5 inline-flex items-center rounded-sm border border-ink/20 px-1 text-[9px] font-medium uppercase tracking-[0.18em] text-dust"
      title="Synthesized client-side until the backend ships sizing/BOM."
    >
      Mock
    </span>
  );
}

/** Mark figures derived from real backend numbers but using placeholder
 *  catalog list-prices, so the seller knows the math is real but pricing
 *  isn't yet wired to live wholesale costs. */
function CatalogChip() {
  return (
    <span
      className="ml-1.5 inline-flex items-center rounded-sm border border-ink/15 px-1 text-[9px] font-medium uppercase tracking-[0.18em] text-dust"
      title="Computed from real backend BOM × catalog list-prices."
    >
      List
    </span>
  );
}

function BackendNotice({
  estimatedInputs,
  warnings,
}: {
  estimatedInputs: EstimatedInput[];
  warnings: string[];
}) {
  if (estimatedInputs.length === 0 && warnings.length === 0) return null;
  return (
    <div className="px-6 pb-5 pt-2 fade">
      {estimatedInputs.length > 0 && (
        <ul className="space-y-1 text-[11px] text-dust">
          {estimatedInputs.map((e) => (
            <li key={e.field}>
              <span className="text-ink-soft">Estimated</span> {prettyField(e.field)} ={" "}
              <span className="font-mono num text-ink">{String(e.value)}</span>
            </li>
          ))}
        </ul>
      )}
      {warnings.length > 0 && (
        <ul
          className={`space-y-1 text-[11px] text-amber ${
            estimatedInputs.length > 0 ? "mt-2" : ""
          }`}
        >
          {warnings.map((w) => (
            <li key={w}>! {prettyWarning(w)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function prettyField(field: string): string {
  return field.replace(/_/g, " ");
}

function prettyWarning(code: string): string {
  if (code === "heating_existing_type_unknown") {
    return "Heating type unknown — heat-pump fit will fall back to estimates.";
  }
  return code.replace(/_/g, " ");
}

function Header({
  design,
  variantLabel,
}: {
  design: Design;
  variantLabel: string;
}) {
  return (
    <div key={variantLabel} className="px-6 pb-5 pt-6 fade">
      <div className="flex items-baseline justify-between">
        <Eyebrow>Package · {variantLabel}</Eyebrow>
        <Eyebrow>{design.packageId}</Eyebrow>
      </div>
      <h2 className="mt-3 flex items-baseline gap-2 leading-none text-ink">
        <span className="num text-[36px] font-semibold tracking-tight">{design.pv.kwp}</span>
        <span className="text-[16px] font-medium text-dust">kWp</span>
      </h2>
      <span className="draw-underline mt-3 block h-[2px] w-16 origin-left bg-signal" />
      <p className="mt-3 max-w-[340px] text-[12px] leading-snug text-dust">
        {design.reasoning.pv}
      </p>
    </div>
  );
}

function Metrics({
  design,
  realAnnualGenerationKwh,
  monthlySolar,
  layoutOption,
  electricityPriceEurPerKwh = 0.32,
}: {
  design: Design;
  realAnnualGenerationKwh?: number | null;
  monthlySolar?: MonthlySolarWeather[] | null;
  layoutOption?: SolarLayoutOption | null;
  electricityPriceEurPerKwh?: number;
}) {
  const generationTarget =
    realAnnualGenerationKwh ?? design.metrics.annualGenerationKwh;
  // Recompute payback + CO2 from the live generation target so they track the
  // active variant + the real backend annual production figure (not the synth
  // mock baked into `design.metrics`). System cost still comes from the synth
  // BOM line items (real catalog list-prices, no backend cost service yet).
  const yearlyValueEur = Math.max(
    generationTarget * electricityPriceEurPerKwh,
    1,
  );
  const liveCost = design.metrics.systemCostEur;
  const livePaybackYears =
    Math.round((liveCost / yearlyValueEur) * 10) / 10;
  const liveCo2KgPerYear = Math.round(generationTarget * 0.42);

  const cost = useCountUp(liveCost);
  const gen = useCountUp(generationTarget);
  const payback = useCountUp(livePaybackYears);
  const co2yr = useCountUp(liveCo2KgPerYear);

  const generationIsReal = realAnnualGenerationKwh != null;
  // Backend gives a real demand-coverage ratio (annual production /
  // annual demand). Capped at 100% for display since coverage above 1
  // means surplus generation, not "more than fully covered".
  const coveragePct =
    layoutOption?.demand_coverage_ratio != null
      ? Math.round(Math.min(1, layoutOption.demand_coverage_ratio) * 100)
      : null;

  return (
    <div className="grid grid-cols-2 gap-px bg-ink/10">
      <Metric
        eyebrow={
          <>
            Yearly generation
            {!generationIsReal && <MockedChip />}
          </>
        }
        value={kwh(gen)}
        accent
        sub={
          <SparkLine annualKwh={generationTarget} monthly={monthlySolar} />
        }
      />
      <Metric
        eyebrow={
          <>
            System cost
            <CatalogChip />
          </>
        }
        value={eur(Math.round(cost))}
        sub={
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
            incl. install · catalog list price
          </span>
        }
      />
      <Metric
        eyebrow={<>Payback</>}
        value={
          <>
            <span className="num">{payback.toFixed(1)}</span>{" "}
            <span className="text-[14px] font-normal text-dust">years</span>
          </>
        }
        sub={
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
            @ {electricityPriceEurPerKwh.toFixed(2)} €/kWh
          </span>
        }
      />
      <Metric
        eyebrow={<>CO₂ saved / yr</>}
        value={co2(co2yr)}
        sub={
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
            {coveragePct != null
              ? `${coveragePct}% demand covered`
              : `self-cons. ${design.metrics.selfConsumptionPct}%`}
          </span>
        }
      />
    </div>
  );
}

function Metric({
  eyebrow,
  value,
  sub,
  accent,
}: {
  eyebrow: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col justify-between gap-3 bg-paper px-5 py-5">
      <Eyebrow>{eyebrow}</Eyebrow>
      <div
        className={`text-[22px] font-medium leading-none tracking-tight ${
          accent ? "text-signal" : "text-ink"
        }`}
      >
        {value}
      </div>
      {sub && <div className="-mb-1">{sub}</div>}
    </div>
  );
}

function SystemStrip({
  design,
  layoutOption,
}: {
  design: Design;
  layoutOption?: SolarLayoutOption | null;
}) {
  // Prefer the real backend module spec when available — gives us the actual
  // brand, model name, and watt-peak for this layout instead of a hardcoded
  // string. Falls back to the synth `463W modules` line during the loading
  // window before geometry resolves.
  const modulePvLine = layoutOption?.module
    ? `${design.pv.panelCount} × ${Math.round(layoutOption.module.watt_peak)}W ${layoutOption.module.brand} ${layoutOption.module.model}`
    : `${design.pv.panelCount} × 463W modules`;
  const items: { label: string; value: string; reasoning?: string }[] = [
    {
      label: "PV",
      value: modulePvLine,
      reasoning: design.reasoning.pv,
    },
    {
      label: "Battery",
      value: design.battery
        ? `${design.battery.kwh} kWh · ${design.battery.brand}`
        : "—",
      reasoning: design.reasoning.battery,
    },
    {
      label: "Heat pump",
      value: design.heatpump
        ? `${design.heatpump.kw} kW · ${design.heatpump.brand}`
        : "—",
      reasoning: design.reasoning.heatpump,
    },
    {
      label: "Wallbox",
      value: design.wallbox
        ? `${design.wallbox.kw} kW · ${design.wallbox.brand}`
        : "—",
    },
  ];

  return (
    <div className="px-6 py-5">
      <Eyebrow>Composition</Eyebrow>
      <ul className="mt-3 divide-y divide-ink/10">
        {items.map((it) => (
          <CompositionRow key={it.label} {...it} />
        ))}
      </ul>
    </div>
  );
}

function CompositionRow({
  label,
  value,
  reasoning,
}: {
  label: string;
  value: string;
  reasoning?: string;
}) {
  const [open, setOpen] = useState(false);
  const empty = value === "—";
  return (
    <li>
      <button
        type="button"
        onClick={() => reasoning && !empty && setOpen((o) => !o)}
        disabled={empty || !reasoning}
        className="flex w-full items-baseline justify-between gap-4 py-2.5 text-left"
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
          {label}
        </span>
        <span
          className={`text-[12.5px] ${empty ? "text-dust-soft" : "text-ink-soft"}`}
        >
          {value}
        </span>
      </button>
      {open && reasoning && (
        <p className="pb-3 pr-2 text-[11.5px] leading-snug text-dust fade">
          {reasoning}
        </p>
      )}
    </li>
  );
}

function BomTable({ bom }: { bom: BomLine[] }) {
  const total = bom.reduce((s, l) => s + l.quantity * l.unitPriceEur, 0);
  const groups = CATEGORY_ORDER.map((cat) => ({
    cat,
    lines: bom.filter((l) => l.category === cat),
  })).filter((g) => g.lines.length > 0);

  return (
    <div className="px-6 py-5">
      <div className="flex items-baseline justify-between">
        <Eyebrow>Bill of materials</Eyebrow>
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
          {bom.length} lines
        </span>
      </div>

      <div className="mt-4 space-y-4">
        {groups.map(({ cat, lines }) => (
          <div key={cat}>
            <div className="flex items-baseline justify-between border-b border-ink/15 pb-1.5">
              <span className="text-[13px] font-medium text-ink">
                {CATEGORY_LABEL[cat]}
              </span>
              <span className="font-mono num text-[11px] text-dust">
                {num(lines.reduce((s, l) => s + l.quantity, 0))} units
              </span>
            </div>
            <ul className="mt-1.5 divide-y divide-ink/8">
              {lines.map((l, i) => (
                <li
                  key={`${cat}-${i}`}
                  className="grid grid-cols-[auto_1fr_auto] items-baseline gap-3 py-1.5"
                >
                  <span className="font-mono num text-[11px] text-dust">
                    {String(l.quantity).padStart(2, "0")}×
                  </span>
                  <span className="text-[12.5px] text-ink-soft">
                    {l.name}
                    {l.brand && (
                      <span className="ml-1 text-dust">· {l.brand}</span>
                    )}
                  </span>
                  <span className="font-mono num text-[12px] text-ink">
                    {eur(l.quantity * l.unitPriceEur)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-baseline justify-between border-t-2 border-ink pt-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink">
          Total
        </span>
        <span className="num text-[20px] font-semibold tracking-tight text-signal">
          {eur(total)}
        </span>
      </div>
    </div>
  );
}

function CustomerOnePager({
  design,
  notesCount,
  onExportPdf,
}: {
  design: Design;
  notesCount: number;
  onExportPdf?: () => void;
}) {
  return (
    <div className="px-6 py-5">
      <Eyebrow>Customer one-pager</Eyebrow>
      <div className="mt-3 flex items-stretch gap-4">
        <div className="relative aspect-[3/4] w-20 shrink-0 overflow-hidden border border-ink/15 bg-paper-deep/50">
          <div className="absolute inset-0 p-1.5">
            <div className="h-1.5 w-full rounded-full bg-ink/30" />
            <div className="mt-1 h-1 w-2/3 rounded-full bg-ink/20" />
            <div className="mt-2 h-9 w-full rounded-sm bg-ink/15" />
            <div className="mt-1.5 h-1 w-full rounded-full bg-ink/15" />
            <div className="mt-1 h-1 w-3/4 rounded-full bg-ink/15" />
            <div className="absolute bottom-1.5 left-1.5 h-2 w-6 rounded-sm bg-signal" />
          </div>
        </div>
        <div className="flex flex-col justify-between text-[12px] text-dust">
          <p className="leading-snug">
            One-page customer summary with the {design.pv.kwp} kWp render,
            generation chart, and signed pricing.
            {notesCount > 0 && (
              <span className="text-ink-soft"> Excludes {notesCount} install note{notesCount === 1 ? "" : "s"}.</span>
            )}
          </p>
          <button
            type="button"
            onClick={onExportPdf}
            className="self-start font-mono text-[11px] uppercase tracking-[0.2em] text-ink underline-offset-4 hover:underline hover:decoration-signal"
          >
            Generate PDF →
          </button>
        </div>
      </div>
    </div>
  );
}

function FooterActions({
  onSendCustomer,
  onAddToInstallQueue,
  onSaveTemplate,
}: {
  onSendCustomer?: () => void;
  onAddToInstallQueue?: () => void;
  onSaveTemplate?: () => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-px bg-ink/15">
      <button
        type="button"
        onClick={onSaveTemplate}
        className="bg-paper px-3 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dust transition hover:bg-paper-deep hover:text-ink"
      >
        Save template
      </button>
      <button
        type="button"
        onClick={onAddToInstallQueue}
        className="bg-paper px-3 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-ink transition hover:bg-paper-deep"
      >
        + Install queue
      </button>
      <button
        type="button"
        onClick={onSendCustomer}
        className="bg-signal px-3 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-paper transition hover:bg-ink"
      >
        Send to customer →
      </button>
    </div>
  );
}
