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
import { DEFAULT_PANEL, type PanelDimensions } from "@/lib/catalog";

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
}: {
  panelCount: number;
  panel?: PanelDimensions;
  modelUrl: string;
  placementOverride?: PlacementOverride;
}) {
  const [houseRoot, setHouseRoot] = useState<THREE.Object3D | null>(null);

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [22, 16, 22], fov: 35 }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#e8f0f7"]} />
      <Suspense fallback={<Loader />}>
        <House url={modelUrl} onReady={setHouseRoot} />
        {houseRoot && (
          <RoofPlacedPanels
            houseRoot={houseRoot}
            panelCount={panelCount}
            panel={panel}
            override={placementOverride}
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
