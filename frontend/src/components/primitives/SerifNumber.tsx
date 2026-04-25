// Kept for backwards-compat — emits a sans display number now.
export function SerifNumber({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`num font-medium leading-none tracking-tight ${className}`}
    >
      {children}
    </span>
  );
}
