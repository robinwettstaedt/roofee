"use client";

export function SessionBar({
  showBack,
  onBack,
  breadcrumb,
  rightSlot,
}: {
  showBack?: boolean;
  onBack?: () => void;
  breadcrumb?: React.ReactNode;
  rightSlot?: React.ReactNode;
}) {
  return (
    <div className="relative flex h-12 w-full items-center justify-between border-b border-ink/15 bg-paper/80 px-5 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        {showBack && (
          <button
            type="button"
            onClick={onBack}
            className="text-[13px] text-dust transition hover:text-ink"
          >
            ← Back
          </button>
        )}
        <span className="text-[15px] font-semibold leading-none tracking-tight text-ink">
          Roofee
        </span>
        {breadcrumb ? (
          <span className="ml-3 flex items-center gap-2 text-[12px] text-dust">
            <span className="rule-vert h-3" />
            {breadcrumb}
          </span>
        ) : null}
      </div>

      <div className="flex items-center gap-3">{rightSlot}</div>
    </div>
  );
}
