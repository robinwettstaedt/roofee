"use client";
import { useMemo, useState } from "react";
import type { Design, DesignResponse } from "@/types/api";
import type { PanelDimensions } from "@/lib/catalog";
import { buildVariants, variantFor, type VariantId } from "@/lib/variants";
import { eur } from "@/lib/format";
import { annualGenerationFromPvgis } from "@/lib/realGeneration";
import type { RecommendationValidationResponse } from "@/types/recommendation";
import type {
  RoofGeometryAnalysisResponse,
  RoofObstruction,
  SelectedRoof,
} from "@/types/roof";
import { BomSidebar } from "./BomSidebar";
import { CanvasModeToggle, type CanvasMode } from "./CanvasModeToggle";
import { CanvasOverlays, type Note } from "./CanvasOverlays";
import { PlacementControls } from "./PlacementControls";
import { PresentToggle } from "./PresentToggle";
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
  recommendation,
  selectedRoof,
  obstructions,
  roofGeometry,
  onBack,
}: {
  response: DesignResponse;
  baseDesign: Design;
  panelDims: PanelDimensions;
  modelUrl: string;
  placementOverride: PlacementOverride;
  onPlacementChange: (p: PlacementOverride) => void;
  onPlacementReset: () => void;
  recommendation: RecommendationValidationResponse | null;
  selectedRoof: SelectedRoof | null;
  obstructions: RoofObstruction[];
  roofGeometry: RoofGeometryAnalysisResponse | null;
  onBack: () => void;
}) {
  const variants = useMemo(() => buildVariants(baseDesign), [baseDesign]);
  const [variantId, setVariantId] = useState<VariantId>("standard");
  const variant = variantFor(variants, variantId);
  const design = variant.design;

  // Real PVGIS-derived annual generation for the active variant; null until
  // /api/recommendations completes, in which case we keep showing the mock.
  const realAnnualGenerationKwh = annualGenerationFromPvgis(
    design.pv.kwp,
    recommendation?.solar_weather,
  );

  const realLatLng = recommendation?.house_data?.location ?? null;
  const realAddress = recommendation?.input.address ?? null;
  const realRoofAreaM2 =
    recommendation?.house_data?.solar_building.roof_segments.reduce(
      (sum, seg) => sum + (seg.area_meters2 ?? 0),
      0,
    ) ?? null;
  const backendLayout = useMemo(() => {
    const options = roofGeometry?.solar_layout_options ?? [];
    return (
      options.find(
        (option) => option.id === roofGeometry?.recommended_layout_option_id,
      ) ??
      options.find((option) => option.panel_placements.length > 0) ??
      null
    );
  }, [roofGeometry]);

  const [mode, setMode] = useState<"edit" | "present">("edit");
  const [canvasMode, setCanvasMode] = useState<CanvasMode>("real");
  const [hour, setHour] = useState(13);
  const [lens, setLens] = useState<"panels" | "obstructions" | "irradiance" | "measure">(
    "panels",
  );
  const [notes, setNotes] = useState<Note[]>([]);
  const [tuning, setTuning] = useState(false);

  const annualKwhForUi =
    realAnnualGenerationKwh ?? design.metrics.annualGenerationKwh;
  const monthlySavings = (annualKwhForUi * 0.32) / 12;
  const presenting = mode === "present";

  return (
    <div className="flex h-screen w-screen flex-col">
      <SessionBar
        showBack
        onBack={onBack}
        breadcrumb={
          <span className="font-mono num text-[12px]">
            {(realLatLng?.latitude ?? response.location.latLng.lat).toFixed(4)}°,{" "}
            {(realLatLng?.longitude ?? response.location.latLng.lng).toFixed(4)}° ·{" "}
            <span className="text-ink-soft">
              {realAddress ?? "Hauptstraße 1, 10827 Berlin"}
            </span>
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
              <CanvasModeToggle
                mode={canvasMode}
                onChange={setCanvasMode}
                disabled={
                  !roofGeometry ||
                  (roofGeometry.roof_planes?.length ?? 0) === 0
                }
              />
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
              placementOverride={tuning ? placementOverride : undefined}
              backendPlacements={backendLayout?.panel_placements ?? []}
              backendModule={backendLayout?.module ?? null}
              allowPlacementFallback={!roofGeometry}
              canvasMode={canvasMode}
              roofGeometry={roofGeometry}
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
              freeRoofM2={
                (realRoofAreaM2 && realRoofAreaM2 > 0
                  ? realRoofAreaM2
                  : response.roof.segments[0]?.areaMeters2) ?? 56
              }
              lat={realLatLng?.latitude ?? response.location.latLng.lat}
              lng={realLatLng?.longitude ?? response.location.latLng.lng}
              selectedRoofAreaPixels={selectedRoof?.area_pixels ?? null}
              obstructionCount={
                roofGeometry?.mapped_obstructions.length ?? obstructions.length
              }
            />
          )}

          {!presenting && tuning && (
            <PlacementControls
              value={placementOverride}
              onChange={onPlacementChange}
              onReset={onPlacementReset}
            />
          )}

          {presenting && (
            <PresentingOverlay
              annualKwh={annualKwhForUi}
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
              realAnnualGenerationKwh={realAnnualGenerationKwh}
              estimatedInputs={recommendation?.estimated_inputs ?? []}
              warnings={recommendation?.warnings ?? []}
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
