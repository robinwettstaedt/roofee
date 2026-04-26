"use client";
import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

type UpAxis = "x" | "y" | "z";
type OrientationMode = UpAxis | "geospatial";

declare global {
  interface Window {
    __roofee?: Record<string, unknown>;
  }
}

function detectUpAxis(size: THREE.Vector3): UpAxis {
  if (size.y <= size.x && size.y <= size.z) return "y";
  if (size.z <= size.x && size.z <= size.y) return "z";
  return "x";
}

function isGeospatialFrame(center: THREE.Vector3): boolean {
  return center.length() > 100_000;
}

function robustFloorY(root: THREE.Object3D): number | null {
  root.updateMatrixWorld(true);
  const values: number[] = [];
  const point = new THREE.Vector3();
  root.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    const position = child.geometry.getAttribute("position");
    if (!position) return;
    const stride = Math.max(1, Math.floor(position.count / 8000));
    for (let index = 0; index < position.count; index += stride) {
      point.fromBufferAttribute(position, index).applyMatrix4(child.matrixWorld);
      if (Number.isFinite(point.y)) values.push(point.y);
    }
  });
  if (values.length === 0) return null;
  values.sort((a, b) => a - b);
  return values[Math.floor(values.length * 0.08)] ?? values[0];
}

export function House({
  url,
  forceUpAxis,
  onReady,
}: {
  url: string;
  forceUpAxis?: UpAxis;
  onReady?: (root: THREE.Object3D) => void;
}) {
  const { scene } = useGLTF(url);

  const oriented = useMemo(() => {
    const root = scene.clone(true);

    const rawBox = new THREE.Box3().setFromObject(root);
    const rawSize = new THREE.Vector3();
    rawBox.getSize(rawSize);
    const rawCenter = new THREE.Vector3();
    rawBox.getCenter(rawCenter);
    const orientationMode: OrientationMode =
      !forceUpAxis && isGeospatialFrame(rawCenter)
        ? "geospatial"
        : forceUpAxis ?? detectUpAxis(rawSize);

    const wrapper = new THREE.Group();
    wrapper.add(root);

    if (orientationMode === "geospatial") {
      const localUp = rawCenter.clone().normalize();
      wrapper.quaternion.copy(
        new THREE.Quaternion().setFromUnitVectors(localUp, new THREE.Vector3(0, 1, 0)),
      );
    } else if (orientationMode === "z") wrapper.rotateX(-Math.PI / 2);
    else if (orientationMode === "x") wrapper.rotateZ(Math.PI / 2);

    wrapper.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(wrapper);
    const center = new THREE.Vector3();
    box.getCenter(center);
    const floorY = robustFloorY(wrapper) ?? box.min.y;
    wrapper.position.set(-center.x, -floorY, -center.z);

    wrapper.userData.roofeeUpAxis = orientationMode;
    wrapper.userData.roofeeRawSize = rawSize.toArray();
    wrapper.userData.roofeeRawCenter = rawCenter.toArray();
    wrapper.userData.roofeeFloorY = floorY;
    wrapper.userData.roofeeModelRoot = root;
    return wrapper;
  }, [scene, forceUpAxis]);

  useEffect(() => {
    onReady?.(oriented);
  }, [oriented, onReady]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const finalBox = new THREE.Box3().setFromObject(oriented);
    const finalSize = new THREE.Vector3();
    finalBox.getSize(finalSize);
    const finalCenter = new THREE.Vector3();
    finalBox.getCenter(finalCenter);
    const rawSize = oriented.userData.roofeeRawSize as number[] | undefined;
    const upAxis = oriented.userData.roofeeUpAxis as OrientationMode | undefined;
    const rawCenter = oriented.userData.roofeeRawCenter as number[] | undefined;
    const floorY = oriented.userData.roofeeFloorY as number | undefined;
    console.info(
      `[House] up=${upAxis ?? "?"} raw=${(rawSize ?? []).map((n) => n.toFixed(2)).join(",")} rawCenter=${(rawCenter ?? []).map((n) => n.toFixed(2)).join(",")} floorY=${floorY?.toFixed(2) ?? "?"} final=${finalSize.toArray().map((n) => n.toFixed(2)).join(",")} center=${finalCenter.toArray().map((n) => n.toFixed(2)).join(",")} ymax=${finalBox.max.y.toFixed(2)}`,
    );
    window.__roofee = {
      upAxis,
      bbox: {
        min: finalBox.min.toArray(),
        max: finalBox.max.toArray(),
        size: finalSize.toArray(),
        center: finalCenter.toArray(),
      },
      houseRoot: oriented,
    };
  }, [oriented]);

  return <primitive object={oriented} />;
}
