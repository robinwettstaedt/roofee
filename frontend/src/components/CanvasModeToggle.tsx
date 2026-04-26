"use client";

export type CanvasMode = "real" | "synthetic";

export function CanvasModeToggle({
  mode,
  onChange,
  disabled,
}: {
  mode: CanvasMode;
  onChange: (mode: CanvasMode) => void;
  disabled?: boolean;
}) {
  const baseChip =
    "border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em] transition";
  return (
    <div
      className="flex"
      role="group"
      aria-label="Canvas view"
      title={disabled ? "Calculating geometry…" : undefined}
    >
      <button
        type="button"
        onClick={() => !disabled && onChange("real")}
        aria-pressed={mode === "real"}
        disabled={disabled}
        className={`${baseChip} ${
          mode === "real"
            ? "border-ink bg-ink text-paper"
            : "border-ink/25 text-ink-soft hover:border-ink hover:text-ink"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        Real
      </button>
      <button
        type="button"
        onClick={() => !disabled && onChange("synthetic")}
        aria-pressed={mode === "synthetic"}
        disabled={disabled}
        className={`${baseChip} -ml-px ${
          mode === "synthetic"
            ? "border-signal bg-signal text-paper"
            : "border-ink/25 text-ink-soft hover:border-ink hover:text-ink"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        Blueprint
      </button>
    </div>
  );
}
