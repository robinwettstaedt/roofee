"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RoofAnalysis, RoofOutline } from "@/types/roof";

/**
 * Lets the user click the building they want to design panels for. Renders
 * the satellite image returned by /api/recommendations with each detected
 * roof outline as a clickable polygon overlay. Selection is single-roof for
 * V1 — clicking a different polygon replaces the previous selection.
 */
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

  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Pick the largest, most-confident outline as the default suggestion.
  const suggestedOutline = useMemo(() => suggestPrimary(outlines), [outlines]);

  useEffect(() => {
    if (suggestedOutline && selectedIds.size === 0) {
      setSelectedIds(new Set([suggestedOutline.id]));
    }
  }, [suggestedOutline, selectedIds.size]);

  function toggle(id: string) {
    setSelectedIds((prev) => {
      // V1: single-select. Click same → keep. Click other → replace.
      const next = new Set<string>();
      if (!prev.has(id)) next.add(id);
      else next.add(id);
      return next;
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
                    {outlines.map((o) => {
                      const selected = selectedIds.has(o.id);
                      return (
                        <Outline
                          key={o.id}
                          outline={o}
                          selected={selected}
                          onClick={() => toggle(o.id)}
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
                ? "Click a building to select."
                : `${selectedIds.size} selected${
                    selectedIds.size > 1 ? " — must be touching" : ""
                  }`}
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
                  Use this roof
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
  selected,
  onClick,
}: {
  outline: RoofOutline;
  selected: boolean;
  onClick: () => void;
}) {
  const points = outline.polygon_pixels
    .map(([x, y]) => `${x},${y}`)
    .join(" ");

  // Stroke + fill scale up when selected.
  const fill = selected ? "rgba(232, 90, 44, 0.32)" : "rgba(24, 23, 21, 0.12)";
  const stroke = selected ? "#e85a2c" : "rgba(24, 23, 21, 0.55)";
  const strokeWidth = selected ? 4 : 2;

  return (
    <g style={{ pointerEvents: "auto", cursor: "pointer" }} onClick={onClick}>
      {/* Invisible expanded hit-area: the bounding box, so small polygons stay clickable */}
      <rect
        x={outline.bounding_box_pixels.x_min}
        y={outline.bounding_box_pixels.y_min}
        width={outline.bounding_box_pixels.x_max - outline.bounding_box_pixels.x_min}
        height={
          outline.bounding_box_pixels.y_max - outline.bounding_box_pixels.y_min
        }
        fill="transparent"
      />
      <polygon
        points={points}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        style={{ transition: "fill 160ms ease, stroke 160ms ease" }}
      />
    </g>
  );
}

function suggestPrimary(outlines: RoofOutline[]): RoofOutline | null {
  if (outlines.length === 0) return null;
  // Prefer the outline with highest (area * confidence). Confidence may be null.
  return [...outlines].sort((a, b) => {
    const score = (o: RoofOutline) =>
      o.area_pixels * (o.confidence ?? 0.5);
    return score(b) - score(a);
  })[0];
}
