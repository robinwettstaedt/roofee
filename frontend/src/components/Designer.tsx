"use client";
import { useMemo, useState } from "react";
import type { Design, DesignResponse } from "@/types/api";
import type { PanelDimensions } from "@/lib/catalog";
import { buildVariants, variantFor, type VariantId } from "@/lib/variants";
import { eur } from "@/lib/format";
import { BomSidebar } from "./BomSidebar";
import { CanvasOverlays, type Note } from "./CanvasOverlays";
import { PlacementControls } from "./PlacementControls";
import { PresentToggle } from "./PresentToggle";
import { RefineChat } from "./RefineChat";
import { Scene } from "./Scene";
import { SessionBar } from "./SessionBar";
import { SparkLine } from "./SparkLine";
import { VariantTabs } from "./VariantTabs";
import { Eyebrow } from "./primitives/Eyebrow";
import type { PlacementOverride } from "./RoofPlacedPanels";

export function Designer({
  response,
  baseDesign,
  panelDims,
  modelUrl,
  placementOverride,
  onPlacementChange,
  onPlacementReset,
  refineLoading,
  onRefine,
  onBack,
}: {
  response: DesignResponse;
  baseDesign: Design;
  panelDims: PanelDimensions;
  modelUrl: string;
  placementOverride: PlacementOverride;
  onPlacementChange: (p: PlacementOverride) => void;
  onPlacementReset: () => void;
  refineLoading: boolean;
  onRefine: (intent: string) => void;
  onBack: () => void;
}) {
  const variants = useMemo(() => buildVariants(baseDesign), [baseDesign]);
  const [variantId, setVariantId] = useState<VariantId>("standard");
  const variant = variantFor(variants, variantId);
  const design = variant.design;

  const [mode, setMode] = useState<"edit" | "present">("edit");
  const [hour, setHour] = useState(13);
  const [lens, setLens] = useState<"panels" | "obstructions" | "irradiance" | "measure">(
    "panels",
  );
  const [notes, setNotes] = useState<Note[]>([]);
  const [tuning, setTuning] = useState(false);

  const monthlySavings = (design.metrics.annualGenerationKwh * 0.32) / 12;
  const presenting = mode === "present";

  return (
    <div className="flex h-screen w-screen flex-col">
      <SessionBar
        showBack
        onBack={onBack}
        breadcrumb={
          <span className="font-mono num text-[12px]">
            {response.location.latLng.lat.toFixed(4)}°,{" "}
            {response.location.latLng.lng.toFixed(4)}° ·{" "}
            <span className="text-ink-soft">Hauptstraße 1, 10827 Berlin</span>
          </span>
        }
        rightSlot={
          <>
            {!presenting && (
              <div className="hidden md:block">
                <VariantTabs
                  variants={variants}
                  activeId={variantId}
                  onSelect={setVariantId}
                />
              </div>
            )}
            {!presenting && (
              <button
                type="button"
                onClick={() => setTuning((t) => !t)}
                aria-pressed={tuning}
                className={`border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em] transition ${
                  tuning
                    ? "border-ink bg-ink text-paper"
                    : "border-ink/25 text-ink-soft hover:border-ink hover:text-ink"
                }`}
              >
                Tune
              </button>
            )}
            <PresentToggle
              mode={mode}
              onToggle={() => setMode((m) => (m === "edit" ? "present" : "edit"))}
            />
          </>
        }
      />

      <main className="flex flex-1 overflow-hidden">
        {/* Canvas region */}
        <section className="relative flex-1">
          <div className="absolute inset-0 bg-gradient-to-br from-paper via-paper-deep to-paper">
            <Scene
              panelCount={design.pv.panelCount}
              panel={panelDims}
              modelUrl={modelUrl}
              placementOverride={placementOverride}
            />
          </div>

          {!presenting && (
            <CanvasOverlays
              hour={hour}
              onHour={setHour}
              lens={lens}
              onLens={setLens}
              notes={notes}
              onAddNote={(n) => setNotes((arr) => [...arr, n])}
              onRemoveNote={(id) =>
                setNotes((arr) => arr.filter((n) => n.id !== id))
              }
              freeRoofM2={response.roof.segments[0]?.areaMeters2 ?? 56}
              lat={response.location.latLng.lat}
              lng={response.location.latLng.lng}
            />
          )}

          {!presenting && tuning && (
            <PlacementControls
              value={placementOverride}
              onChange={onPlacementChange}
              onReset={onPlacementReset}
            />
          )}

          {!presenting && (
            <RefineChat onRefine={onRefine} loading={refineLoading} />
          )}

          {presenting && (
            <PresentingOverlay
              annualKwh={design.metrics.annualGenerationKwh}
              monthlySavingsEur={monthlySavings}
              kwp={design.pv.kwp}
            />
          )}
        </section>

        {/* BOM rail */}
        {!presenting && (
          <section className="w-[440px] shrink-0">
            <BomSidebar
              design={design}
              variantLabel={variant.label}
              notesCount={notes.length}
              onSendCustomer={() => alert("Sending offer to customer (stub)")}
              onAddToInstallQueue={() =>
                alert(`Added to install queue with ${notes.length} notes`)
              }
              onSaveTemplate={() => alert("Profile saved as template (stub)")}
              onExportPdf={() => alert("PDF export coming next")}
            />
          </section>
        )}
      </main>
    </div>
  );
}

function PresentingOverlay({
  annualKwh,
  monthlySavingsEur,
  kwp,
}: {
  annualKwh: number;
  monthlySavingsEur: number;
  kwp: number;
}) {
  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col justify-end p-12">
      <div className="pointer-events-auto max-w-[640px]">
        <Eyebrow>For your home</Eyebrow>
        <h2 className="mt-4 text-[52px] font-medium leading-[1.05] tracking-tight text-ink">
          A <span className="text-signal">{kwp} kWp</span> system
        </h2>
        <div className="mt-6 grid grid-cols-2 gap-x-12 gap-y-2 border-t border-ink/30 pt-5">
          <div>
            <Eyebrow>Yearly generation</Eyebrow>
            <p className="mt-1 text-[28px] font-medium num text-ink">
              {Math.round(annualKwh).toLocaleString("de-DE")} kWh
            </p>
            <SparkLine annualKwh={annualKwh} width={220} height={36} />
          </div>
          <div>
            <Eyebrow>Estimated monthly savings</Eyebrow>
            <p className="mt-1 text-[28px] font-medium num text-signal">
              {eur(Math.round(monthlySavingsEur))}
            </p>
            <p className="mt-1 text-[12px] text-dust">
              vs. current grid spend, year one
            </p>
          </div>
        </div>

        <button
          type="button"
          className="mt-8 inline-flex items-center gap-3 bg-ink px-7 py-4 text-[13px] font-medium text-paper transition hover:bg-signal"
        >
          Sign the offer
          <span>→</span>
        </button>
      </div>
    </div>
  );
}
