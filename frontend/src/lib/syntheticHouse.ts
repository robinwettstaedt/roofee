import * as THREE from "three";

// Wall height used for the schematic blueprint house. The backend doesn't
// expose eave / building height, so this is a sensible residential default.
export const WALL_HEIGHT_M = 6;

// Tiny vertical offsets to keep coplanar overlays from z-fighting.
export const ROOF_OVERLAY_LIFT_M = 0.04;
export const REMOVED_OVERLAY_LIFT_M = 0.02;

// Backend polygons are 2D `[x, z]` floats in MODEL METERS (x east-ish, z
// south-ish in the Y-up world frame). THREE.Shape is 2D in (x, y); when we
// later rotate the resulting mesh by -π/2 around X to lay it flat, the
// shape's y becomes world -z, so we negate the input z to get the right
// orientation.
export function modelPolygonToShape(points: number[][]): THREE.Shape | null {
  if (points.length < 3) return null;
  const shape = new THREE.Shape();
  shape.moveTo(points[0][0], -points[0][1]);
  for (let i = 1; i < points.length; i++) {
    shape.lineTo(points[i][0], -points[i][1]);
  }
  shape.closePath();
  return shape;
}

export function polygonCentroidXZ(points: number[][]): [number, number] {
  if (points.length === 0) return [0, 0];
  let sx = 0;
  let sz = 0;
  for (const p of points) {
    sx += p[0];
    sz += p[1];
  }
  return [sx / points.length, sz / points.length];
}

// Combines all polygons into a single bounding box in model meters so the
// synthetic root can be re-centered onto the GLB's center for consistent
// camera framing.
export function combinedBoundingBox(polygons: number[][][]): THREE.Box3 {
  const box = new THREE.Box3();
  for (const polygon of polygons) {
    for (const point of polygon) {
      box.expandByPoint(new THREE.Vector3(point[0], 0, point[1]));
    }
  }
  return box;
}

export const degToRad = THREE.MathUtils.degToRad;
