"use client";
import { useState } from "react";
import type { Profile } from "@/types/api";

const HEATING: { value: Profile["heating"]; label: string }[] = [
  { value: "gas", label: "Gas" },
  { value: "oil", label: "Oil" },
  { value: "district", label: "District" },
  { value: "electric", label: "Electric" },
  { value: "heatpump", label: "Heat pump" },
  { value: "none", label: "None" },
  { value: "unknown", label: "Not sure" },
];

const HOUSE_SIZES: { sqm: number; label: string }[] = [
  { sqm: 75, label: "< 90 m²" },
  { sqm: 110, label: "90–130 m²" },
  { sqm: 155, label: "130–180 m²" },
  { sqm: 200, label: "> 180 m²" },
];

// Rough German residential price per kWh — used only for the live "≈ X kWh
// per year" echo so the user can see we're already using their bill input.
// Backend has the canonical sizing logic; this is just user-facing reassurance.
const EUR_PER_KWH = 0.32;

const STEPS = [
  "bill",
  "heating",
  "ev",
  "people",
  "size",
  "existing",
] as const;
type StepId = (typeof STEPS)[number];

export function SecondaryInputs({
  monthlyBillEur,
  onMonthlyBillEur,
  inhabitants,
  onInhabitants,
  heating,
  onHeating,
  hasEv,
  onHasEv,
  evKmPerYear,
  onEvKmPerYear,
  houseSizeSqm,
  onHouseSizeSqm,
  hasSolar,
  onHasSolar,
  hasStorage,
  onHasStorage,
  hasWallbox,
  onHasWallbox,
  loading,
  onComplete,
  onBackToAddress,
}: {
  monthlyBillEur: number;
  onMonthlyBillEur: (v: number) => void;
  inhabitants: number;
  onInhabitants: (v: number) => void;
  heating: Profile["heating"];
  onHeating: (v: Profile["heating"]) => void;
  hasEv: boolean;
  onHasEv: (v: boolean) => void;
  evKmPerYear: number;
  onEvKmPerYear: (v: number) => void;
  houseSizeSqm: number;
  onHouseSizeSqm: (v: number) => void;
  hasSolar: boolean;
  onHasSolar: (v: boolean) => void;
  hasStorage: boolean;
  onHasStorage: (v: boolean) => void;
  hasWallbox: boolean;
  onHasWallbox: (v: boolean) => void;
  loading: boolean;
  onComplete: () => void;
  onBackToAddress: () => void;
}) {
  const [step, setStep] = useState<StepId>("bill");
  const stepIndex = STEPS.indexOf(step);
  const isLast = stepIndex === STEPS.length - 1;

  function next() {
    if (isLast) onComplete();
    else setStep(STEPS[stepIndex + 1]);
  }

  function prev() {
    if (stepIndex === 0) onBackToAddress();
    else setStep(STEPS[stepIndex - 1]);
  }

  // Bill is the only step that genuinely needs validation; everything else has
  // a sensible default selected so Continue is always allowed.
  const canContinue = step === "bill" ? monthlyBillEur > 0 : true;

  return (
    <div className="flex flex-col">
      <ProgressBar current={stepIndex + 1} total={STEPS.length} />

      <div key={step} className="rise mt-9 min-h-[280px]">
        {step === "bill" && (
          <BillStep
            value={monthlyBillEur}
            onChange={onMonthlyBillEur}
            onEnter={next}
          />
        )}
        {step === "heating" && (
          <HeatingStep value={heating} onChange={onHeating} />
        )}
        {step === "ev" && (
          <EvStep
            hasEv={hasEv}
            onHasEv={onHasEv}
            evKmPerYear={evKmPerYear}
            onEvKmPerYear={onEvKmPerYear}
          />
        )}
        {step === "people" && (
          <PeopleStep value={inhabitants} onChange={onInhabitants} />
        )}
        {step === "size" && (
          <SizeStep value={houseSizeSqm} onChange={onHouseSizeSqm} />
        )}
        {step === "existing" && (
          <ExistingStep
            hasSolar={hasSolar}
            onHasSolar={onHasSolar}
            hasStorage={hasStorage}
            onHasStorage={onHasStorage}
            hasWallbox={hasWallbox}
            onHasWallbox={onHasWallbox}
          />
        )}
      </div>

      <div className="mt-10 flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={prev}
          disabled={loading}
          className="text-[13px] text-dust transition hover:text-ink disabled:opacity-40"
        >
          {stepIndex === 0 ? "← Address" : "← Back"}
        </button>

        <div className="flex items-center gap-5">
          <span className="text-[12px] num text-dust">
            {stepIndex + 1} / {STEPS.length}
          </span>
          <button
            type="button"
            onClick={next}
            disabled={!canContinue || loading}
            className="inline-flex items-center gap-2 rounded-full bg-signal px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
          >
            {isLast ? (
              loading ? (
                <>
                  Designing…
                  <span
                    className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper"
                    aria-hidden
                  />
                </>
              ) : (
                <>
                  Design my system
                  <span aria-hidden>→</span>
                </>
              )
            ) : (
              <>
                Continue
                <span aria-hidden>→</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────── individual steps

function BillStep({
  value,
  onChange,
  onEnter,
}: {
  value: number;
  onChange: (v: number) => void;
  onEnter: () => void;
}) {
  const annualKwh = Math.round((value * 12) / EUR_PER_KWH / 50) * 50;
  return (
    <Step
      title="What's the monthly electricity bill?"
      hint="Anchors the system size — we work backwards to your annual usage."
    >
      <div className="relative max-w-[300px]">
        <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[18px] text-dust">
          €
        </span>
        <input
          type="number"
          min={10}
          autoFocus
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && value > 0) onEnter();
          }}
          className="w-full rounded-md border border-ink/20 bg-paper py-3 pl-9 pr-20 text-[18px] num text-ink outline-none transition focus:border-signal"
        />
        <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[13px] text-dust">
          per month
        </span>
      </div>
      {value > 0 && (
        <p className="mt-3 text-[13px] text-dust num">
          ≈ {annualKwh.toLocaleString("de-DE")} kWh per year
          <span className="ml-2 text-ink/30">
            (at ~{EUR_PER_KWH.toFixed(2).replace(".", ",")} €/kWh)
          </span>
        </p>
      )}
    </Step>
  );
}

function HeatingStep({
  value,
  onChange,
}: {
  value: Profile["heating"];
  onChange: (v: Profile["heating"]) => void;
}) {
  return (
    <Step
      title="How is the home heated?"
      hint="Helps us decide whether a heat pump is worth recommending alongside the panels."
    >
      <div className="flex flex-wrap gap-2">
        {HEATING.map((h) => {
          const active = value === h.value;
          return (
            <button
              key={h.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(h.value)}
              className={`rounded-full border px-5 py-2 text-[14px] transition ${
                active
                  ? "border-ink bg-ink text-paper"
                  : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
              }`}
            >
              {h.label}
            </button>
          );
        })}
      </div>
    </Step>
  );
}

function EvStep({
  hasEv,
  onHasEv,
  evKmPerYear,
  onEvKmPerYear,
}: {
  hasEv: boolean;
  onHasEv: (v: boolean) => void;
  evKmPerYear: number;
  onEvKmPerYear: (v: number) => void;
}) {
  return (
    <Step
      title="Is there an electric vehicle?"
      hint="If yes, we add the car's annual draw on top of household usage."
    >
      <div className="flex gap-2">
        <button
          type="button"
          aria-pressed={!hasEv}
          onClick={() => onHasEv(false)}
          className={`rounded-full border px-7 py-2 text-[14px] transition ${
            !hasEv
              ? "border-ink bg-ink text-paper"
              : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
          }`}
        >
          No
        </button>
        <button
          type="button"
          aria-pressed={hasEv}
          onClick={() => onHasEv(true)}
          className={`rounded-full border px-7 py-2 text-[14px] transition ${
            hasEv
              ? "border-ink bg-ink text-paper"
              : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
          }`}
        >
          Yes
        </button>
      </div>

      {hasEv && (
        <div className="rise mt-6 max-w-[440px]">
          <p className="mb-3 text-[12px] text-dust">Driven per year</p>
          <div className="flex items-center gap-4 text-[13px]">
            <input
              type="range"
              min={2000}
              max={40000}
              step={1000}
              value={evKmPerYear}
              onChange={(e) => onEvKmPerYear(Number(e.target.value))}
              className="flex-1"
            />
            <span className="w-[88px] text-right num text-ink">
              {evKmPerYear.toLocaleString("de-DE")} km
            </span>
          </div>
        </div>
      )}
    </Step>
  );
}

function PeopleStep({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Step
      title="How many people live in the home?"
      hint="More people means a higher baseline draw."
    >
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, value - 1))}
          disabled={value <= 1}
          className="grid h-11 w-11 place-items-center rounded-full border border-ink/20 text-[20px] text-ink-soft transition hover:border-ink hover:bg-ink hover:text-paper disabled:cursor-not-allowed disabled:opacity-30"
          aria-label="Fewer occupants"
        >
          −
        </button>
        <span className="w-12 text-center text-[28px] font-medium num text-ink">
          {value}
        </span>
        <button
          type="button"
          onClick={() => onChange(Math.min(12, value + 1))}
          disabled={value >= 12}
          className="grid h-11 w-11 place-items-center rounded-full border border-ink/20 text-[20px] text-ink-soft transition hover:border-ink hover:bg-ink hover:text-paper disabled:cursor-not-allowed disabled:opacity-30"
          aria-label="More occupants"
        >
          +
        </button>
      </div>
    </Step>
  );
}

function SizeStep({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Step
      title="Roughly how big is the home?"
      hint="Sanity-checks the bill against typical floor-area usage."
    >
      <div className="flex flex-wrap gap-2">
        {HOUSE_SIZES.map((s) => {
          const active = value === s.sqm;
          return (
            <button
              key={s.sqm}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(s.sqm)}
              className={`rounded-full border px-5 py-2 text-[14px] num transition ${
                active
                  ? "border-ink bg-ink text-paper"
                  : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
              }`}
            >
              {s.label}
            </button>
          );
        })}
      </div>
    </Step>
  );
}

function ExistingStep({
  hasSolar,
  onHasSolar,
  hasStorage,
  onHasStorage,
  hasWallbox,
  onHasWallbox,
}: {
  hasSolar: boolean;
  onHasSolar: (v: boolean) => void;
  hasStorage: boolean;
  onHasStorage: (v: boolean) => void;
  hasWallbox: boolean;
  onHasWallbox: (v: boolean) => void;
}) {
  return (
    <Step
      title="Anything already installed?"
      hint="We exclude these from the bill of materials. Skip if none."
    >
      <div className="flex flex-wrap gap-2">
        <SystemPill
          label="Solar panels"
          active={hasSolar}
          onToggle={() => onHasSolar(!hasSolar)}
        />
        <SystemPill
          label="Battery"
          active={hasStorage}
          onToggle={() => onHasStorage(!hasStorage)}
        />
        <SystemPill
          label="EV charger"
          active={hasWallbox}
          onToggle={() => onHasWallbox(!hasWallbox)}
        />
      </div>
    </Step>
  );
}

// ─────────────────────────────────────────────────────────── shared building blocks

function Step({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h2 className="text-[26px] font-medium leading-tight tracking-tight text-ink">
        {title}
      </h2>
      <p className="mt-2 max-w-[520px] text-[14px] text-dust">{hint}</p>
      <div className="mt-7">{children}</div>
    </div>
  );
}

function ProgressBar({ current, total }: { current: number; total: number }) {
  return (
    <div
      className="flex gap-1.5"
      role="progressbar"
      aria-valuenow={current}
      aria-valuemin={1}
      aria-valuemax={total}
    >
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
            i < current ? "bg-signal" : "bg-ink/12"
          }`}
        />
      ))}
    </div>
  );
}

function SystemPill({
  label,
  active,
  onToggle,
}: {
  label: string;
  active: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      className={`group inline-flex items-center gap-2 rounded-full border px-5 py-2 text-[14px] transition ${
        active
          ? "border-signal bg-signal/10 text-ink"
          : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
      }`}
    >
      <span
        aria-hidden
        className={`grid h-4 w-4 place-items-center rounded-sm border text-[11px] leading-none transition ${
          active
            ? "border-signal bg-signal text-paper"
            : "border-ink/30 bg-paper text-transparent"
        }`}
      >
        ✓
      </span>
      {label}
    </button>
  );
}
