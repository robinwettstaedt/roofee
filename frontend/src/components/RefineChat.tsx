"use client";
import { useState } from "react";

const SUGGESTIONS = ["Remove battery", "Make it cheaper", "Add EV charger"];

export function RefineChat({
  onRefine,
  loading,
}: {
  onRefine: (intent: string) => void;
  loading: boolean;
}) {
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);

  function submit(intent: string) {
    if (!intent.trim() || loading) return;
    onRefine(intent.trim());
    setValue("");
    setOpen(false);
  }

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-6 z-10 flex justify-center px-6">
      <div className="pointer-events-auto w-full max-w-[640px]">
        {open ? (
          <div className="overlay-surface fade flex flex-col gap-2 p-2 shadow-xl">
            <div className="flex flex-wrap gap-1.5 px-1.5 pt-1">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={loading}
                  onClick={() => submit(s)}
                  className="border border-ink/15 bg-paper px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft transition hover:border-signal hover:text-signal disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit(value);
              }}
              className="flex items-center gap-2 border border-ink/20 bg-paper px-3 py-1.5"
            >
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">
                Refine
              </span>
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="e.g. 'remove battery', 'add EV charger'"
                disabled={loading}
                autoFocus
                className="flex-1 bg-transparent px-1 py-1 text-[13px] text-ink placeholder:text-dust focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="font-mono text-[10px] uppercase tracking-[0.2em] text-dust hover:text-ink"
              >
                Esc
              </button>
              <button
                type="submit"
                disabled={loading || !value.trim()}
                className="bg-ink px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.2em] text-paper transition hover:bg-signal disabled:opacity-40"
              >
                {loading ? (
                  <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-paper/40 border-t-paper" />
                ) : (
                  "Send →"
                )}
              </button>
            </form>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="overlay-surface mx-auto flex items-center gap-3 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-soft shadow-lg transition hover:text-ink"
          >
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-signal" />
            Refine the design
            <span className="text-dust-soft">⌘K</span>
          </button>
        )}
      </div>
    </div>
  );
}
