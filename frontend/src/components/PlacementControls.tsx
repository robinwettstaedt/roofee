"use client";
import { useState } from "react";
import type { PlacementOverride } from "./RoofPlacedPanels";

const RANGES = {
  cx: { min: -30, max: 30, step: 0.5 },
  cy: { min: 0, max: 15, step: 0.1 },
  cz: { min: -30, max: 30, step: 0.5 },
  tilt: { min: 0, max: 60, step: 1 },
  az: { min: 0, max: 359, step: 5 },
  yaw: { min: -180, max: 180, step: 1 },
  cols: { min: 1, max: 12, step: 1 },
};

function Row({
  label,
  value,
  onChange,
  range,
  unit,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  range: { min: number; max: number; step: number };
  unit?: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-14 shrink-0 text-zinc-500">{label}</span>
      <input
        type="range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-emerald-500"
      />
      <input
        type="number"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-16 rounded border border-zinc-200 px-1.5 py-0.5 text-right tabular-nums"
      />
      {unit && <span className="w-3 text-zinc-400">{unit}</span>}
    </div>
  );
}

export function PlacementControls({
  value,
  onChange,
  onReset,
}: {
  value: PlacementOverride;
  onChange: (v: PlacementOverride) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);

  const update = (patch: Partial<PlacementOverride>) =>
    onChange({ ...value, ...patch });

  const copyValues = async () => {
    const snippet = `const CENTER_HOUSE_PLACEMENT: PlacementOverride = {
  center: [${value.center[0]}, ${value.center[1]}, ${value.center[2]}],
  tiltDeg: ${value.tiltDeg},
  azimuthDeg: ${value.azimuthDeg},
  yawDeg: ${value.yawDeg ?? 0},
  cols: ${value.cols ?? 6},
};`;
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div className="pointer-events-auto absolute right-4 top-4 z-20 w-72 rounded-xl border border-zinc-200 bg-white/95 shadow-lg backdrop-blur">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-zinc-800"
      >
        <span>Panel placement</span>
        <span className="text-zinc-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-zinc-100 px-3 py-3">
          <Row
            label="X"
            value={value.center[0]}
            onChange={(x) =>
              update({ center: [x, value.center[1], value.center[2]] })
            }
            range={RANGES.cx}
            unit="m"
          />
          <Row
            label="Y"
            value={value.center[1]}
            onChange={(y) =>
              update({ center: [value.center[0], y, value.center[2]] })
            }
            range={RANGES.cy}
            unit="m"
          />
          <Row
            label="Z"
            value={value.center[2]}
            onChange={(z) =>
              update({ center: [value.center[0], value.center[1], z] })
            }
            range={RANGES.cz}
            unit="m"
          />
          <Row
            label="Tilt"
            value={value.tiltDeg}
            onChange={(tiltDeg) => update({ tiltDeg })}
            range={RANGES.tilt}
            unit="°"
          />
          <Row
            label="Azimuth"
            value={value.azimuthDeg}
            onChange={(azimuthDeg) => update({ azimuthDeg })}
            range={RANGES.az}
            unit="°"
          />
          <Row
            label="Yaw"
            value={value.yawDeg ?? 0}
            onChange={(yawDeg) => update({ yawDeg })}
            range={RANGES.yaw}
            unit="°"
          />
          <Row
            label="Cols"
            value={value.cols ?? 6}
            onChange={(cols) => update({ cols })}
            range={RANGES.cols}
          />
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={copyValues}
              className="flex-1 rounded-md bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-600"
            >
              {copied ? "✓ Copied" : "Copy snippet"}
            </button>
            <button
              type="button"
              onClick={onReset}
              className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs text-zinc-700 transition hover:bg-zinc-50"
            >
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
