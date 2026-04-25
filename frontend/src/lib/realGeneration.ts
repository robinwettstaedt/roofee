import type { SolarWeatherMetadata } from "@/types/recommendation";

// Industry-standard performance ratio for residential PV in Germany.
const PERFORMANCE_RATIO = 0.85;

/**
 * Compute annual generation (kWh) from PVGIS-provided optimal-plane irradiation
 * and a chosen system size. This is the real calculation while the backend's
 * sizing/BOM services are still stubbed.
 *
 * Returns null if solar weather data is unavailable so callers can fall back.
 */
export function annualGenerationFromPvgis(
  kwp: number,
  solarWeather: SolarWeatherMetadata | null | undefined,
): number | null {
  if (!solarWeather || !solarWeather.annual_optimal_irradiation_kwh_per_m2) {
    return null;
  }
  return Math.round(
    solarWeather.annual_optimal_irradiation_kwh_per_m2 *
      kwp *
      PERFORMANCE_RATIO,
  );
}
