export function MonoNumber({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={`font-mono num ${className}`}>{children}</span>;
}
