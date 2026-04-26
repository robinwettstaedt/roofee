"use client";

/**
 * Roofee wordmark + chevron mark. The chevron is a stylised roof peak
 * (the silhouette of a pitched roof from the front), drawn architectural-
 * draughting style: square line caps, mitered apex, ink stroke. Sized to
 * sit on the cap-height line of the wordmark.
 */
export function RoofeeLogo({
  className = "",
  size = "default",
}: {
  className?: string;
  size?: "compact" | "default" | "large";
}) {
  const iconSize =
    size === "large"
      ? "h-7 w-7"
      : size === "compact"
        ? "h-3.5 w-3.5"
        : "h-4 w-4";
  const textSize =
    size === "large"
      ? "text-[24px]"
      : size === "compact"
        ? "text-[13px]"
        : "text-[15px]";
  const gap = size === "large" ? "gap-2.5" : "gap-1.5";
  return (
    <span
      className={`inline-flex items-center text-ink ${gap} ${className}`}
      aria-label="Roofee"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.75"
        strokeLinecap="square"
        strokeLinejoin="miter"
        className={iconSize}
        aria-hidden
      >
        <path d="M 3 13.5 L 12 8.5 L 21 13.5" />
      </svg>
      <span className={`font-semibold tracking-tight ${textSize}`}>
        Roofee
      </span>
    </span>
  );
}
