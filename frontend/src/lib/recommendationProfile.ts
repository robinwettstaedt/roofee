import type { Profile } from "@/types/api";
import type { RecommendationRequest } from "@/types/recommendation";

// Defaults the user never sees.
export const DEFAULT_ELECTRICITY_PRICE_EUR_PER_KWH = 0.35;
export const DEFAULT_LOAD_PROFILE = "H0";

export function buildRecommendationRequest(
  profile: Profile,
  latLng: { latitude: number; longitude: number },
  googlePlaceId?: string | null,
): RecommendationRequest {
  const annualKwh =
    (profile.monthlyBillEur * 12) / DEFAULT_ELECTRICITY_PRICE_EUR_PER_KWH;

  return {
    address: profile.address,
    latitude: latLng.latitude,
    longitude: latLng.longitude,
    google_place_id: googlePlaceId ?? null,
    annual_electricity_demand_kwh: Math.max(1, Math.round(annualKwh)),
    electricity_price_per_kwh: DEFAULT_ELECTRICITY_PRICE_EUR_PER_KWH,
    load_profile: DEFAULT_LOAD_PROFILE,
    num_inhabitants: profile.inhabitants,
    house_size_sqm: profile.houseSizeSqm ?? 110,
    heating_existing_type: profile.heating,
    has_ev: profile.hasEv,
    has_solar: profile.hasSolar ?? false,
    has_storage: profile.hasStorage ?? false,
    has_wallbox: profile.hasWallbox ?? false,
    recommendation_goal: "balanced",
    battery_preference: "consider",
    heat_pump_preference: "consider",
    ev_charger_preference: "consider",
    ev_annual_drive_distance_km: profile.hasEv ? profile.evKmPerYear ?? null : null,
  };
}
