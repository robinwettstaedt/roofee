"use client";
import { useGLTF } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

type UpAxis = "x" | "y" | "z";

function detectUpAxis(size: THREE.Vector3): UpAxis {
  if (size.y <= size.x && size.y <= size.z) return "y";
  if (size.z <= size.x && size.z <= size.y) return "z";
  return "x";
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
    const upAxis = forceUpAxis ?? detectUpAxis(rawSize);

    const wrapper = new THREE.Group();
    wrapper.add(root);

    if (upAxis === "z") wrapper.rotateX(-Math.PI / 2);
    else if (upAxis === "x") wrapper.rotateZ(Math.PI / 2);

    wrapper.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(wrapper);
    const center = new THREE.Vector3();
    box.getCenter(center);
    wrapper.position.set(-center.x, -box.min.y, -center.z);

    if (typeof window !== "undefined") {
      const finalBox = new THREE.Box3().setFromObject(wrapper);
      const finalSize = new THREE.Vector3();
      finalBox.getSize(finalSize);
      const finalCenter = new THREE.Vector3();
      finalBox.getCenter(finalCenter);
      console.info(
        `[House] up=${upAxis} raw=${rawSize.toArray().map((n) => n.toFixed(2)).join(",")} final=${finalSize.toArray().map((n) => n.toFixed(2)).join(",")} center=${finalCenter.toArray().map((n) => n.toFixed(2)).join(",")} ymax=${finalBox.max.y.toFixed(2)}`,
      );
      // expose for debugging via Playwright
      (window as unknown as { __roofee?: Record<string, unknown> }).__roofee = {
        upAxis,
        bbox: {
          min: finalBox.min.toArray(),
          max: finalBox.max.toArray(),
          size: finalSize.toArray(),
          center: finalCenter.toArray(),
        },
        houseRoot: wrapper,
      };
    }

    return wrapper;
  }, [scene, forceUpAxis]);

  useEffect(() => {
    onReady?.(oriented);
  }, [oriented, onReady]);

  return <primitive object={oriented} />;
}
