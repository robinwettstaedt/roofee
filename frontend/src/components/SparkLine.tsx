// Annual generation distribution sparkline — German solar curve, normalized.
const MONTHLY_SHARE = [
  0.04, 0.06, 0.09, 0.11, 0.12, 0.12, 0.12, 0.11, 0.09, 0.07, 0.04, 0.03,
];

export function SparkLine({
  annualKwh,
  width = 132,
  height = 28,
}: {
  annualKwh: number;
  width?: number;
  height?: number;
}) {
  const max = Math.max(...MONTHLY_SHARE);
  const w = width;
  const h = height;
  const stepX = w / (MONTHLY_SHARE.length - 1);
  const pts = MONTHLY_SHARE.map((s, i) => {
    const y = h - (s / max) * (h - 4) - 2;
    return [i * stepX, y] as const;
  });
  const d = pts
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`)
    .join(" ");
  const area = `${d} L ${w} ${h} L 0 ${h} Z`;
  return (
    <svg width={w} height={h} className="block" aria-hidden>
      <path d={area} fill="#F0A93B" fillOpacity="0.18" />
      <path d={d} stroke="#E9542A" strokeWidth="1.25" fill="none" />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={1.2} fill="#16140F" opacity={0.4} />
      ))}
      <title>Monthly share of {Math.round(annualKwh)} kWh annual generation</title>
    </svg>
  );
}
