"use client";
import * as THREE from "three";
import { useEffect, useMemo } from "react";
import type { PanelDimensions } from "@/lib/catalog";
import type {
  PanelPlacement as BackendPanelPlacement,
  SolarModulePreset,
} from "@/types/roof";

type Pose = {
  id: string;
  pos: [number, number, number];
  rot: [number, number, number];
};

type BackendPose = Pose & {
  lengthMeters: number;
  widthMeters: number;
  thicknessMeters: number;
};

const UP = new THREE.Vector3(0, 1, 0);
const SAMPLE_OFFSETS_M = 1.5;

function castDown(
  houseRoot: THREE.Object3D,
  x: number,
  z: number,
): THREE.Intersection | null {
  const box = new THREE.Box3().setFromObject(houseRoot);
  const ray = new THREE.Raycaster(
    new THREE.Vector3(x, box.max.y + 50, z),
    new THREE.Vector3(0, -1, 0),
  );
  const hits = ray.intersectObject(houseRoot, true);
  return hits[0] ?? null;
}

function findRoof(houseRoot: THREE.Object3D): THREE.Intersection | null {
  const offsets: [number, number][] = [
    [0, 0],
    [SAMPLE_OFFSETS_M, 0],
    [-SAMPLE_OFFSETS_M, 0],
    [0, SAMPLE_OFFSETS_M],
    [0, -SAMPLE_OFFSETS_M],
  ];
  let best: THREE.Intersection | null = null;
  for (const [dx, dz] of offsets) {
    const hit = castDown(houseRoot, dx, dz);
    if (!hit) continue;
    if (!best || hit.point.y > best.point.y) best = hit;
  }
  return best;
}

function buildGrid(
  count: number,
  origin: THREE.Vector3,
  normalWorld: THREE.Vector3,
  panel: PanelDimensions,
  colsOverride?: number,
  yawDeg = 0,
): Pose[] {
  const cols = Math.min(colsOverride ?? 6, count);
  const rows = Math.ceil(count / cols);
  const dx = panel.lengthMeters * 1.02;
  const dz = panel.widthMeters * 1.02;

  const n = normalWorld.clone().normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(UP, n);
  const yawQ = new THREE.Quaternion().setFromAxisAngle(
    n,
    THREE.MathUtils.degToRad(yawDeg),
  );
  const finalQ = yawQ.multiply(q);
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(finalQ);
  const forward = new THREE.Vector3(0, 0, 1).applyQuaternion(finalQ);
  const lift = n.clone().multiplyScalar(0.05);
  const e = new THREE.Euler().setFromQuaternion(finalQ);

  const startX = -((cols - 1) * dx) / 2;
  const startZ = -((rows - 1) * dz) / 2;

  const poses: Pose[] = [];
  let i = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (i >= count) break;
      const offset = right
        .clone()
        .multiplyScalar(startX + c * dx)
        .add(forward.clone().multiplyScalar(startZ + r * dz))
        .add(lift);
      const pos = origin.clone().add(offset);
      poses.push({
        id: `panel-${i}`,
        pos: [pos.x, pos.y, pos.z],
        rot: [e.x, e.y, e.z],
      });
      i++;
    }
  }
  return poses;
}

export type PlacementOverride = {
  center: [number, number, number];
  tiltDeg: number;
  azimuthDeg: number;
  yawDeg?: number;
  cols?: number;
};

function normalFromTiltAzimuth(tiltDeg: number, azimuthDeg: number): THREE.Vector3 {
  const tilt = THREE.MathUtils.degToRad(tiltDeg);
  const az = THREE.MathUtils.degToRad(azimuthDeg);
  return new THREE.Vector3(
    Math.sin(tilt) * Math.sin(az),
    Math.cos(tilt),
    Math.sin(tilt) * Math.cos(az),
  ).normalize();
}

export function RoofPlacedPanels({
  houseRoot,
  panelCount,
  panel,
  override,
  backendPlacements = [],
  backendModule,
}: {
  houseRoot: THREE.Object3D;
  panelCount: number;
  panel: PanelDimensions;
  override?: PlacementOverride;
  backendPlacements?: BackendPanelPlacement[];
  backendModule?: SolarModulePreset | null;
}) {
  const backendPoses = useMemo<BackendPose[]>(() => {
    if (!backendModule || backendPlacements.length === 0) return [];
    houseRoot.updateMatrixWorld(true);
    const originWorld = houseRoot.localToWorld(new THREE.Vector3(0, 0, 0));

    return backendPlacements
      .map((placement) => {
        if (
          placement.center_model.length !== 3 ||
          placement.normal_model.length !== 3 ||
          placement.length_axis_model.length !== 3
        ) {
          return null;
        }
        const center = houseRoot.localToWorld(
          new THREE.Vector3(
            placement.center_model[0],
            placement.center_model[1],
            placement.center_model[2],
          ),
        );
        const normal = houseRoot
          .localToWorld(
            new THREE.Vector3(
              placement.normal_model[0],
              placement.normal_model[1],
              placement.normal_model[2],
            ),
          )
          .sub(originWorld)
          .normalize();
        const lengthAxis = houseRoot
          .localToWorld(
            new THREE.Vector3(
              placement.length_axis_model[0],
              placement.length_axis_model[1],
              placement.length_axis_model[2],
            ),
          )
          .sub(originWorld)
          .normalize();
        const widthAxis = lengthAxis.clone().cross(normal).normalize();
        const basis = new THREE.Matrix4().makeBasis(lengthAxis, normal, widthAxis);
        const rotation = new THREE.Euler().setFromQuaternion(
          new THREE.Quaternion().setFromRotationMatrix(basis),
        );
        return {
          id: placement.id,
          pos: [center.x, center.y, center.z] as [number, number, number],
          rot: [rotation.x, rotation.y, rotation.z] as [number, number, number],
          lengthMeters: backendModule.length_m,
          widthMeters: backendModule.width_m,
          thicknessMeters: placement.thickness_m || backendModule.thickness_m,
        };
      })
      .filter((pose): pose is BackendPose => pose !== null);
  }, [backendModule, backendPlacements, houseRoot]);

  const poses = useMemo(() => {
    if (backendPoses.length > 0) return [];
    if (panelCount <= 0) return [];

    if (override) {
      const center = new THREE.Vector3(...override.center);
      const normal = normalFromTiltAzimuth(override.tiltDeg, override.azimuthDeg);
      console.info(
        `[RoofPlacedPanels] override center=${center.toArray().map((n) => n.toFixed(2)).join(",")} normal=${normal.toArray().map((n) => n.toFixed(2)).join(",")}`,
      );
      return buildGrid(
        panelCount,
        center,
        normal,
        panel,
        override.cols,
        override.yawDeg ?? 0,
      );
    }

    const hit = findRoof(houseRoot);
    if (!hit || !hit.face) {
      console.warn("[RoofPlacedPanels] no roof hit at scene center");
      return [];
    }
    const normalMatrix = new THREE.Matrix3().getNormalMatrix(
      hit.object.matrixWorld,
    );
    const normalWorld = hit.face.normal
      .clone()
      .applyMatrix3(normalMatrix)
      .normalize();
    if (normalWorld.y < 0) normalWorld.negate();
    console.info(
      `[RoofPlacedPanels] hit at (${hit.point.x.toFixed(2)}, ${hit.point.y.toFixed(2)}, ${hit.point.z.toFixed(2)}) normal=(${normalWorld.x.toFixed(2)}, ${normalWorld.y.toFixed(2)}, ${normalWorld.z.toFixed(2)})`,
    );
    return buildGrid(panelCount, hit.point, normalWorld, panel);
  }, [backendPoses.length, houseRoot, panelCount, panel, override]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    (window as unknown as { __roofeePanels?: unknown }).__roofeePanels = {
      panelCount,
      backendPoseCount: backendPoses.length,
      poseCount: poses.length,
      override,
      firstPose: backendPoses[0] ?? poses[0] ?? null,
    };
  }, [backendPoses, override, panelCount, poses]);

  if (backendPoses.length > 0) {
    return (
      <group>
        {backendPoses.map((p) => (
          <mesh key={p.id} position={p.pos} rotation={p.rot} castShadow receiveShadow>
            <boxGeometry
              args={[p.lengthMeters, p.thicknessMeters, p.widthMeters]}
            />
            <meshStandardMaterial
              color="#1a1a3e"
              metalness={0.85}
              roughness={0.3}
              envMapIntensity={1.2}
            />
          </mesh>
        ))}
      </group>
    );
  }

  if (poses.length === 0) return null;

  return (
    <group>
      {poses.map((p) => (
        <mesh key={p.id} position={p.pos} rotation={p.rot} castShadow receiveShadow>
          <boxGeometry
            args={[panel.lengthMeters, panel.thicknessMeters, panel.widthMeters]}
          />
          <meshStandardMaterial
            color="#1a1a3e"
            metalness={0.85}
            roughness={0.3}
            envMapIntensity={1.2}
          />
        </mesh>
      ))}
    </group>
  );
}
