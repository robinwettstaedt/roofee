import { NextResponse } from "next/server";
import { PACKAGES } from "@/lib/mock/reonic-catalog";
import type { BomLine, Design, RefineRequest, RefineResponse } from "@/types/api";

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function removeBattery(design: Design): Design {
  const next = clone(design);
  next.battery = null;
  next.bom = next.bom.filter((l) => l.category !== "battery");
  next.metrics.systemCostEur = Math.max(0, next.metrics.systemCostEur - 4200);
  next.metrics.selfConsumptionPct = 32;
  next.reasoning.battery = "Battery removed at user request.";
  return next;
}

function makeCheaper(design: Design): Design {
  const next = clone(design);
  const goodwe = PACKAGES.find((p) => p.id === "goodwe_6_3_5")!;
  const newCount = Math.max(8, Math.floor(next.pv.panelCount / 2));
  next.packageId = goodwe.id;
  next.pv.panelCount = newCount;
  next.pv.kwp = Math.round(newCount * 0.463 * 10) / 10;
  next.pv.positions = next.pv.positions.slice(0, newCount);
  next.battery = {
    kwh: goodwe.batteryKwh,
    brand: goodwe.brand,
    model: `${goodwe.brand} ${goodwe.batteryKwh}kWh`,
  };
  next.bom = next.bom
    .filter((l) => l.category !== "module" && l.category !== "mounting")
    .concat([
      {
        category: "module",
        name: "463W TOPCon module",
        brand: "Reonic",
        quantity: newCount,
        unitPriceEur: 140,
      },
      {
        category: "mounting",
        name: "Concrete tile mounting kit",
        quantity: newCount,
        unitPriceEur: 50,
      },
    ]);
  next.bom = next.bom.map((l) =>
    l.category === "battery"
      ? { ...l, name: `${goodwe.brand} battery ${goodwe.batteryKwh}kWh`, unitPriceEur: 2800 }
      : l.category === "inverter"
        ? { ...l, name: `${goodwe.brand} hybrid inverter ${goodwe.inverterKw}kW`, unitPriceEur: 1600 }
        : l,
  );
  next.metrics.systemCostEur = next.bom.reduce(
    (s, l) => s + l.quantity * l.unitPriceEur,
    0,
  );
  next.metrics.annualGenerationKwh = Math.round(newCount * 0.463 * 950);
  next.metrics.paybackYears =
    Math.round((next.metrics.systemCostEur / Math.max(next.metrics.annualGenerationKwh * 0.32, 1)) * 10) /
    10;
  next.reasoning.pv = `Switched to GoodWe ${goodwe.pvKwp} kWp to lower upfront cost.`;
  return next;
}

function addWallbox(design: Design): Design {
  const next = clone(design);
  next.wallbox = { kw: 11, brand: "Reonic" };
  const lines: BomLine[] = [
    {
      category: "wallbox",
      name: "Wallbox 11kW v2",
      brand: "Reonic",
      quantity: 1,
      unitPriceEur: 900,
    },
    {
      category: "service",
      name: "Wallbox Installation",
      quantity: 1,
      unitPriceEur: 700,
    },
  ];
  next.bom = next.bom.concat(lines);
  next.metrics.systemCostEur += 1600;
  next.metrics.paybackYears =
    Math.round((next.metrics.systemCostEur / Math.max(next.metrics.annualGenerationKwh * 0.32, 1)) * 10) /
    10;
  return next;
}

export async function POST(req: Request) {
  const body = (await req.json()) as RefineRequest;
  const intent = body.intent.toLowerCase().trim();

  await new Promise((r) => setTimeout(r, 1500));

  let design = body.currentDesign;
  let note: string | undefined;

  if (intent.includes("remove battery") || intent.includes("no battery")) {
    design = removeBattery(design);
  } else if (intent.includes("cheaper")) {
    design = makeCheaper(design);
  } else if (intent.includes("wallbox") || intent.includes("ev charger") || intent.includes("add ev")) {
    design = addWallbox(design);
  } else {
    note = "Refinement understood as no-op for the prototype.";
  }

  const response: RefineResponse = { design, note };
  return NextResponse.json(response);
}
