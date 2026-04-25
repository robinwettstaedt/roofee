"use client";
import type { Profile } from "@/types/api";

const HEATING: { value: Profile["heating"]; label: string }[] = [
  { value: "gas", label: "Gas" },
  { value: "oil", label: "Oil" },
  { value: "district", label: "District" },
  { value: "electric", label: "Electric" },
  { value: "heatpump", label: "Heat pump" },
  { value: "none", label: "None" },
];

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
}) {
  return (
    <div className="flex flex-col gap-7">
      <Field label="Monthly electricity bill">
        <div className="relative max-w-[260px]">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[15px] text-dust">
            €
          </span>
          <input
            type="number"
            min={10}
            value={monthlyBillEur}
            onChange={(e) => onMonthlyBillEur(Number(e.target.value))}
            className="w-full rounded-md border border-ink/20 bg-paper py-2.5 pl-9 pr-16 text-[15px] num text-ink outline-none transition focus:border-signal"
          />
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[13px] text-dust">
            per month
          </span>
        </div>
      </Field>

      <Field label="People living in the home">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => onInhabitants(Math.max(1, inhabitants - 1))}
            className="grid h-9 w-9 place-items-center rounded-full border border-ink/20 text-[18px] text-ink-soft transition hover:border-ink hover:bg-ink hover:text-paper"
            aria-label="Fewer occupants"
          >
            −
          </button>
          <span className="w-8 text-center text-[18px] font-medium num text-ink">
            {inhabitants}
          </span>
          <button
            type="button"
            onClick={() => onInhabitants(Math.min(12, inhabitants + 1))}
            className="grid h-9 w-9 place-items-center rounded-full border border-ink/20 text-[18px] text-ink-soft transition hover:border-ink hover:bg-ink hover:text-paper"
            aria-label="More occupants"
          >
            +
          </button>
        </div>
      </Field>

      <Field label="Heating">
        <div className="flex flex-wrap gap-2">
          {HEATING.map((h) => {
            const active = heating === h.value;
            return (
              <button
                key={h.value}
                type="button"
                aria-pressed={active}
                onClick={() => onHeating(h.value)}
                className={`rounded-full border px-4 py-1.5 text-[13px] transition ${
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
      </Field>

      <Field label="Do you own an electric vehicle?">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex gap-2">
            <button
              type="button"
              aria-pressed={!hasEv}
              onClick={() => onHasEv(false)}
              className={`rounded-full border px-5 py-1.5 text-[13px] transition ${
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
              className={`rounded-full border px-5 py-1.5 text-[13px] transition ${
                hasEv
                  ? "border-ink bg-ink text-paper"
                  : "border-ink/20 text-ink-soft hover:border-ink hover:text-ink"
              }`}
            >
              Yes
            </button>
          </div>

          {hasEv && (
            <div className="rise flex min-w-[280px] flex-1 items-center gap-3 text-[13px]">
              <span className="text-dust">Driven per year:</span>
              <input
                type="range"
                min={2000}
                max={40000}
                step={1000}
                value={evKmPerYear}
                onChange={(e) => onEvKmPerYear(Number(e.target.value))}
                className="flex-1"
              />
              <span className="num text-ink">
                {evKmPerYear.toLocaleString("de-DE")} km
              </span>
            </div>
          )}
        </div>
      </Field>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-3 text-[13px] font-medium text-ink">{label}</p>
      {children}
    </div>
  );
}
