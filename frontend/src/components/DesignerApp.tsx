"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AddressIntake } from "./AddressIntake";
import { Designer } from "./Designer";
import { HouseTilePicker, type TilePick } from "./HouseTilePicker";
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
  RoofGeometryAnalysisResponse,
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

type View =
  | "intake"
  | "picking-tile"
  | "thinking"
  | "picking-roof"
  | "selecting-roof"
  | "designer";

type PendingPayload = {
  design: DesignResponse;
  recommendation: RecommendationValidationResponse | null;
  houseGlbUrl: string | null;
};

export default function DesignerApp() {
  const [view, setView] = useState<View>("intake");
  const [pendingProfile, setPendingProfile] = useState<Profile | null>(null);
  const [pendingPayload, setPendingPayload] = useState<PendingPayload | null>(null);
  const [response, setResponse] = useState<DesignResponse | null>(null);
  const [recommendation, setRecommendation] =
    useState<RecommendationValidationResponse | null>(null);
  const [selectedRoof, setSelectedRoof] = useState<SelectedRoof | null>(null);
  const [obstructions, setObstructions] = useState<RoofObstruction[]>([]);
  const [roofGeometry, setRoofGeometry] =
    useState<RoofGeometryAnalysisResponse | null>(null);
  const [roofPickerError, setRoofPickerError] = useState<string | null>(null);
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

  const runPipeline = useCallback(
    async (
      profile: Profile,
      houseModelPromise: Promise<{
        glbUrl: string | null;
        latLng: { latitude: number; longitude: number } | null;
      }>,
    ) => {
      setView("thinking");
      setPendingPayload(null);
      setRoofGeometry(null);

      // Step 3 (still mocked): /api/design for the synthesized BOM.
      // TODO: when backend ships steps G–K, this entire call disappears and
      // step 2's response carries the real Design.
      const designPromise: Promise<DesignResponse | null> = fetch(
        "/api/design",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(profile),
        },
      )
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
        console.error("[DesignerApp] runPipeline failed:", err);
        setView("intake");
      }
    },
    [],
  );

  const handleAddressSubmit = useCallback(
    (profile: Profile) => {
      setPendingProfile(profile);
      // If we have a geocoded lat/lng (from Places autocomplete) AND the browser
      // has the Maps API key wired up, let the user pick the building in 3D
      // first; otherwise fall back to the address-driven server-side walk.
      const hasLatLng =
        profile.latitude != null && profile.longitude != null;
      const hasApiKey = !!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
      if (hasLatLng && hasApiKey) {
        setView("picking-tile");
        return;
      }
      void runPipeline(profile, fetchHouseModel(profile));
    },
    [runPipeline],
  );

  const handleTilePickConfirm = useCallback(
    (pick: TilePick) => {
      const profile = pendingProfile;
      if (!profile) {
        setView("intake");
        return;
      }
      const houseModelPromise = pick.tileUri
        ? fetchTileGlb(pick, profile)
        : fetchHouseModel(profile);
      void runPipeline(profile, houseModelPromise);
    },
    [pendingProfile, runPipeline],
  );

  const confirmRoofSelection = useCallback(
    async (
      satelliteImageUrl: string,
      selectedIds: string[],
    ): Promise<boolean> => {
      setView("selecting-roof");
      setRoofPickerError(null);
      try {
        const geometryRes = await fetch("/api/roof/geometry", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            satellite_image_url: satelliteImageUrl,
            selected_roof_outline_ids: selectedIds,
          }),
        });

        if (!geometryRes.ok) {
          const detail = await geometryRes.text();
          console.error(
            "[DesignerApp] /api/roof/geometry failed",
            geometryRes.status,
            detail,
          );
          setRoofPickerError(
            "We couldn't calculate panel placement for that roof — try a different building.",
          );
          setView("picking-roof");
          return false;
        }

        const geometry =
          (await geometryRes.json()) as RoofGeometryAnalysisResponse;
        setRoofGeometry(geometry);
        setSelectedRoof(geometry.selected_roof);
        setObstructions([]);

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
      setRoofGeometry(null);
      setRoofPickerError(null);
      setView("picking-roof");
      return;
    }

    // Zero outlines or no satellite image — degrade gracefully and skip the picker.
    setSelectedRoof(null);
    setObstructions([]);
    setRoofGeometry(null);
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
        obstructions={obstructions}
        roofGeometry={roofGeometry}
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

  if (
    view === "picking-tile" &&
    pendingProfile?.latitude != null &&
    pendingProfile.longitude != null
  ) {
    return (
      <HouseTilePicker
        address={pendingProfile.address}
        latitude={pendingProfile.latitude}
        longitude={pendingProfile.longitude}
        onConfirm={handleTilePickConfirm}
        onBack={handleBack}
        loading={false}
        error={null}
      />
    );
  }

  return (
    <>
      <AddressIntake
        onSubmit={handleAddressSubmit}
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

/**
 * Fetch the GLB for the leaf tile the user picked in the 3D viewer. Falls back
 * to the address-driven walk if the backend can't stream the requested tile,
 * so the user never gets stranded on a network error.
 */
async function fetchTileGlb(
  pick: TilePick,
  profile: Profile,
): Promise<{
  glbUrl: string | null;
  latLng: { latitude: number; longitude: number } | null;
}> {
  try {
    const res = await fetch("/api/location/tile-glb", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        tile_uri: pick.tileUri,
        session: pick.session,
        latitude: profile.latitude ?? null,
        longitude: profile.longitude ?? null,
      }),
    });
    if (!res.ok) {
      const detail = await res.text();
      console.warn(
        "[DesignerApp] /api/location/tile-glb failed, falling back",
        res.status,
        detail,
      );
      return fetchHouseModel(profile);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const latLng =
      profile.latitude != null && profile.longitude != null
        ? { latitude: profile.latitude, longitude: profile.longitude }
        : null;
    return { glbUrl: url, latLng };
  } catch (err) {
    console.warn("[DesignerApp] /api/location/tile-glb threw, falling back:", err);
    return fetchHouseModel(profile);
  }
}
