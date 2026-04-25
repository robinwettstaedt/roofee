"use client";
import type { Variant, VariantId } from "@/lib/variants";

export function VariantTabs({
  variants,
  activeId,
  onSelect,
}: {
  variants: Variant[];
  activeId: VariantId;
  onSelect: (id: VariantId) => void;
}) {
  return (
    <div className="flex items-stretch gap-0 border-x border-ink/15">
      {variants.map((v) => {
        const active = v.id === activeId;
        return (
          <button
            key={v.id}
            type="button"
            onClick={() => onSelect(v.id)}
            className={`group relative flex flex-col items-start gap-0.5 border-r border-ink/15 px-4 py-2 text-left transition last:border-r-0 ${
              active ? "bg-paper" : "bg-paper-deep/30 hover:bg-paper"
            }`}
          >
            <span
              className={`font-mono text-[10px] uppercase tracking-[0.18em] ${
                active ? "text-signal" : "text-dust"
              }`}
            >
              {v.label}
            </span>
            <span
              className={`num text-[15px] font-medium leading-none ${
                active ? "text-ink" : "text-ink-soft"
              }`}
            >
              {v.design.pv.kwp} kWp
            </span>
            {active && (
              <span className="draw-underline absolute -bottom-px left-0 right-0 h-[2px] bg-signal" />
            )}
          </button>
        );
      })}
    </div>
  );
}
