"use client";
import { useCallback, useEffect, useState } from "react";
import { AddressIntake } from "./AddressIntake";
import { Designer } from "./Designer";
import { ProcessingNarrative } from "./ProcessingNarrative";
import type { PlacementOverride } from "./RoofPlacedPanels";
import {
  dimensionsFor,
  fetchPvModules,
  pickPrimaryPanel,
  type CatalogComponent,
  type PanelDimensions,
} from "@/lib/catalog";
import type {
  DesignResponse,
  Profile,
  RefineResponse,
} from "@/types/api";

const HOUSE_GLB = "/house.glb";

// Default placement on the central peaked-roof house. Tunable live via the
// PlacementControls overlay inside the Designer (Tune toggle); persists in
// localStorage and is copy-pastable back into this constant.
const DEFAULT_PLACEMENT: PlacementOverride = {
  center: [-1, 9, 5],
  tiltDeg: 14,
  azimuthDeg: 80,
  yawDeg: -10,
  cols: 2,
};

const STORAGE_KEY = "roofee.placement.v1";

function loadStoredPlacement(): PlacementOverride {
  if (typeof window === "undefined") return DEFAULT_PLACEMENT;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PLACEMENT;
    const parsed = JSON.parse(raw) as PlacementOverride;
    if (
      Array.isArray(parsed?.center) &&
      parsed.center.length === 3 &&
      typeof parsed.tiltDeg === "number" &&
      typeof parsed.azimuthDeg === "number"
    ) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return DEFAULT_PLACEMENT;
}

type View = "intake" | "thinking" | "designer";

export default function DesignerApp() {
  const [view, setView] = useState<View>("intake");
  const [pendingResponse, setPendingResponse] = useState<DesignResponse | null>(
    null,
  );
  const [response, setResponse] = useState<DesignResponse | null>(null);
  const [refineLoading, setRefineLoading] = useState(false);
  const [catalogPanel, setCatalogPanel] = useState<CatalogComponent | null>(null);
  const [placement, setPlacement] = useState<PlacementOverride>(DEFAULT_PLACEMENT);

  useEffect(() => {
    setPlacement(loadStoredPlacement());
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(placement));
  }, [placement]);

  useEffect(() => {
    let cancelled = false;
    fetchPvModules().then((modules) => {
      if (cancelled) return;
      const picked = pickPrimaryPanel(modules);
      setCatalogPanel(picked);
      if (picked) {
        console.info(
          `[catalog] primary panel: ${picked.component_brand ?? "?"} ${picked.component_name} (${picked.spec.module_watt_peak ?? "?"}W)`,
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleGenerate = useCallback(async (profile: Profile) => {
    setView("thinking");
    setPendingResponse(null);
    try {
      const res = await fetch("/api/design", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = (await res.json()) as DesignResponse;
      setPendingResponse(data);
    } catch (err) {
      console.error(err);
      setView("intake");
    }
  }, []);

  const handleNarrativeDone = useCallback(() => {
    if (pendingResponse) {
      setResponse(pendingResponse);
      setView("designer");
    } else {
      setView("intake");
    }
  }, [pendingResponse]);

  const handleRefine = useCallback(
    async (intent: string) => {
      if (!response) return;
      setRefineLoading(true);
      try {
        const res = await fetch("/api/refine", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ currentDesign: response.design, intent }),
        });
        const data = (await res.json()) as RefineResponse;
        setResponse({ ...response, design: data.design });
      } catch (err) {
        console.error(err);
      } finally {
        setRefineLoading(false);
      }
    },
    [response],
  );

  const handleBack = useCallback(() => {
    setView("intake");
  }, []);

  const panelDims: PanelDimensions = dimensionsFor(catalogPanel);

  if (view === "designer" && response) {
    return (
      <>
        <Designer
          response={response}
          baseDesign={response.design}
          panelDims={panelDims}
          modelUrl={HOUSE_GLB}
          placementOverride={placement}
          onPlacementChange={setPlacement}
          onPlacementReset={() => setPlacement(DEFAULT_PLACEMENT)}
          refineLoading={refineLoading}
          onRefine={handleRefine}
          onBack={handleBack}
        />
      </>
    );
  }

  return (
    <>
      <AddressIntake
        onSubmit={handleGenerate}
        disabled={view === "thinking"}
      />
      {view === "thinking" && (
        <ProcessingNarrative onDone={handleNarrativeDone} />
      )}
    </>
  );
}
