export const eur = (n: number) =>
  new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);

export const eurCompact = (n: number) =>
  new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    notation: n >= 10000 ? "compact" : "standard",
    maximumFractionDigits: n >= 10000 ? 1 : 0,
  }).format(n);

export const kwh = (n: number) =>
  `${new Intl.NumberFormat("de-DE").format(Math.round(n))} kWh`;

export const co2 = (kg: number) => {
  if (kg >= 1000) return `${(kg / 1000).toFixed(1)} t CO₂`;
  return `${Math.round(kg)} kg CO₂`;
};

export const num = (n: number) => new Intl.NumberFormat("de-DE").format(n);
