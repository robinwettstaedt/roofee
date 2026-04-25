"use client";
import { useEffect, useState } from "react";

const STEPS = [
  "Fetching satellite imagery",
  "Reading roof geometry from 3D tiles",
  "Modelling sun exposure across 365 days",
  "Detecting obstructions — chimneys, skylights, vents",
  "Matching against 1,593 similar German homes",
  "Selecting components from Reonic catalog",
  "Sizing battery for evening self-consumption",
  "Composing the bill of materials",
];

export function ProcessingNarrative({ onDone }: { onDone: () => void }) {
  const [doneCount, setDoneCount] = useState(0);
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    if (doneCount >= STEPS.length) {
      const t = setTimeout(() => {
        setFadingOut(true);
        const t2 = setTimeout(onDone, 320);
        return () => clearTimeout(t2);
      }, 280);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setDoneCount((c) => c + 1), 540);
    return () => clearTimeout(t);
  }, [doneCount, onDone]);

  return (
    <div
      className={`fixed inset-0 z-50 grid place-items-center bg-paper/95 backdrop-blur-md transition-opacity duration-300 ${
        fadingOut ? "opacity-0" : "opacity-100"
      }`}
    >
      <div className="w-full max-w-[560px] px-8">
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-signal">
          {String(Math.min(doneCount + 1, STEPS.length)).padStart(2, "0")} /{" "}
          {String(STEPS.length).padStart(2, "0")} · Designing
        </p>
        <h2 className="mt-3 text-[28px] font-medium leading-tight tracking-tight text-ink">
          Reading your roof…
        </h2>

        <ul className="mt-8 space-y-3">
          {STEPS.map((s, i) => {
            const done = i < doneCount;
            const active = i === doneCount;
            return (
              <li
                key={s}
                className={`grid grid-cols-[28px_1fr] items-baseline gap-3 transition-opacity duration-500 ${
                  done || active ? "opacity-100" : "opacity-30"
                }`}
              >
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.2em] ${
                    done ? "text-signal" : active ? "text-ink" : "text-dust"
                  }`}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  className={`text-[14px] ${
                    done
                      ? "text-ink-soft line-through decoration-ink/30"
                      : active
                        ? "text-ink"
                        : "text-dust"
                  }`}
                >
                  {s}
                  {active && (
                    <span className="ml-2 inline-block h-1 w-1 animate-pulse rounded-full bg-signal align-middle" />
                  )}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="mt-10 h-px w-full overflow-hidden bg-ink/15">
          <div
            className="h-full bg-signal transition-[width] duration-500 ease-out"
            style={{ width: `${(doneCount / STEPS.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
