"use client";
import { Edges } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type {
  RoofGeometryAnalysisResponse,
  RoofPlaneGeometry,
  UsableRoofRegion,
  RemovedRoofArea,
} from "@/types/roof";
import {
  WALL_HEIGHT_M,
  ROOF_OVERLAY_LIFT_M,
  REMOVED_OVERLAY_LIFT_M,
  modelPolygonToShape,
  polygonCentroidXZ,
  combinedBoundingBox,
  degToRad,
} from "@/lib/syntheticHouse";

const PAPER = "#fafaf6";
const INK = "#1a1a1a";
const SIGNAL = "#ff5a1f";
const AMBER = "#a16b1a";

const FLAT_ROTATION: [number, number, number] = [-Math.PI / 2, 0, 0];

function planeIndex(planes: RoofPlaneGeometry[]): Map<string, RoofPlaneGeometry> {
  return new Map(planes.map((plane) => [plane.id, plane]));
}

function tiltedTransform(plane: RoofPlaneGeometry): {
  position: [number, number, number];
  rotation: [number, number, number];
  centroid: [number, number];
} {
  const [cx, cz] = polygonCentroidXZ(plane.footprint_polygon);
  return {
    position: [cx, WALL_HEIGHT_M, cz],
    rotation: [0, -degToRad(plane.azimuth_degrees), 0],
    centroid: [cx, cz],
  };
}

function PlaneSlab({ plane }: { plane: RoofPlaneGeometry }) {
  const shape = useMemo(
    () => modelPolygonToShape(plane.footprint_polygon),
    [plane.footprint_polygon],
  );
  const transform = useMemo(() => tiltedTransform(plane), [plane]);
  if (!shape) return null;
  const tiltRad = degToRad(plane.tilt_degrees);
  const [cx, cz] = transform.centroid;
  return (
    <group position={transform.position} rotation={transform.rotation}>
      <group rotation={[tiltRad, 0, 0]}>
        <mesh
          position={[-cx, 0, -cz]}
          rotation={FLAT_ROTATION}
          castShadow
          receiveShadow
        >
          <shapeGeometry args={[shape]} />
          <meshStandardMaterial
            color={PAPER}
            roughness={0.95}
            metalness={0}
            side={THREE.DoubleSide}
          />
          <Edges color={INK} threshold={1} lineWidth={1} />
        </mesh>
      </group>
    </group>
  );
}

function RegionOverlay({
  polygon,
  plane,
  color,
  liftM,
  opacity,
}: {
  polygon: number[][];
  plane: RoofPlaneGeometry;
  color: string;
  liftM: number;
  opacity: number;
}) {
  const shape = useMemo(() => modelPolygonToShape(polygon), [polygon]);
  const transform = useMemo(() => tiltedTransform(plane), [plane]);
  if (!shape) return null;
  const tiltRad = degToRad(plane.tilt_degrees);
  const [cx, cz] = transform.centroid;
  return (
    <group position={transform.position} rotation={transform.rotation}>
      <group rotation={[tiltRad, 0, 0]}>
        <mesh
          position={[-cx, liftM, -cz]}
          rotation={FLAT_ROTATION}
          renderOrder={2}
        >
          <shapeGeometry args={[shape]} />
          <meshStandardMaterial
            color={color}
            roughness={0.9}
            metalness={0}
            transparent
            opacity={opacity}
            side={THREE.DoubleSide}
            depthWrite={false}
            polygonOffset
            polygonOffsetFactor={-2}
            polygonOffsetUnits={-2}
          />
        </mesh>
      </group>
    </group>
  );
}

function BuildingBody({ polygon }: { polygon: number[][] }) {
  const shape = useMemo(() => modelPolygonToShape(polygon), [polygon]);
  const geometry = useMemo(() => {
    if (!shape) return null;
    return new THREE.ExtrudeGeometry(shape, {
      depth: WALL_HEIGHT_M,
      bevelEnabled: false,
    });
  }, [shape]);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} rotation={FLAT_ROTATION} castShadow receiveShadow>
      <meshStandardMaterial color={PAPER} roughness={0.95} metalness={0} />
      <Edges color={INK} threshold={15} lineWidth={1} />
    </mesh>
  );
}

export function SyntheticHouse({
  geometry,
  onReady,
}: {
  geometry: RoofGeometryAnalysisResponse;
  onReady?: (root: THREE.Object3D) => void;
}) {
  const groupRef = useRef<THREE.Group | null>(null);

  // Pre-center the synthetic root on the polygon bbox so it lines up roughly
  // with where the GLB lives after its own re-centering in House.tsx.
  const recenterOffset = useMemo<[number, number, number]>(() => {
    const all: number[][][] = [
      ...geometry.mapped_roof_outlines.map((o) => o.model_polygon),
      ...geometry.roof_planes.map((p) => p.footprint_polygon),
    ];
    if (all.length === 0) return [0, 0, 0];
    const box = combinedBoundingBox(all);
    const center = new THREE.Vector3();
    box.getCenter(center);
    return [-center.x, 0, -center.z];
  }, [geometry]);

  const planeById = useMemo(() => planeIndex(geometry.roof_planes), [
    geometry.roof_planes,
  ]);

  useEffect(() => {
    if (!groupRef.current) return;
    onReady?.(groupRef.current);
    if (typeof window !== "undefined") {
      const w = window as unknown as { __roofee?: Record<string, unknown> };
      w.__roofee = {
        ...(w.__roofee ?? {}),
        synthetic: true,
        syntheticPlaneCount: geometry.roof_planes.length,
      };
    }
  }, [onReady, geometry]);

  return (
    <group ref={groupRef} position={recenterOffset}>
      {geometry.mapped_roof_outlines.map((outline) => (
        <BuildingBody key={outline.id} polygon={outline.model_polygon} />
      ))}

      {geometry.roof_planes.map((plane) => (
        <PlaneSlab key={plane.id} plane={plane} />
      ))}

      {geometry.usable_regions.map((region: UsableRoofRegion) => {
        const plane = planeById.get(region.roof_plane_id);
        if (!plane) return null;
        return (
          <RegionOverlay
            key={region.id}
            polygon={region.polygon}
            plane={plane}
            color={SIGNAL}
            liftM={ROOF_OVERLAY_LIFT_M}
            opacity={0.7}
          />
        );
      })}

      {geometry.removed_areas.map((area: RemovedRoofArea) => {
        const plane = planeById.get(area.roof_plane_id);
        if (!plane) return null;
        return (
          <RegionOverlay
            key={area.id}
            polygon={area.polygon}
            plane={plane}
            color={AMBER}
            liftM={REMOVED_OVERLAY_LIFT_M}
            opacity={0.4}
          />
        );
      })}
    </group>
  );
}
