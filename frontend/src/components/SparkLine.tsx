import type { MonthlySolarWeather } from "@/types/recommendation";

// Fallback shape for the seasonal curve when PVGIS monthly data isn't
// available — generic Northern-European residential profile, normalised.
const FALLBACK_MONTHLY_SHARE = [
  0.04, 0.06, 0.09, 0.11, 0.12, 0.12, 0.12, 0.11, 0.09, 0.07, 0.04, 0.03,
];

function shareFromPvgis(monthly: MonthlySolarWeather[]): number[] {
  // Sort defensively — backend returns 1..12 in order, but we'd rather not
  // assume — and normalise the optimal-plane irradiation across the year.
  const sorted = [...monthly].sort((a, b) => a.month - b.month);
  const values = sorted.map((m) => m.optimal_irradiation_kwh_per_m2);
  const total = values.reduce((s, v) => s + v, 0);
  if (total <= 0) return FALLBACK_MONTHLY_SHARE;
  return values.map((v) => v / total);
}

export function SparkLine({
  annualKwh,
  monthly,
  width = 132,
  height = 28,
}: {
  annualKwh: number;
  monthly?: MonthlySolarWeather[] | null;
  width?: number;
  height?: number;
}) {
  const share =
    monthly && monthly.length === 12 ? shareFromPvgis(monthly) : FALLBACK_MONTHLY_SHARE;
  const max = Math.max(...share);
  const w = width;
  const h = height;
  const stepX = w / (share.length - 1);
  const pts = share.map((s, i) => {
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
