"use client";
import { Canvas, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Object3D, Raycaster, Vector2 } from "three";
import { Html, useProgress } from "@react-three/drei";
import { TilesPlugin, TilesRenderer } from "3d-tiles-renderer/r3f";
import { GoogleCloudAuthPlugin } from "3d-tiles-renderer/plugins";
import type { TilesRenderer as TilesRendererImpl } from "3d-tiles-renderer/three";
import { EnvironmentControls } from "3d-tiles-renderer/three";
import {
  cameraPoseForHouse,
  pickTileContentUrl,
} from "@/lib/google3DTiles";

const GOOGLE_TILES_ROOT_URL =
  "https://tile.googleapis.com/v1/3dtiles/root.json";

export type TilePick = {
  tileUri: string;
  session: string | null;
  hitPoint: { x: number; y: number; z: number };
};

function Loader() {
  const { progress } = useProgress();
  return (
    <Html center className="text-[12px] tracking-wide text-paper/85">
      Loading tiles… {progress.toFixed(0)}%
    </Html>
  );
}

/**
 * Inner R3F scene. Mounts the Google 3D Tileset, sets up the initial camera
 * pose looking at the geocoded house, and forwards leaf-tile picks back up.
 */
function PickerScene({
  lat,
  lng,
  apiKey,
  onPick,
  setHasFetchedAny,
}: {
  lat: number;
  lng: number;
  apiKey: string;
  onPick: (pick: TilePick) => void;
  setHasFetchedAny: (v: boolean) => void;
}) {
  const [tiles, setTiles] = useState<TilesRendererImpl | null>(null);
  const { camera, gl, scene } = useThree();

  useEffect(() => {
    // Position + up are mutated on sub-objects (Vector3), which is r3f-idiomatic;
    // near/far/fov come from the parent Canvas's camera={...} prop so we don't
    // need to touch top-level fields on the hook-owned camera here.
    const pose = cameraPoseForHouse(lat, lng);
    camera.position.copy(pose.position);
    camera.up.copy(pose.up);
    camera.lookAt(pose.target);
  }, [lat, lng, camera]);

  // Stand up the EnvironmentControls (handles up-vector + ground constraint
  // for ECEF coords, which OrbitControls can't do out of the box).
  useEffect(() => {
    if (!tiles) return;
    const controls = new EnvironmentControls(scene, camera, gl.domElement, tiles);
    controls.enableDamping = true;
    controls.minDistance = 25;
    controls.maxDistance = 4000;
    let raf = 0;
    let lastTime = performance.now();
    const tick = () => {
      const now = performance.now();
      controls.update((now - lastTime) / 1000);
      lastTime = now;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      controls.dispose();
    };
  }, [tiles, scene, camera, gl]);

  // Tag every loaded tile mesh with the absolute URL it was fetched from so
  // we can read it back during a click raycast.
  const handleLoadModel = useCallback(
    (event: { scene: Object3D; url: string }) => {
      if (event?.scene && typeof event.url === "string") {
        event.scene.userData.tileContentUrl = event.url;
      }
      setHasFetchedAny(true);
    },
    [setHasFetchedAny],
  );

  // Pointer-up click handler with a small drag tolerance so orbit drags don't
  // register as picks.
  useEffect(() => {
    const canvas = gl.domElement;
    let downXY: { x: number; y: number } | null = null;

    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      downXY = { x: e.clientX, y: e.clientY };
    };
    const onUp = (e: PointerEvent) => {
      if (e.button !== 0 || !downXY) return;
      const dx = Math.abs(e.clientX - downXY.x);
      const dy = Math.abs(e.clientY - downXY.y);
      downXY = null;
      if (dx > 4 || dy > 4) return;

      const rect = canvas.getBoundingClientRect();
      const ndc = new Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      const raycaster = new Raycaster();
      raycaster.setFromCamera(ndc, camera);
      raycaster.far = 1e8;
      if (!tiles) return;
      const hits = raycaster.intersectObject(
        tiles.group as unknown as Object3D,
        true,
      );
      if (hits.length === 0) return;

      const url = pickTileContentUrl(hits[0].object);
      if (!url) return;

      const plugin = tiles.getPluginByName?.("GOOGLE_CLOUD_AUTH_PLUGIN") as
        | { auth?: { sessionToken?: string | null } }
        | undefined;
      const session = plugin?.auth?.sessionToken ?? null;

      const point = hits[0].point;
      onPick({
        tileUri: url,
        session,
        hitPoint: { x: point.x, y: point.y, z: point.z },
      });
    };

    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointerup", onUp);
    return () => {
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointerup", onUp);
    };
  }, [gl, camera, onPick, tiles]);

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight intensity={1.0} position={[1, 1, 1]} />
      <TilesRenderer
        ref={setTiles}
        url={GOOGLE_TILES_ROOT_URL}
        onLoadModel={handleLoadModel}
      >
        <TilesPlugin
          plugin={GoogleCloudAuthPlugin}
          args={[{ apiToken: apiKey, autoRefreshToken: true }]}
        />
      </TilesRenderer>
    </>
  );
}

/**
 * 3D Photorealistic Tiles building picker. Loads the Google tileset around the
 * geocoded address, lets the user orbit and click their house, and emits the
 * picked leaf tile's content URL plus the active Google Cloud session token
 * so the backend can stream that exact tile.
 */
export function HouseTilePicker({
  address,
  latitude,
  longitude,
  onConfirm,
  onBack,
  loading,
  error,
}: {
  address: string;
  latitude: number;
  longitude: number;
  onConfirm: (pick: TilePick) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const [pick, setPick] = useState<TilePick | null>(null);
  const [hasFetchedAny, setHasFetchedAny] = useState(false);
  const initialCameraPosition = useMemo(
    () =>
      cameraPoseForHouse(latitude, longitude).position.toArray() as [
        number,
        number,
        number,
      ],
    [latitude, longitude],
  );

  const handlePick = useCallback((next: TilePick) => {
    setPick(next);
  }, []);

  const handleConfirm = () => {
    if (!pick || loading) return;
    onConfirm(pick);
  };

  const handleSkip = () => {
    if (loading) return;
    onConfirm({
      tileUri: "",
      session: null,
      hitPoint: { x: 0, y: 0, z: 0 },
    });
  };

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

      <main className="flex flex-1 items-start justify-center overflow-hidden px-6 pb-6">
        <div className="flex h-full w-full max-w-[1200px] flex-col">
          <div className="rise mb-5">
            <h1 className="text-[28px] font-medium leading-tight tracking-tight text-ink">
              Pick the building.
            </h1>
            <p className="mt-2 text-[14px] text-dust">
              We zoomed onto the address in Google Photorealistic 3D. Drag to
              orbit, scroll to zoom, then click your house to lock the
              high-detail tile.
            </p>
          </div>

          <div className="rise relative flex-1 overflow-hidden rounded-xl border border-ink/15 bg-ink/95">
            {apiKey ? (
              <Canvas
                gl={{ logarithmicDepthBuffer: true, antialias: true }}
                camera={{
                  position: initialCameraPosition,
                  fov: 55,
                  near: 1,
                  far: 1e8,
                }}
                dpr={[1, 2]}
              >
                <color attach="background" args={["#0d0d0e"]} />
                <Suspense fallback={<Loader />}>
                  <PickerScene
                    lat={latitude}
                    lng={longitude}
                    apiKey={apiKey}
                    onPick={handlePick}
                    setHasFetchedAny={setHasFetchedAny}
                  />
                </Suspense>
              </Canvas>
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-[13px] text-paper/85">
                NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is not set, so the Photorealistic
                3D Tiles preview is disabled. We&rsquo;ll skip ahead and use
                server-side tile selection instead.
              </div>
            )}

            {/* Soft hint overlay until a click is registered */}
            {apiKey && !pick && (
              <div className="overlay-surface pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-full px-4 py-1.5 text-[12px] tracking-wide text-ink">
                {hasFetchedAny
                  ? "Click the building to confirm"
                  : "Streaming tiles…"}
              </div>
            )}

            {apiKey && pick && (
              <div className="overlay-surface pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-full px-4 py-1.5 text-[12px] tracking-wide text-ink">
                Tile locked. Confirm below to continue.
              </div>
            )}
          </div>

          {error && <p className="mt-4 text-[12px] text-signal">{error}</p>}

          <footer className="mt-6 flex items-center justify-between">
            <p className="text-[12px] text-dust">
              {pick
                ? "1 leaf tile selected"
                : "Click on your house once it's in view"}
            </p>
            <div className="flex items-center gap-4">
              {!apiKey || !pick ? (
                <button
                  type="button"
                  onClick={handleSkip}
                  disabled={loading}
                  className="text-[13px] text-dust transition hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Skip and use server selection
                </button>
              ) : null}
              <button
                type="button"
                disabled={!pick || loading}
                onClick={handleConfirm}
                className="inline-flex items-center gap-2 rounded-full bg-signal px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
              >
                {loading ? (
                  <>
                    Loading model…
                    <span
                      className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper"
                      aria-hidden
                    />
                  </>
                ) : (
                  <>
                    Use this tile
                    <span aria-hidden>→</span>
                  </>
                )}
              </button>
            </div>
          </footer>
        </div>
      </main>
    </div>
  );
}
