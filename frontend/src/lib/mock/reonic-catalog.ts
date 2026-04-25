export const PACKAGES = [
  {
    id: "sigenergy_10_8_9",
    brand: "Sigenergy",
    pvKwp: 10.8,
    batteryKwh: 9,
    inverterKw: 10,
    targetDemandKwh: [4500, 8000],
    estimatedPriceEur: [22000, 25000],
  },
  {
    id: "goodwe_6_3_5",
    brand: "GoodWe",
    pvKwp: 6.3,
    batteryKwh: 5,
    inverterKw: 5,
    targetDemandKwh: [0, 3500],
    estimatedPriceEur: [14000, 16000],
  },
  {
    id: "sigenergy_13_5_9",
    brand: "Sigenergy",
    pvKwp: 13.5,
    batteryKwh: 9,
    inverterKw: 12,
    targetDemandKwh: [6000, 12000],
    estimatedPriceEur: [26000, 30000],
  },
] as const;

export const STANDARD_SERVICES = [
  { name: "Travel & Logistics Flat Rate", priceEur: 350 },
  { name: "Planning & Consulting", priceEur: 600 },
  { name: "Install Inverter", priceEur: 480 },
  { name: "AC Surge Protection", priceEur: 220 },
  { name: "Grid Registration", priceEur: 180 },
  { name: "Delivery to Site", priceEur: 290 },
  { name: "Site Setup / Safety", priceEur: 340 },
];

export const MOUNTING_PER_PANEL_EUR = 50;
export const PANEL_PRICE_EUR = 140;
