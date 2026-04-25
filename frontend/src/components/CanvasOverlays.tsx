"use client";
import { useState } from "react";
import { Eyebrow } from "./primitives/Eyebrow";

type Lens = "panels" | "obstructions" | "irradiance" | "measure";

export type Note = {
  id: string;
  x: number; // 0..1 within canvas
  y: number;
  text: string;
};

export function CanvasOverlays({
  hour,
  onHour,
  lens,
  onLens,
  notes,
  onAddNote,
  onRemoveNote,
  freeRoofM2 = 56,
  lat = 52.4985,
  lng = 13.3877,
}: {
  hour: number;
  onHour: (h: number) => void;
  lens: Lens;
  onLens: (l: Lens) => void;
  notes: Note[];
  onAddNote: (n: Note) => void;
  onRemoveNote: (id: string) => void;
  freeRoofM2?: number;
  lat?: number;
  lng?: number;
}) {
  const [pinning, setPinning] = useState(false);

  function handleCanvasClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!pinning) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const text = window.prompt("Install note (visible to crew):") ?? "";
    if (text.trim()) {
      onAddNote({
        id: `n_${Date.now()}`,
        x,
        y,
        text: text.trim(),
      });
    }
    setPinning(false);
  }

  return (
    <div
      className={`pointer-events-none absolute inset-0 ${pinning ? "cursor-crosshair pointer-events-auto" : ""}`}
      onClick={handleCanvasClick}
    >
      {/* TL: lens toggles + sun-path */}
      <div className="pointer-events-auto absolute left-4 top-4 flex flex-col gap-3">
        <div className="overlay-surface flex items-stretch">
          {(["panels", "obstructions", "irradiance", "measure"] as Lens[]).map(
            (l) => (
              <button
                key={l}
                type="button"
                onClick={() => onLens(l)}
                aria-pressed={lens === l}
                className={`border-r border-ink/10 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] transition last:border-r-0 ${
                  lens === l
                    ? "bg-ink text-paper"
                    : "text-dust hover:text-ink"
                }`}
              >
                {l}
              </button>
            ),
          )}
        </div>

        <div className="overlay-surface flex w-[260px] items-center gap-3 px-3 py-2">
          <Eyebrow>Sun</Eyebrow>
          <input
            type="range"
            min={5}
            max={21}
            step={0.25}
            value={hour}
            onChange={(e) => onHour(Number(e.target.value))}
            className="flex-1"
            aria-label="Sun position"
          />
          <span className="font-mono num text-[11px] text-ink">
            {String(Math.floor(hour)).padStart(2, "0")}:
            {String(Math.round((hour % 1) * 60)).padStart(2, "0")}
          </span>
        </div>
      </div>

      {/* BL: annotation tool */}
      <div className="pointer-events-auto absolute bottom-4 left-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setPinning((p) => !p)}
          aria-pressed={pinning}
          className={`overlay-surface flex items-center gap-2 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] transition ${
            pinning ? "bg-signal text-paper" : "text-ink-soft hover:text-ink"
          }`}
        >
          <span aria-hidden>📍</span>
          {pinning ? "Click on canvas" : "Pin install note"}
        </button>
        {notes.length > 0 && (
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-dust">
            {notes.length} note{notes.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {/* BR: coordinate readout */}
      <div className="pointer-events-auto absolute bottom-4 right-4 overlay-surface px-3 py-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust">
          Site readout
        </div>
        <div className="mt-1 grid grid-cols-2 gap-x-5 gap-y-0.5 text-[11px]">
          <span className="text-dust">lat</span>
          <span className="font-mono num text-ink">{lat.toFixed(5)}°</span>
          <span className="text-dust">lng</span>
          <span className="font-mono num text-ink">{lng.toFixed(5)}°</span>
          <span className="text-dust">free roof</span>
          <span className="font-mono num text-ink">{freeRoofM2.toFixed(1)} m²</span>
        </div>
      </div>

      {/* Pinned notes */}
      {notes.map((n) => (
        <div
          key={n.id}
          className="pointer-events-auto absolute -translate-x-1/2 -translate-y-full"
          style={{ left: `${n.x * 100}%`, top: `${n.y * 100}%` }}
        >
          <div className="group relative">
            <button
              type="button"
              onClick={() => onRemoveNote(n.id)}
              className="block h-6 w-6 rounded-full border-2 border-paper bg-signal text-[12px] leading-none text-paper shadow-md"
              aria-label="Remove note"
            >
              ×
            </button>
            <div className="invisible absolute bottom-full left-1/2 mb-1 w-max max-w-[220px] -translate-x-1/2 overlay-surface px-2 py-1 text-[11px] text-ink-soft shadow group-hover:visible">
              {n.text}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
