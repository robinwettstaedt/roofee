"use client";

import { useEffect, useRef, useState } from "react";
import { loadGoogleMaps } from "@/lib/google-maps";

export type PickedHouseLocation = {
  latitude: number;
  longitude: number;
  altitude?: number | null;
};

type LocationClickEventLike = Event & {
  position?: {
    lat?: number;
    lng?: number;
    latitude?: number;
    longitude?: number;
    altitude?: number;
  };
};

type Map3DElementLike = HTMLElement & {
  center?: unknown;
  append: (...nodes: HTMLElement[]) => void;
};

type Maps3DLibrary = {
  Map3DElement: new (options: Record<string, unknown>) => Map3DElementLike;
  Marker3DElement?: new (options: Record<string, unknown>) => HTMLElement;
};

export function HouseTilePicker({
  address,
  latitude,
  longitude,
  loading,
  error,
  onConfirm,
  onBack,
}: {
  address: string;
  latitude: number;
  longitude: number;
  loading: boolean;
  error: string | null;
  onConfirm: (picked: PickedHouseLocation) => void;
  onBack: () => void;
}) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map3DElementLike | null>(null);
  const markerRef = useRef<HTMLElement | null>(null);
  const markerCtorRef = useRef<Maps3DLibrary["Marker3DElement"] | null>(null);
  const [picked, setPicked] = useState<PickedHouseLocation | null>(null);
  const [mapError, setMapError] = useState<string | null>(() =>
    apiKey ? null : "Google Maps is not configured.",
  );

  useEffect(() => {
    if (!apiKey) {
      return;
    }
    const mapsApiKey = apiKey;
    const host = hostRef.current;
    if (!host) return;

    let cancelled = false;
    let clickHandler: ((event: Event) => void) | null = null;

    async function init() {
      try {
        const google = await loadGoogleMaps(mapsApiKey);
        const maps3d = (await google.maps.importLibrary("maps3d")) as Maps3DLibrary;
        if (cancelled || !hostRef.current) return;

        const map = new maps3d.Map3DElement({
          center: { lat: latitude, lng: longitude, altitude: 0 },
          range: 240,
          tilt: 58,
          heading: 0,
          mode: "SATELLITE",
          gestureHandling: "COOPERATIVE",
        });
        map.className = "h-full w-full";
        map.style.display = "block";
        mapRef.current = map;
        markerCtorRef.current = maps3d.Marker3DElement ?? null;

        clickHandler = (event: Event) => {
          const position = (event as LocationClickEventLike).position;
          const lat = position?.lat ?? position?.latitude;
          const lng = position?.lng ?? position?.longitude;
          if (typeof lat !== "number" || typeof lng !== "number") return;
          const next = {
            latitude: lat,
            longitude: lng,
            altitude: position?.altitude ?? null,
          };
          setPicked(next);
          setMarker(next);
        };

        map.addEventListener("gmp-click", clickHandler);
        hostRef.current.replaceChildren(map);
        const initial = { latitude, longitude, altitude: null };
        setPicked(initial);
        setMarker(initial);
      } catch (err) {
        console.error("[HouseTilePicker] 3D map failed:", err);
        setMapError("The 3D map could not be loaded.");
      }
    }

    function setMarker(location: PickedHouseLocation) {
      const map = mapRef.current;
      const Marker3DElement = markerCtorRef.current;
      if (!map || !Marker3DElement) return;
      if (markerRef.current) {
        markerRef.current.remove();
      }
      const marker = new Marker3DElement({
        position: {
          lat: location.latitude,
          lng: location.longitude,
          altitude: location.altitude ?? 0,
        },
        altitudeMode: "RELATIVE_TO_MESH",
        extruded: true,
        label: "Selected house",
      });
      markerRef.current = marker;
      map.append(marker);
    }

    void init();
    return () => {
      cancelled = true;
      if (mapRef.current && clickHandler) {
        mapRef.current.removeEventListener("gmp-click", clickHandler);
      }
      host.replaceChildren();
      mapRef.current = null;
      markerRef.current = null;
      markerCtorRef.current = null;
    };
  }, [apiKey, latitude, longitude]);

  const visibleError = error ?? mapError;

  return (
    <div className="flex h-screen w-screen flex-col">
      <header className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={onBack}
            disabled={loading}
            className="text-[13px] text-dust transition hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← Edit address
          </button>
          <span className="text-[15px] font-semibold tracking-tight text-ink">
            Roofee
          </span>
        </div>
        <span className="hidden truncate text-[12px] text-dust md:block md:max-w-[420px]">
          {address}
        </span>
      </header>

      <main className="flex min-h-0 flex-1 flex-col px-6 pb-6">
        <div className="mb-4 flex items-end justify-between gap-6">
          <div>
            <h1 className="text-[26px] font-medium leading-tight tracking-tight text-ink">
              Select the house.
            </h1>
            <p className="mt-2 text-[13px] text-dust">
              Click the correct building in the 3D view.
            </p>
          </div>
          <button
            type="button"
            disabled={!picked || loading || Boolean(mapError)}
            onClick={() => picked && onConfirm(picked)}
            className="inline-flex items-center gap-2 rounded-full bg-signal px-7 py-3 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
          >
            {loading ? (
              <>
                Analyzing…
                <span
                  className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper"
                  aria-hidden
                />
              </>
            ) : (
              <>
                Use this house
                <span aria-hidden>→</span>
              </>
            )}
          </button>
        </div>

        <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-ink/15 bg-paper-deep">
          <div ref={hostRef} className="h-full w-full" />
          {visibleError && (
            <div className="absolute left-4 top-4 max-w-sm rounded-md border border-signal/25 bg-paper px-4 py-3 text-[12px] text-signal shadow-sm">
              {visibleError}
            </div>
          )}
          {picked && !visibleError && (
            <div className="absolute bottom-4 left-4 rounded-md border border-ink/10 bg-paper/95 px-3 py-2 text-[12px] text-ink shadow-sm">
              {picked.latitude.toFixed(6)}, {picked.longitude.toFixed(6)}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
