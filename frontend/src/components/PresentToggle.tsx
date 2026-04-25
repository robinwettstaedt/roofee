"use client";

export function PresentToggle({
  mode,
  onToggle,
}: {
  mode: "edit" | "present";
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={mode === "present"}
      className={`flex items-center gap-2 border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em] transition ${
        mode === "present"
          ? "border-signal bg-signal text-paper"
          : "border-ink/25 text-ink-soft hover:border-ink hover:text-ink"
      }`}
    >
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          mode === "present" ? "bg-paper" : "bg-signal"
        }`}
      />
      {mode === "present" ? "Presenting" : "Present"}
    </button>
  );
}
