"use client";
import { Canvas } from "@react-three/fiber";
import { Suspense, useState } from "react";
import * as THREE from "three";
import {
  OrbitControls,
  Environment,
  ContactShadows,
  Html,
  useProgress,
} from "@react-three/drei";
import {
  EffectComposer,
  N8AO,
  Bloom,
  Vignette,
  SMAA,
} from "@react-three/postprocessing";
import { House } from "./House";
import { RoofPlacedPanels, type PlacementOverride } from "./RoofPlacedPanels";
import { SyntheticHouse } from "./SyntheticHouse";
import type { CanvasMode } from "./CanvasModeToggle";
import { DEFAULT_PANEL, type PanelDimensions } from "@/lib/catalog";
import type {
  PanelPlacement as BackendPanelPlacement,
  RoofGeometryAnalysisResponse,
  SolarModulePreset,
} from "@/types/roof";

function Loader() {
  const { progress } = useProgress();
  return (
    <Html center className="text-white text-sm">
      {progress.toFixed(0)}%
    </Html>
  );
}

export function Scene({
  panelCount,
  panel = DEFAULT_PANEL,
  modelUrl,
  placementOverride,
  backendPlacements,
  backendModule,
  canvasMode = "real",
  roofGeometry = null,
}: {
  panelCount: number;
  panel?: PanelDimensions;
  modelUrl: string;
  placementOverride?: PlacementOverride;
  backendPlacements?: BackendPanelPlacement[];
  backendModule?: SolarModulePreset | null;
  canvasMode?: CanvasMode;
  roofGeometry?: RoofGeometryAnalysisResponse | null;
}) {
  const [houseRoot, setHouseRoot] = useState<THREE.Object3D | null>(null);
  const showSynthetic = canvasMode === "synthetic" && roofGeometry !== null;
  const bg = showSynthetic ? "#f3eee0" : "#e8f0f7";

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [22, 16, 22], fov: 35 }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={[bg]} />
      <Suspense fallback={<Loader />}>
        {showSynthetic ? (
          <SyntheticHouse geometry={roofGeometry!} onReady={setHouseRoot} />
        ) : (
          <House url={modelUrl} onReady={setHouseRoot} />
        )}
        {houseRoot && !showSynthetic && (
          <RoofPlacedPanels
            houseRoot={houseRoot}
            panelCount={panelCount}
            panel={panel}
            override={placementOverride}
            backendPlacements={backendPlacements}
            backendModule={backendModule}
          />
        )}
        <Environment preset="sunset" />
        <ContactShadows
          position={[0, -0.01, 0]}
          opacity={0.55}
          blur={2.5}
          scale={30}
          far={10}
        />
        <EffectComposer>
          <N8AO halfRes aoRadius={0.5} intensity={1.2} />
          <Bloom intensity={0.3} luminanceThreshold={1} mipmapBlur />
          <Vignette eskil={false} offset={0.1} darkness={0.6} />
          <SMAA />
        </EffectComposer>
      </Suspense>
      <OrbitControls
        makeDefault
        enableDamping
        maxPolarAngle={Math.PI / 2.1}
        target={[0, 5, 0]}
      />
    </Canvas>
  );
}
