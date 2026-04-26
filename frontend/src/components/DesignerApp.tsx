"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AddressIntake } from "./AddressIntake";
import { Designer } from "./Designer";
import { HouseTilePicker, type PickedHouseLocation } from "./HouseTilePicker";
import { ProcessingNarrative } from "./ProcessingNarrative";
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
  ProposalResponse,
  RecommendationValidationResponse,
} from "@/types/recommendation";
import type { RoofGeometryAnalysisResponse, SelectedRoof } from "@/types/roof";

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

type View = "intake" | "picking-house" | "thinking" | "designer";

type PendingPayload = {
  design: DesignResponse;
  recommendation: RecommendationValidationResponse | null;
  houseGlbUrl: string | null;
  roofGeometry: RoofGeometryAnalysisResponse | null;
};

export default function DesignerApp() {
  const [view, setView] = useState<View>("intake");
  const [pendingPayload, setPendingPayload] = useState<PendingPayload | null>(null);
  const [response, setResponse] = useState<DesignResponse | null>(null);
  const [recommendation, setRecommendation] =
    useState<RecommendationValidationResponse | null>(null);
  const [activeProfile, setActiveProfile] = useState<Profile | null>(null);
  const [selectedRoof, setSelectedRoof] = useState<SelectedRoof | null>(null);
  const [roofGeometry, setRoofGeometry] =
    useState<RoofGeometryAnalysisResponse | null>(null);
  const [housePickerError, setHousePickerError] = useState<string | null>(null);
  const [houseGlbUrl, setHouseGlbUrl] = useState<string | null>(null);
  const [catalogPanel, setCatalogPanel] = useState<CatalogComponent | null>(null);
  const [placement, setPlacement] =
    useState<PlacementOverride>(loadStoredPlacement);
  const previousGlbUrl = useRef<string | null>(null);

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
    setRoofGeometry(null);
    setHousePickerError(null);
    setSelectedRoof(null);

    const latLng = await resolveProfileLatLng(profile);
    if (!latLng) {
      setHousePickerError("We couldn't locate that address. Select an autocomplete result or try another address.");
      setView("intake");
      return;
    }

    setActiveProfile({
      ...profile,
      latitude: latLng.latitude,
      longitude: latLng.longitude,
    });
    setView("picking-house");
  }, []);

  const confirmHouseSelection = useCallback(async (picked: PickedHouseLocation) => {
    if (activeProfile?.latitude == null || activeProfile.longitude == null) {
      setView("intake");
      return;
    }

    setView("thinking");
    setPendingPayload(null);
    setRoofGeometry(null);
    setSelectedRoof(null);

    const designPromise: Promise<DesignResponse | null> = fetch("/api/design", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(activeProfile),
    })
      .then((res) => (res.ok ? (res.json() as Promise<DesignResponse>) : null))
      .catch((err) => {
        console.error("[DesignerApp] /api/design failed:", err);
        return null;
      });

    try {
      const recRequest = buildRecommendationRequest(
        activeProfile,
        { latitude: activeProfile.latitude, longitude: activeProfile.longitude },
        activeProfile.googlePlaceId,
      );
      const houseModel = await fetchHouseModelBlob(picked);
      if (!houseModel) {
        setHousePickerError("We couldn't load the selected 3D model. Try clicking the house again.");
        setView("picking-house");
        return;
      }
      const formData = new FormData();
      formData.append(
        "request",
        JSON.stringify({
          project: recRequest,
          picked_location: {
            latitude: picked.latitude,
            longitude: picked.longitude,
          },
        }),
      );
      formData.append("model_file", houseModel, "selected-house.glb");
      const proposalRes = await fetch("/api/proposal", {
        method: "POST",
        body: formData,
      });
      if (!proposalRes.ok) {
        const detail = await proposalRes.text();
        console.error("[DesignerApp] /api/proposal failed", proposalRes.status, detail);
        setHousePickerError("We couldn't analyze that house. Try clicking the roof again.");
        setView("picking-house");
        return;
      }

      const proposal = (await proposalRes.json()) as ProposalResponse;
      const designResponse = await designPromise;
      if (!designResponse) {
        setView("intake");
        return;
      }

      setPendingPayload({
        design: designResponse,
        recommendation: proposal.recommendation,
        houseGlbUrl: modelUrlFromProposal(proposal),
        roofGeometry: proposal.roof_geometry,
      });
    } catch (err) {
      console.error("[DesignerApp] proposal flow failed:", err);
      setHousePickerError("Network hiccup — please try again.");
      setView("picking-house");
    }
  }, [activeProfile]);

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
    setRoofGeometry(pendingPayload.roofGeometry);
    setSelectedRoof(pendingPayload.roofGeometry?.selected_roof ?? null);
    setView("designer");
  }, [pendingPayload]);

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
        obstructions={[]}
        roofGeometry={roofGeometry}
        onBack={handleBack}
      />
    );
  }

  if (
    view === "picking-house" &&
    activeProfile?.latitude != null &&
    activeProfile.longitude != null
  ) {
    return (
      <HouseTilePicker
        address={activeProfile.address}
        latitude={activeProfile.latitude}
        longitude={activeProfile.longitude}
        loading={false}
        error={housePickerError}
        onConfirm={(picked) => void confirmHouseSelection(picked)}
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

async function resolveProfileLatLng(
  profile: Profile,
): Promise<{ latitude: number; longitude: number } | null> {
  if (profile.latitude != null && profile.longitude != null) {
    return { latitude: profile.latitude, longitude: profile.longitude };
  }
  try {
    const res = await fetch("/api/location/geocode", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ address: profile.address }),
    });
    if (!res.ok) {
      const detail = await res.text();
      console.warn("[DesignerApp] /api/location/geocode failed", res.status, detail);
      return null;
    }
    const payload = (await res.json()) as {
      latitude?: number;
      longitude?: number;
    };
    if (typeof payload.latitude !== "number" || typeof payload.longitude !== "number") {
      return null;
    }
    return { latitude: payload.latitude, longitude: payload.longitude };
  } catch (err) {
    console.warn("[DesignerApp] /api/location/geocode threw:", err);
    return null;
  }
}

function modelUrlFromProposal(proposal: ProposalResponse): string | null {
  const overheadUrl = proposal.recommendation.house_data?.overhead_image_url;
  const assetId = assetIdFromOverheadUrl(overheadUrl);
  return assetId ? `/api/house-assets/${assetId}/house.glb` : null;
}

async function fetchHouseModelBlob(
  picked: PickedHouseLocation,
): Promise<Blob | null> {
  try {
    const res = await fetch("/api/location/house-model", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        latitude: picked.latitude,
        longitude: picked.longitude,
        radius_m: 120,
      }),
    });
    if (!res.ok) {
      const detail = await res.text();
      console.warn("[DesignerApp] /api/location/house-model failed", res.status, detail);
      return null;
    }
    return await res.blob();
  } catch (err) {
    console.warn("[DesignerApp] /api/location/house-model threw:", err);
    return null;
  }
}

function assetIdFromOverheadUrl(url: string | null | undefined): string | null {
  const match = url?.match(/^\/api\/house-assets\/([^/]+)\/overhead\.png$/);
  return match?.[1] ?? null;
}
