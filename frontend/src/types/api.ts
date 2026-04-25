export type Vec3 = [number, number, number];
export type LatLng = { lat: number; lng: number };

export type RoofSegment = {
  id: string;
  pitchDegrees: number;
  azimuthDegrees: number;
  areaMeters2: number;
  groundAreaMeters2: number;
  centerLatLng: LatLng;
  planeHeightMeters: number;
};

export type Obstruction = {
  id: string;
  type: "chimney" | "skylight" | "vent" | "antenna" | "dormer";
  polygonLatLng: LatLng[];
  confidence: number;
};

export type PanelPlacement = {
  id: string;
  position: Vec3;
  normal: Vec3;
  orientation: "LANDSCAPE" | "PORTRAIT";
  segmentId: string;
  yearlyEnergyKwh: number;
};

export type BomLine = {
  category:
    | "module"
    | "inverter"
    | "battery"
    | "mounting"
    | "wallbox"
    | "heatpump"
    | "service";
  name: string;
  brand?: string;
  quantity: number;
  unitPriceEur: number;
};

export type Design = {
  packageId: string;
  pv: { kwp: number; panelCount: number; positions: PanelPlacement[] };
  battery: { kwh: number; brand: string; model: string } | null;
  heatpump: { kw: number; brand: string; model: string } | null;
  wallbox: { kw: number; brand: string } | null;
  bom: BomLine[];
  metrics: {
    annualGenerationKwh: number;
    systemCostEur: number;
    paybackYears: number;
    co2SavedKgPerYear: number;
    selfConsumptionPct: number;
  };
  reasoning: { pv: string; battery: string; heatpump?: string };
};

export type HeatingType =
  | "gas"
  | "oil"
  | "district"
  | "electric"
  | "heatpump"
  | "none"
  | "unknown";

export type Profile = {
  address: string;
  monthlyBillEur: number;
  inhabitants: number;
  heating: HeatingType;
  hasEv: boolean;
  evKmPerYear?: number;
  // V2 fields backing the real /api/recommendations contract.
  // Optional only at the type level — the form always sets them.
  houseSizeSqm?: number;
  hasSolar?: boolean;
  hasStorage?: boolean;
  hasWallbox?: boolean;
  // Geocoded metadata when the user picked a Google Places result. If null,
  // DesignerApp falls back to /api/location/house-model server-side geocoding.
  latitude?: number | null;
  longitude?: number | null;
  googlePlaceId?: string | null;
};

export type DesignResponse = {
  location: { latLng: LatLng; buildingFootprint: LatLng[] };
  roof: { segments: RoofSegment[] };
  obstructions: Obstruction[];
  design: Design;
};

export type RefineRequest = {
  currentDesign: Design;
  intent: string;
};

export type RefineResponse = {
  design: Design;
  note?: string;
};
