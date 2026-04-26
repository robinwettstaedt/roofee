import { Object3D, Vector3 } from "three";
import { WGS84_ELLIPSOID } from "3d-tiles-renderer/three";

export const DEFAULT_HOUSE_VIEW_HEIGHT_M = 180;
export const DEFAULT_HOUSE_VIEW_PITCH_DEG = 55;

export type CameraPose = {
  position: Vector3;
  target: Vector3;
  up: Vector3;
};

/**
 * Convert a (lat, lng, alt) WGS84 coordinate to ECEF Cartesian using the
 * renderer's ellipsoid (same one the tileset is positioned in).
 * Inputs are in degrees / meters.
 */
export function latLngToEcef(
  latDeg: number,
  lngDeg: number,
  altM = 0,
): Vector3 {
  const out = new Vector3();
  WGS84_ELLIPSOID.getCartographicToPosition(
    (latDeg * Math.PI) / 180,
    (lngDeg * Math.PI) / 180,
    altM,
    out,
  );
  return out;
}

/**
 * Compute a camera pose centered on the geocoded house: target at ground level,
 * camera offset to the south by `pitchDeg` from the local up axis at `heightM`
 * above the surface. The returned vectors are in the same ECEF frame as the
 * Google Photorealistic 3D Tileset.
 */
export function cameraPoseForHouse(
  latDeg: number,
  lngDeg: number,
  heightM: number = DEFAULT_HOUSE_VIEW_HEIGHT_M,
  pitchDeg: number = DEFAULT_HOUSE_VIEW_PITCH_DEG,
): CameraPose {
  const lat = (latDeg * Math.PI) / 180;
  const lng = (lngDeg * Math.PI) / 180;

  const target = new Vector3();
  WGS84_ELLIPSOID.getCartographicToPosition(lat, lng, 0, target);

  const east = new Vector3();
  const north = new Vector3();
  const up = new Vector3();
  WGS84_ELLIPSOID.getEastNorthUpAxes(lat, lng, east, north, up);

  const pitch = (pitchDeg * Math.PI) / 180;
  const distance = heightM;

  const offset = new Vector3()
    .copy(up)
    .multiplyScalar(distance * Math.cos(pitch))
    .addScaledVector(north, -distance * Math.sin(pitch));

  const position = new Vector3().addVectors(target, offset);
  return { position, target, up };
}

/**
 * Walks the click hit chain looking for the absolute URL that was used to load
 * the tile content. We tag scenes via the `load-model` event so leaves carry
 * `userData.tileContentUrl` for picks.
 */
export function pickTileContentUrl(obj: Object3D | null): string | null {
  let current: Object3D | null = obj;
  while (current) {
    const url = current.userData?.tileContentUrl;
    if (typeof url === "string" && url.length > 0) return url;
    current = current.parent;
  }
  return null;
}
