import { NextResponse } from "next/server";
import {
  PACKAGES,
  STANDARD_SERVICES,
  MOUNTING_PER_PANEL_EUR,
  PANEL_PRICE_EUR,
} from "@/lib/mock/reonic-catalog";
import type {
  BomLine,
  Design,
  DesignResponse,
  PanelPlacement,
  Profile,
} from "@/types/api";

const PANEL_KWP = 0.463;
const NORMAL: [number, number, number] = [0, 0.866, 0.5];

function panelGrid(count: number): PanelPlacement[] {
  const cols = 6;
  const rows = Math.ceil(count / cols);
  const dx = 1.65;
  const dz = 1.05;
  const cx = 0;
  const cy = 3;
  const cz = 0;
  const startX = cx - ((cols - 1) * dx) / 2;
  const startZ = cz - ((rows - 1) * dz) / 2;
  const out: PanelPlacement[] = [];
  let i = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (i >= count) break;
      out.push({
        id: `panel-${i}`,
        position: [startX + c * dx, cy + r * 0.5, startZ + r * dz],
        normal: NORMAL,
        orientation: "LANDSCAPE",
        segmentId: "roof-south",
        yearlyEnergyKwh: 410,
      });
      i++;
    }
  }
  return out;
}

function panelCountFromBill(bill: number): number {
  if (bill < 120) return 16;
  if (bill < 220) return 24;
  return 24;
}

function pickPackage(panelCount: number) {
  if (panelCount <= 16) return PACKAGES[1]; // GoodWe
  return PACKAGES[0]; // Sigenergy 10.8/9
}

function buildBom(panelCount: number, pkg: (typeof PACKAGES)[number]): BomLine[] {
  const bom: BomLine[] = [
    {
      category: "module",
      name: "463W TOPCon glass-glass module",
      brand: "Reonic",
      quantity: panelCount,
      unitPriceEur: PANEL_PRICE_EUR,
    },
    {
      category: "inverter",
      name: `${pkg.brand} hybrid inverter ${pkg.inverterKw}kW`,
      brand: pkg.brand,
      quantity: 1,
      unitPriceEur: 2400,
    },
    {
      category: "battery",
      name: `${pkg.brand} battery ${pkg.batteryKwh}kWh`,
      brand: pkg.brand,
      quantity: 1,
      unitPriceEur: 4200,
    },
    {
      category: "mounting",
      name: "Concrete tile mounting kit",
      quantity: panelCount,
      unitPriceEur: MOUNTING_PER_PANEL_EUR,
    },
  ];
  for (const s of STANDARD_SERVICES) {
    bom.push({
      category: "service",
      name: s.name,
      quantity: 1,
      unitPriceEur: s.priceEur,
    });
  }
  return bom;
}

function bomTotal(bom: BomLine[]): number {
  return bom.reduce((sum, l) => sum + l.quantity * l.unitPriceEur, 0);
}

export async function POST(req: Request) {
  const profile = (await req.json()) as Profile;

  await new Promise((r) => setTimeout(r, 4500));

  const panelCount = panelCountFromBill(profile.monthlyBillEur);
  const pkg = pickPackage(panelCount);
  const positions = panelGrid(panelCount);
  const bom = buildBom(panelCount, pkg);
  const systemCostEur = Math.round(bomTotal(bom));
  const annualGenerationKwh = Math.round(panelCount * PANEL_KWP * 950);
  const yearlySavingsEur = profile.monthlyBillEur * 12 * 0.78;
  const paybackYears =
    Math.round((systemCostEur / Math.max(yearlySavingsEur, 1)) * 10) / 10;

  const design: Design = {
    packageId: pkg.id,
    pv: {
      kwp: Math.round(panelCount * PANEL_KWP * 10) / 10,
      panelCount,
      positions,
    },
    battery: {
      kwh: pkg.batteryKwh,
      brand: pkg.brand,
      model: `${pkg.brand} ${pkg.batteryKwh}kWh`,
    },
    heatpump: null,
    wallbox: null,
    bom,
    metrics: {
      annualGenerationKwh,
      systemCostEur,
      paybackYears,
      co2SavedKgPerYear: Math.round(annualGenerationKwh * 0.42),
      selfConsumptionPct: 78,
    },
    reasoning: {
      pv: `Recommended ${Math.round(panelCount * PANEL_KWP * 10) / 10} kWp because your €${profile.monthlyBillEur}/mo bill implies roughly ${Math.round((profile.monthlyBillEur * 12) / 0.35)} kWh/yr demand.`,
      battery: `${pkg.batteryKwh} kWh battery covers your evening load and lifts self-consumption to 78%.`,
    },
  };

  const response: DesignResponse = {
    location: {
      latLng: { lat: 52.4985, lng: 13.3877 },
      buildingFootprint: [
        { lat: 52.4986, lng: 13.3876 },
        { lat: 52.4986, lng: 13.3878 },
        { lat: 52.4984, lng: 13.3878 },
        { lat: 52.4984, lng: 13.3876 },
      ],
    },
    roof: {
      segments: [
        {
          id: "roof-south",
          pitchDegrees: 30,
          azimuthDegrees: 180,
          areaMeters2: 56,
          groundAreaMeters2: 48.5,
          centerLatLng: { lat: 52.4985, lng: 13.3877 },
          planeHeightMeters: 6.4,
        },
      ],
    },
    obstructions: [
      {
        id: "ob-1",
        type: "chimney",
        polygonLatLng: [
          { lat: 52.49853, lng: 13.38772 },
          { lat: 52.49854, lng: 13.38773 },
        ],
        confidence: 0.92,
      },
    ],
    design,
  };

  return NextResponse.json(response);
}
