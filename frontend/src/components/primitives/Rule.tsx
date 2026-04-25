export function Rule({
  soft = false,
  className = "",
}: {
  soft?: boolean;
  className?: string;
}) {
  return <div className={`${soft ? "rule-soft" : "rule"} ${className}`} />;
}
