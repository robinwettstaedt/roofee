"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AddressIntake } from "./AddressIntake";
import { Designer } from "./Designer";
import { ProcessingNarrative } from "./ProcessingNarrative";
import { RoofPicker } from "./RoofPicker";
import type { PlacementOverride } from "./RoofPlacedPanels";
import {
  dimensionsFor,
  fetchPvModules,
  pickPrimaryPanel,
  type CatalogComponent,
  type PanelDimensions,
} from "@/lib/catalog";
import { buildRecommendationRequest } from "@/lib/recommendationProfile";
import type { DesignResponse, Profile } from "@/types/api";
import type {
  HouseModelMetadata,
  RecommendationValidationResponse,
} from "@/types/recommendation";
import type {
  RoofObstruction,
  RoofObstructionAnalysis,
  RoofSelectionResponse,
  SelectedRoof,
} from "@/types/roof";

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

type View = "intake" | "thinking" | "picking-roof" | "selecting-roof" | "designer";

type PendingPayload = {
  design: DesignResponse;
  recommendation: RecommendationValidationResponse | null;
  houseGlbUrl: string | null;
};

export default function DesignerApp() {
  const [view, setView] = useState<View>("intake");
  const [pendingPayload, setPendingPayload] = useState<PendingPayload | null>(null);
  const [response, setResponse] = useState<DesignResponse | null>(null);
  const [recommendation, setRecommendation] =
    useState<RecommendationValidationResponse | null>(null);
  const [selectedRoof, setSelectedRoof] = useState<SelectedRoof | null>(null);
  const [obstructions, setObstructions] = useState<RoofObstruction[]>([]);
  const [roofPickerError, setRoofPickerError] = useState<string | null>(null);
  const [houseGlbUrl, setHouseGlbUrl] = useState<string | null>(null);
  const [catalogPanel, setCatalogPanel] = useState<CatalogComponent | null>(null);
  const [placement, setPlacement] = useState<PlacementOverride>(DEFAULT_PLACEMENT);
  const previousGlbUrl = useRef<string | null>(null);

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
    setPendingPayload(null);

    // Step 1 + Step 3 can race; Step 2 needs lat/lng.
    // Step 1: fetch GLB (and lat/lng if not already from Places autocomplete).
    const houseModelPromise = fetchHouseModel(profile);

    // Step 3 (still mocked): /api/design for the synthesized BOM.
    // TODO: when backend ships steps G–K, this entire call disappears and
    // step 2's response carries the real Design.
    const designPromise: Promise<DesignResponse | null> = fetch("/api/design", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(profile),
    })
      .then((res) => (res.ok ? (res.json() as Promise<DesignResponse>) : null))
      .catch((err) => {
        console.error("[DesignerApp] /api/design failed:", err);
        return null;
      });

    try {
      const houseModel = await houseModelPromise;
      const latLng =
        profile.latitude != null && profile.longitude != null
          ? { latitude: profile.latitude, longitude: profile.longitude }
          : houseModel.latLng;

      // Step 2: real /api/recommendations now that we have lat/lng.
      let recommendationResponse: RecommendationValidationResponse | null = null;
      if (latLng) {
        try {
          const recRequest = buildRecommendationRequest(
            profile,
            latLng,
            profile.googlePlaceId,
          );
          const formData = new FormData();
          formData.append("request", JSON.stringify(recRequest));
          const recRes = await fetch("/api/recommendations", {
            method: "POST",
            body: formData,
          });
          if (recRes.ok) {
            recommendationResponse =
              (await recRes.json()) as RecommendationValidationResponse;
          } else {
            const detail = await recRes.text();
            console.error(
              "[DesignerApp] /api/recommendations failed",
              recRes.status,
              detail,
            );
          }
        } catch (err) {
          console.error("[DesignerApp] /api/recommendations threw:", err);
        }
      }

      const designResponse = await designPromise;
      if (!designResponse) {
        setView("intake");
        return;
      }

      setPendingPayload({
        design: designResponse,
        recommendation: recommendationResponse,
        houseGlbUrl: houseModel.glbUrl,
      });
    } catch (err) {
      console.error("[DesignerApp] handleGenerate failed:", err);
      setView("intake");
    }
  }, []);

  const confirmRoofSelection = useCallback(
    async (
      satelliteImageUrl: string,
      selectedIds: string[],
    ): Promise<boolean> => {
      setView("selecting-roof");
      setRoofPickerError(null);
      try {
        const [selectionRes, obstructionsRes] = await Promise.all([
          fetch("/api/roof/selection", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              satellite_image_url: satelliteImageUrl,
              selected_roof_outline_ids: selectedIds,
            }),
          }),
          fetch("/api/roof/obstructions", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              satellite_image_url: satelliteImageUrl,
              selected_roof_outline_ids: selectedIds,
            }),
          }),
        ]);

        if (!selectionRes.ok) {
          const detail = await selectionRes.text();
          console.error(
            "[DesignerApp] /api/roof/selection failed",
            selectionRes.status,
            detail,
          );
          setRoofPickerError(
            "We couldn't lock in that selection — try a different building.",
          );
          setView("picking-roof");
          return false;
        }

        const selection = (await selectionRes.json()) as RoofSelectionResponse;
        setSelectedRoof(selection.selected_roof);

        if (obstructionsRes.ok) {
          const obs = (await obstructionsRes.json()) as RoofObstructionAnalysis;
          setObstructions(obs.obstructions);
        } else {
          // Obstruction analysis is best-effort; absence shouldn't block flow.
          setObstructions([]);
          console.warn(
            "[DesignerApp] /api/roof/obstructions failed:",
            obstructionsRes.status,
            await obstructionsRes.text(),
          );
        }

        setView("designer");
        return true;
      } catch (err) {
        console.error("[DesignerApp] roof confirmation threw:", err);
        setRoofPickerError("Network hiccup — please try again.");
        setView("picking-roof");
        return false;
      }
    },
    [],
  );

  const handleNarrativeDone = useCallback(() => {
    if (!pendingPayload) {
      setView("intake");
      return;
    }
    setResponse(pendingPayload.design);
    setRecommendation(pendingPayload.recommendation);
    // Revoke the previous Blob URL when we replace it.
    if (previousGlbUrl.current) URL.revokeObjectURL(previousGlbUrl.current);
    previousGlbUrl.current = pendingPayload.houseGlbUrl;
    setHouseGlbUrl(pendingPayload.houseGlbUrl);

    // Decide whether the user needs to disambiguate the building.
    const roofAnalysis = pendingPayload.recommendation?.roof_analysis;
    const outlines = roofAnalysis?.roof_outlines ?? [];
    const satellite = roofAnalysis?.satellite_image_url ?? null;

    if (outlines.length >= 1 && satellite) {
      setSelectedRoof(null);
      setObstructions([]);
      setRoofPickerError(null);
      setView("picking-roof");
      return;
    }

    // Zero outlines or no satellite image — degrade gracefully and skip the picker.
    setSelectedRoof(null);
    setObstructions([]);
    setView("designer");
  }, [pendingPayload, confirmRoofSelection]);

  // Clean up the Blob URL on unmount so we don't leak memory.
  useEffect(() => {
    return () => {
      if (previousGlbUrl.current) URL.revokeObjectURL(previousGlbUrl.current);
    };
  }, []);

  const handleBack = useCallback(() => {
    setView("intake");
  }, []);

  const panelDims: PanelDimensions = dimensionsFor(catalogPanel);

  if (view === "designer" && response) {
    return (
      <Designer
        response={response}
        baseDesign={response.design}
        panelDims={panelDims}
        modelUrl={houseGlbUrl ?? HOUSE_GLB}
        placementOverride={placement}
        onPlacementChange={setPlacement}
        onPlacementReset={() => setPlacement(DEFAULT_PLACEMENT)}
        recommendation={recommendation}
        selectedRoof={selectedRoof}
        obstructions={obstructions}
        onBack={handleBack}
      />
    );
  }

  if (
    (view === "picking-roof" || view === "selecting-roof") &&
    recommendation?.roof_analysis &&
    recommendation.roof_analysis.satellite_image_url
  ) {
    const ra = recommendation.roof_analysis;
    return (
      <RoofPicker
        roofAnalysis={ra}
        address={recommendation.input.address}
        loading={view === "selecting-roof"}
        error={roofPickerError}
        onConfirm={(ids) =>
          void confirmRoofSelection(ra.satellite_image_url ?? "", ids)
        }
        onBack={handleBack}
      />
    );
  }

  return (
    <>
      <AddressIntake
        onSubmit={handleGenerate}
        disabled={view === "thinking"}
      />
      {view === "thinking" && (
        <ProcessingNarrative
          onDone={handleNarrativeDone}
          ready={pendingPayload !== null}
        />
      )}
    </>
  );
}

/**
 * Fetch the Photorealistic 3D Tiles GLB for the home from the backend (via
 * the Next proxy). Returns a Blob URL plus the geocoded lat/lng so the caller
 * can fall back to backend-side geocoding when the user typed an address by
 * hand instead of selecting a Google Places result.
 */
async function fetchHouseModel(profile: Profile): Promise<{
  glbUrl: string | null;
  latLng: { latitude: number; longitude: number } | null;
}> {
  const body: Record<string, unknown> = { address: profile.address };
  if (profile.latitude != null && profile.longitude != null) {
    body.latitude = profile.latitude;
    body.longitude = profile.longitude;
  }
  try {
    const res = await fetch("/api/location/house-model", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.text();
      console.warn(
        "[DesignerApp] /api/location/house-model failed",
        res.status,
        detail,
      );
      return { glbUrl: null, latLng: null };
    }
    const meta = parseRoofeeMetadata(res.headers.get("Roofee-Metadata"));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const latLng =
      meta != null
        ? { latitude: meta.anchor_latitude, longitude: meta.anchor_longitude }
        : null;
    return { glbUrl: url, latLng };
  } catch (err) {
    console.warn("[DesignerApp] /api/location/house-model threw:", err);
    return { glbUrl: null, latLng: null };
  }
}

function parseRoofeeMetadata(raw: string | null): HouseModelMetadata | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as HouseModelMetadata;
  } catch {
    return null;
  }
}
