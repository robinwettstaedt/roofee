"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RoofAnalysis, RoofOutline } from "@/types/roof";

/**
 * Lets the user click the buildings they want to design panels for. Renders
 * the satellite image returned by /api/recommendations with each detected
 * roof outline as a clickable polygon overlay. Multi-select: click toggles.
 *
 * Each candidate gets its own hue from PALETTE so the user can tell them
 * apart at a glance ("I'll click the teal one"). Selected buildings flip to
 * signal-orange + a glow so they read as a different kind of thing on screen.
 * Vertices are RDP-simplified before render so polygons look smooth, not
 * grizzly from segmentation noise.
 */

const C = {
  ink: "24, 23, 21",
  signal: "232, 90, 44",
  paperDeep: "#ece8de",
  paper: "#f7f5f0",
} as const;

// Per-candidate palette. All cool / jewel tones — zero overlap with the
// signal-orange selected state, so flipping a candidate to selected reads
// as a real state change, not just "another colored polygon".
const PALETTE = [
  { name: "teal", rgb: "20, 168, 156" },
  { name: "indigo", rgb: "94, 123, 232" },
  { name: "sky", rgb: "43, 179, 224" },
  { name: "plum", rgb: "160, 94, 212" },
  { name: "emerald", rgb: "43, 184, 123" },
  { name: "violet", rgb: "118, 92, 224" },
] as const;

function colorFor(index: number): string {
  return PALETTE[index % PALETTE.length].rgb;
}

// Ramer–Douglas–Peucker line simplification. Used to clean up the noisy
// vertex output from YOLOv8 segmentation so polygons look smooth instead
// of grizzly. Epsilon controls how aggressively we drop near-collinear points.
function simplifyPath(
  points: number[][],
  epsilon: number,
): [number, number][] {
  const pairs: [number, number][] = points
    .filter((p) => p.length >= 2)
    .map((p) => [p[0], p[1]]);
  if (pairs.length < 4 || epsilon <= 0) return pairs;
  return rdp(pairs, epsilon);
}

function rdp(
  points: [number, number][],
  epsilon: number,
): [number, number][] {
  if (points.length < 3) return points;
  let dmax = 0;
  let index = 0;
  const end = points.length - 1;
  for (let i = 1; i < end; i++) {
    const d = perpDist(points[i], points[0], points[end]);
    if (d > dmax) {
      dmax = d;
      index = i;
    }
  }
  if (dmax > epsilon) {
    const left = rdp(points.slice(0, index + 1), epsilon);
    const right = rdp(points.slice(index), epsilon);
    return [...left.slice(0, -1), ...right];
  }
  return [points[0], points[end]];
}

function perpDist(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  if (dx === 0 && dy === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  const num = Math.abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]);
  return num / Math.hypot(dx, dy);
}

export function RoofPicker({
  roofAnalysis,
  address,
  onConfirm,
  onBack,
  loading,
  error,
}: {
  roofAnalysis: RoofAnalysis;
  address: string;
  onConfirm: (selectedIds: string[]) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}) {
  const outlines = roofAnalysis.roof_outlines;
  const imageUrl = roofAnalysis.satellite_image_url ?? null;

  // Rank once: largest * most-confident first. Indexes drive the "01", "02"
  // captions and the stagger animation, so the auto-suggested roof reads "01".
  const ranked = useMemo(() => rankOutlines(outlines), [outlines]);
  const outlinesById = useMemo(
    () => new Map(outlines.map((o) => [o.id, o])),
    [outlines],
  );

  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const didPreselect = useRef(false);

  // Adjacency tolerance scales with image — small bbox gaps from segmentation
  // imprecision (a few pixels between two row-house polygons that physically
  // share a wall) shouldn't disqualify them as "touching".
  const adjacencyThreshold = imgSize
    ? Math.max(imgSize.w, imgSize.h) * 0.025
    : 0;

  // Preselect the building under the geocoded pin (image center). If the
  // center falls inside a polygon, that's almost certainly the user's house;
  // otherwise pick the candidate whose centroid is closest. Far better than
  // "biggest building", which routinely picks a neighbour.
  useEffect(() => {
    if (didPreselect.current) return;
    if (!imgSize || outlines.length === 0) return;
    const id = pickInitialId(outlines, imgSize.w, imgSize.h);
    if (id) {
      didPreselect.current = true;
      window.setTimeout(() => setSelectedIds(new Set([id])), 0);
    }
  }, [imgSize, outlines]);

  function toggle(id: string) {
    setSelectedIds((prev) => {
      // Click an already-selected polygon → deselect it.
      if (prev.has(id)) {
        const next = new Set(prev);
        next.delete(id);
        return next;
      }

      // Empty → start the selection with this one.
      if (prev.size === 0) return new Set([id]);

      // We cap at two and require physical adjacency (touching/sharing a wall).
      // If the cap is reached or the click target isn't adjacent to *every*
      // currently selected polygon, replace the selection entirely — the user
      // is signalling "this one, not the other(s)", not "add to the group".
      const clicked = outlinesById.get(id);
      if (!clicked) return prev;

      if (prev.size >= 2) return new Set([id]);

      const allAdjacent = [...prev].every((sid) => {
        const sel = outlinesById.get(sid);
        return sel ? areAdjacent(sel, clicked, adjacencyThreshold) : false;
      });

      return allAdjacent ? new Set([...prev, id]) : new Set([id]);
    });
  }

  function handleImageLoad() {
    if (imgRef.current) {
      setImgSize({
        w: imgRef.current.naturalWidth,
        h: imgRef.current.naturalHeight,
      });
    }
  }

  const canConfirm = selectedIds.size > 0 && !loading;
  const anySelected = selectedIds.size > 0;

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
              We found {outlines.length} structure{outlines.length === 1 ? "" : "s"} from
              the satellite image. Click the home you want to design panels for.
              You can include a touching neighbour (e.g. a row-house wing) by
              clicking it as well.
            </p>
          </div>

          <div className="rise relative flex-1 overflow-hidden rounded-xl border border-ink/15 bg-paper-deep">
            {imageUrl ? (
              <div className="relative h-full w-full">
                <img
                  ref={imgRef}
                  src={imageUrl}
                  alt="Satellite imagery of the property"
                  onLoad={handleImageLoad}
                  className="absolute inset-0 h-full w-full object-contain"
                />
                {imgSize && (
                  <svg
                    viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
                    preserveAspectRatio="xMidYMid meet"
                    className="absolute inset-0 h-full w-full"
                    style={{ pointerEvents: "none" }}
                  >
                    <defs>
                      <style>{markupKeyframes}</style>
                    </defs>
                    {ranked.map((o, i) => {
                      const selected = selectedIds.has(o.id);
                      const hovered = hoveredId === o.id;
                      const dimmed = anySelected && !selected && !hovered;
                      return (
                        <Outline
                          key={o.id}
                          outline={o}
                          index={i}
                          color={colorFor(i)}
                          selected={selected}
                          hovered={hovered}
                          dimmed={dimmed}
                          imgWidth={imgSize.w}
                          onClick={() => toggle(o.id)}
                          onEnter={() => setHoveredId(o.id)}
                          onLeave={() =>
                            setHoveredId((cur) => (cur === o.id ? null : cur))
                          }
                        />
                      );
                    })}
                  </svg>
                )}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-[13px] text-dust">
                No satellite image available for this address.
              </div>
            )}
          </div>

          {error && (
            <p className="mt-4 text-[12px] text-signal">{error}</p>
          )}

          <footer className="mt-6 flex items-center justify-between">
            <p className="text-[12px] text-dust">
              {selectedIds.size === 0
                ? "Click buildings to select. Click again to deselect."
                : `${selectedIds.size} ${selectedIds.size === 1 ? "building" : "buildings"} selected`}
            </p>
            <button
              type="button"
              disabled={!canConfirm}
              onClick={() => onConfirm(Array.from(selectedIds))}
              className="inline-flex items-center gap-2 rounded-full bg-signal px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
            >
              {loading ? (
                <>
                  Analyzing roof…
                  <span
                    className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper"
                    aria-hidden
                  />
                </>
              ) : (
                <>
                  {selectedIds.size > 1 ? "Use these roofs" : "Use this roof"}
                  <span aria-hidden>→</span>
                </>
              )}
            </button>
          </footer>
        </div>
      </main>
    </div>
  );
}

function Outline({
  outline,
  index,
  color,
  selected,
  hovered,
  dimmed,
  imgWidth,
  onClick,
  onEnter,
  onLeave,
}: {
  outline: RoofOutline;
  index: number;
  color: string;
  selected: boolean;
  hovered: boolean;
  dimmed: boolean;
  imgWidth: number;
  onClick: () => void;
  onEnter: () => void;
  onLeave: () => void;
}) {
  const bb = outline.bounding_box_pixels;
  const w = bb.x_max - bb.x_min;
  const h = bb.y_max - bb.y_min;

  // Smooth out segmentation noise: epsilon scales with bbox so it works at
  // any image resolution. ~1.5% of the larger dimension drops jaggies without
  // chopping off real corners.
  const points = useMemo(() => {
    const eps = Math.max(w, h) * 0.015;
    return simplifyPath(outline.polygon_pixels, eps)
      .map(([x, y]) => `${x},${y}`)
      .join(" ");
  }, [outline.polygon_pixels, w, h]);

  // Polygon fill / stroke per state.
  let fill: string;
  let stroke: string;
  let strokeWidth: number;
  let polyFilter: string | undefined;

  // Pattern: candidates are OUTLINED (stroke only). Selected is the only one
  // that's FILLED. This avoids low-alpha fills bleeding the underlying roof
  // color through (reddish tiles can make a cool-hue overlay read warm), and
  // makes the "you picked this" state unambiguous regardless of imagery.
  if (selected) {
    fill = `rgba(${C.signal}, 0.55)`;
    stroke = `rgb(${C.signal})`;
    strokeWidth = 4.5;
    polyFilter = `drop-shadow(0 0 3px rgba(${C.signal}, 0.95)) drop-shadow(0 0 14px rgba(${C.signal}, 0.55))`;
  } else if (hovered) {
    fill = `rgba(${color}, 0.22)`;
    stroke = `rgb(${color})`;
    strokeWidth = 3;
  } else if (dimmed) {
    fill = "transparent";
    stroke = `rgba(${color}, 0.55)`;
    strokeWidth = 1.5;
  } else {
    fill = "transparent";
    stroke = `rgb(${color})`;
    strokeWidth = 2.25;
  }

  const labelText = String(index + 1).padStart(2, "0");

  // Caption sizing: image-pixel units (SVG viewBox). Scale with image width so
  // it reads at a similar physical size across image resolutions.
  const captionFontSize = Math.max(10, imgWidth * 0.014);
  const captionPad = captionFontSize * 0.5;
  const captionH = captionFontSize * 1.7;
  const captionW = captionFontSize * 2.4;
  const captionX = bb.x_min;
  const captionY = bb.y_min - captionH - 4;

  // Pill only shows while hovered and not yet selected — once selected, the
  // orange polygon is enough; no label needed.
  const showCaption = hovered && !selected;

  const groupStyle: React.CSSProperties = {
    pointerEvents: "auto",
    cursor: "pointer",
  };

  return (
    <g
      style={groupStyle}
      onClick={onClick}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {/* Hit-area: bbox so small polygons remain clickable */}
      <rect
        x={bb.x_min}
        y={bb.y_min}
        width={w}
        height={h}
        fill="transparent"
      />

      {/* Polygon fill + outline */}
      <polygon
        points={points}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeLinecap="round"
        style={{
          transition:
            "fill 160ms ease, stroke 160ms ease, stroke-width 160ms ease, filter 200ms ease",
          filter: polyFilter,
        }}
      />

      {/* Index pill — only on hover for unselected candidates */}
      {showCaption && (
        <g
          style={{
            animation: "roofee-cap-in 180ms ease-out both",
          }}
        >
          <rect
            x={captionX}
            y={captionY}
            width={captionW}
            height={captionH}
            rx={2}
            ry={2}
            fill={`rgb(${color})`}
            stroke={`rgb(${color})`}
            strokeWidth={1}
          />
          <text
            x={captionX + captionPad}
            y={captionY + captionH / 2}
            dominantBaseline="middle"
            fontFamily="var(--font-mono), ui-monospace, monospace"
            fontSize={captionFontSize}
            letterSpacing="0.08em"
            fill={C.paper}
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {labelText}
          </text>
        </g>
      )}
    </g>
  );
}

// CSS injected once into the SVG <defs> for caption mount.
const markupKeyframes = `
  @keyframes roofee-cap-in {
    from { opacity: 0; transform: translateY(2px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;

function rankOutlines(outlines: RoofOutline[]): RoofOutline[] {
  // Largest * most-confident first. Confidence may be null → treat as 0.5.
  return [...outlines].sort((a, b) => {
    const score = (o: RoofOutline) => o.area_pixels * (o.confidence ?? 0.5);
    return score(b) - score(a);
  });
}

function pickInitialId(
  outlines: RoofOutline[],
  imgW: number,
  imgH: number,
): string | null {
  if (outlines.length === 0) return null;
  const cx = imgW / 2;
  const cy = imgH / 2;
  // 1. Address pin lands inside one of the polygons → that's the house.
  for (const o of outlines) {
    if (pointInPolygon(cx, cy, o.polygon_pixels)) return o.id;
  }
  // 2. Otherwise pick the candidate whose centroid is closest to the pin.
  let bestId: string | null = null;
  let bestDist = Infinity;
  for (const o of outlines) {
    const bb = o.bounding_box_pixels;
    const ox = (bb.x_min + bb.x_max) / 2;
    const oy = (bb.y_min + bb.y_max) / 2;
    const d = Math.hypot(ox - cx, oy - cy);
    if (d < bestDist) {
      bestDist = d;
      bestId = o.id;
    }
  }
  return bestId;
}

function areAdjacent(
  a: RoofOutline,
  b: RoofOutline,
  threshold: number,
): boolean {
  // Bounding-box proximity: compute the gap on each axis. If a bbox is to the
  // left of the other, gapX = leftEdgeOfRight - rightEdgeOfLeft; if they
  // overlap on that axis, gap is 0. Two buildings count as adjacent when both
  // axis gaps are within the tolerance — i.e. they overlap or are separated
  // only by segmentation noise, not by a street/garden.
  const ax = a.bounding_box_pixels;
  const bx = b.bounding_box_pixels;
  const gapX = Math.max(0, Math.max(ax.x_min, bx.x_min) - Math.min(ax.x_max, bx.x_max));
  const gapY = Math.max(0, Math.max(ax.y_min, bx.y_min) - Math.min(ax.y_max, bx.y_max));
  return Math.max(gapX, gapY) <= threshold;
}

function pointInPolygon(x: number, y: number, polygon: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0];
    const yi = polygon[i][1];
    const xj = polygon[j][0];
    const yj = polygon[j][1];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}
