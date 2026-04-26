"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Box, MapPin, Upload, X } from "lucide-react";
import type { Profile } from "@/types/api";
import { RoofeeLogo } from "./RoofeeLogo";
import { SecondaryInputs } from "./SecondaryInputs";
import {
  loadGoogleMaps,
  type AutocompleteSessionToken,
  type AutocompleteSuggestion,
  type GoogleMapsNamespace,
} from "@/lib/google-maps";

// Faint blueprint dot-grid behind the intake pages. Reads as a draftsman's
// surface, so the cream paper feels like a tool, not a marketing background.
const DOT_GRID_BG: React.CSSProperties = {
  backgroundImage:
    "radial-gradient(circle, rgba(24,23,21,0.05) 1px, transparent 1px)",
  backgroundSize: "24px 24px",
  backgroundPosition: "-12px -12px",
};

export function AddressIntake({
  initialAddress = "Hauptstraße 1, 10827 Berlin",
  onSubmit,
  disabled,
}: {
  initialAddress?: string;
  onSubmit: (p: Profile) => void;
  disabled?: boolean;
}) {
  const [address, setAddress] = useState(initialAddress);
  const [step, setStep] = useState<1 | 2>(1);
  const [monthlyBillEur, setMonthlyBillEur] = useState(180);
  const [inhabitants, setInhabitants] = useState(2);
  const [heating, setHeating] = useState<Profile["heating"]>("gas");
  const [hasEv, setHasEv] = useState(false);
  const [evKmPerYear, setEvKmPerYear] = useState(12000);
  const [houseSizeSqm, setHouseSizeSqm] = useState(110);
  const [hasSolar, setHasSolar] = useState(false);
  const [hasStorage, setHasStorage] = useState(false);
  const [hasWallbox, setHasWallbox] = useState(false);
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [googlePlaceId, setGooglePlaceId] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const googleRef = useRef<GoogleMapsNamespace | null>(null);
  const sessionTokenRef = useRef<AutocompleteSessionToken | null>(null);
  const debounceRef = useRef<number | null>(null);
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  // load Google Maps once on mount of step 1
  useEffect(() => {
    if (step !== 1) return;
    inputRef.current?.focus();
    inputRef.current?.select();

    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      console.warn(
        "[AddressIntake] NEXT_PUBLIC_GOOGLE_MAPS_API_KEY not set — autocomplete disabled.",
      );
      return;
    }
    let cancelled = false;
    loadGoogleMaps(apiKey)
      .then((g) => {
        if (cancelled) return;
        googleRef.current = g;
        sessionTokenRef.current = new g.maps.places.AutocompleteSessionToken();
      })
      .catch((err) =>
        console.error("[AddressIntake] Google Maps load failed:", err),
      );
    return () => {
      cancelled = true;
    };
  }, [step]);

  // close dropdown on outside click
  useEffect(() => {
    if (!showDropdown) return;
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [showDropdown]);

  const fetchSuggestions = useCallback(async (input: string) => {
    if (!googleRef.current || input.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      const { suggestions } =
        await googleRef.current.maps.places.AutocompleteSuggestion.fetchAutocompleteSuggestions(
          {
            input,
            sessionToken: sessionTokenRef.current ?? undefined,
            includedRegionCodes: ["de"],
            language: "de",
            region: "DE",
          },
        );
      setSuggestions(suggestions);
      setShowDropdown(true);
      setHighlightedIndex(-1);
    } catch (err) {
      console.error("[AddressIntake] suggestions fetch failed:", err);
      setSuggestions([]);
    }
  }, []);

  const onAddressInputChange = (next: string) => {
    setAddress(next);
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => fetchSuggestions(next), 200);
  };

  const selectSuggestion = useCallback(
    async (suggestion: AutocompleteSuggestion) => {
      if (!suggestion.placePrediction) return;
      try {
        const place = suggestion.placePrediction.toPlace();
        await place.fetchFields({
          fields: ["formattedAddress", "location", "id"],
        });
        if (place.formattedAddress) setAddress(place.formattedAddress);
        if (place.location) {
          setLatitude(place.location.lat());
          setLongitude(place.location.lng());
        }
        if (place.id) setGooglePlaceId(place.id);
        // Per Google billing guidance: rotate session token after a place selection.
        if (googleRef.current) {
          sessionTokenRef.current =
            new googleRef.current.maps.places.AutocompleteSessionToken();
        }
      } catch (err) {
        console.error("[AddressIntake] place fetch failed:", err);
      } finally {
        setSuggestions([]);
        setShowDropdown(false);
        setHighlightedIndex(-1);
      }
    },
    [],
  );

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && suggestions.length) {
      e.preventDefault();
      setShowDropdown(true);
      setHighlightedIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp" && suggestions.length) {
      e.preventDefault();
      setHighlightedIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      if (showDropdown && highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        e.preventDefault();
        void selectSuggestion(suggestions[highlightedIndex]);
      } else {
        continueToStep2();
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  const ready = address.trim().length > 4;

  function continueToStep2() {
    if (!ready) return;
    setStep(2);
  }

  function submit() {
    if (!ready || disabled) return;
    onSubmit({
      address,
      monthlyBillEur,
      inhabitants,
      heating,
      hasEv,
      ...(hasEv ? { evKmPerYear } : {}),
      houseSizeSqm,
      hasSolar,
      hasStorage,
      hasWallbox,
      latitude,
      longitude,
      googlePlaceId,
    });
  }

  return (
    <div className="flex h-screen w-screen flex-col" style={DOT_GRID_BG}>
      <header className="flex flex-col items-center gap-2 px-6 pt-6 pb-3">
        <RoofeeLogo size="large" />
        {step === 2 && (
          <FlowStepper current="details" onJumpToAddress={() => setStep(1)} />
        )}
      </header>

      {step === 1 ? (
        <main className="relative flex flex-1 overflow-hidden">
          <HeroVisual />
          <div className="relative z-10 mx-auto flex w-full max-w-[1180px] items-center px-6 py-8">
            <div className="w-full max-w-[520px]">
            <h1
              className="rise text-[34px] md:text-[40px] font-medium leading-[1.1] tracking-tight text-ink lg:text-[44px]"
              style={{ animationDelay: "20ms" }}
            >
              Let&rsquo;s design your solar system.
            </h1>
            <p
              className="rise mt-4 max-w-[440px] text-[15px] text-dust"
              style={{ animationDelay: "100ms" }}
            >
              Start with the home&rsquo;s address.
            </p>

            <div
              className="rise mt-8 relative z-30"
              style={{ animationDelay: "180ms" }}
            >
              <div ref={wrapRef} className="relative">
                <MapPin
                  className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 h-5 w-5 text-dust"
                  strokeWidth={1.5}
                  aria-hidden
                />
                <input
                  ref={inputRef}
                  className="input-hero text-[24px] md:text-[28px] !pl-14 !pr-16 !text-left"
                  value={address}
                  onChange={(e) => onAddressInputChange(e.target.value)}
                  onFocus={() => {
                    if (suggestions.length) setShowDropdown(true);
                  }}
                  onKeyDown={onKeyDown}
                  placeholder="Street and city"
                  spellCheck={false}
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={continueToStep2}
                  disabled={!ready || disabled}
                  aria-label="Continue"
                  className="absolute right-3 top-1/2 -translate-y-1/2 grid h-10 w-10 place-items-center rounded-full bg-ink text-paper transition hover:bg-signal disabled:cursor-not-allowed disabled:bg-ink/20"
                >
                  <ArrowRight className="h-4 w-4" strokeWidth={2} aria-hidden />
                </button>
                {showDropdown && suggestions.length > 0 && (
                  <ul
                    role="listbox"
                    className="absolute left-0 right-0 top-full z-30 mt-2 max-h-80 overflow-auto rounded-xl border border-ink/15 bg-paper shadow-lg"
                  >
                    {suggestions.map((s, i) => {
                      const pred = s.placePrediction;
                      if (!pred) return null;
                      const main = pred.structuredFormat?.mainText.text ?? pred.text.text;
                      const secondary = pred.structuredFormat?.secondaryText?.text ?? "";
                      const active = i === highlightedIndex;
                      return (
                        <li
                          key={pred.placeId}
                          role="option"
                          aria-selected={active}
                          onMouseEnter={() => setHighlightedIndex(i)}
                          onMouseDown={(e) => {
                            // mousedown beats blur — keeps input focus
                            e.preventDefault();
                            void selectSuggestion(s);
                          }}
                          className={`flex cursor-pointer items-baseline gap-3 px-4 py-3 text-left transition ${
                            active ? "bg-paper-deep" : "hover:bg-paper-deep/60"
                          }`}
                        >
                          <span className="text-[15px] text-ink">{main}</span>
                          {secondary && (
                            <span className="text-[12px] text-dust">{secondary}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>

            <p
              className="rise mt-4 text-[12px] text-dust"
              style={{ animationDelay: "260ms" }}
            >
              Next: a few quick questions about the home — under a minute.
            </p>

            <div
              className="rise mt-8"
              style={{ animationDelay: "340ms" }}
            >
              {fileName ? (
                <div className="inline-flex items-center gap-2 rounded-full border border-ink/15 bg-paper/70 px-3.5 py-1.5 text-[12px]">
                  <Box
                    className="h-3.5 w-3.5 text-ink-soft"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                  <span className="num text-ink">{fileName}</span>
                  <button
                    type="button"
                    onClick={() => setFileName(null)}
                    className="ml-0.5 grid h-4 w-4 place-items-center rounded-full text-dust transition hover:bg-ink/10 hover:text-ink"
                    aria-label="Remove file"
                  >
                    <X className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                  </button>
                </div>
              ) : (
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-[12px] text-dust transition hover:text-ink">
                  <Upload
                    className="h-3.5 w-3.5"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                  <span className="underline-offset-4 hover:underline">
                    Or upload a 3D model
                  </span>
                  <input
                    type="file"
                    accept=".glb,.gltf,model/gltf-binary,model/gltf+json"
                    className="hidden"
                    onChange={(e) =>
                      setFileName(e.target.files?.[0]?.name ?? null)
                    }
                  />
                </label>
              )}
            </div>
            </div>
          </div>
        </main>
      ) : (
        <main className="flex flex-1 items-start justify-center px-6 py-8">
          <div className="w-full max-w-[640px]">
            <p
              className="rise truncate text-[12px] text-dust"
              style={{ animationDelay: "40ms" }}
              title={address}
            >
              {address}
            </p>

            <div
              className="rise mt-8"
              style={{ animationDelay: "120ms" }}
            >
              <SecondaryInputs
                monthlyBillEur={monthlyBillEur}
                onMonthlyBillEur={setMonthlyBillEur}
                inhabitants={inhabitants}
                onInhabitants={setInhabitants}
                heating={heating}
                onHeating={setHeating}
                hasEv={hasEv}
                onHasEv={setHasEv}
                evKmPerYear={evKmPerYear}
                onEvKmPerYear={setEvKmPerYear}
                houseSizeSqm={houseSizeSqm}
                onHouseSizeSqm={setHouseSizeSqm}
                hasSolar={hasSolar}
                onHasSolar={setHasSolar}
                hasStorage={hasStorage}
                onHasStorage={setHasStorage}
                hasWallbox={hasWallbox}
                onHasWallbox={setHasWallbox}
                loading={!!disabled}
                onComplete={submit}
                onBackToAddress={() => setStep(1)}
              />
            </div>
          </div>
        </main>
      )}
    </div>
  );
}

/**
 * Hero visual for the address page. Anchored to the right edge of the main
 * content area, full height, with a left-side gradient mask so it bleeds
 * into the cream paper instead of presenting a hard edge. Hidden below lg.
 *
 * Drop a generated image at /frontend/public/intake-hero.png (or .jpg —
 * adjust the src below). Until the file exists, an inline SVG placeholder
 * keeps the layout intentional.
 */
function HeroVisual() {
  const [imgFailed, setImgFailed] = useState(false);
  // Fade the left ~38% of the image into transparent so it dissolves into
  // the cream background instead of sitting in a hard rectangle.
  const fadeMask =
    "linear-gradient(to right, transparent 0%, rgba(0,0,0,0.35) 18%, black 38%)";
  const maskStyle: React.CSSProperties = {
    WebkitMaskImage: fadeMask,
    maskImage: fadeMask,
  };
  return (
    <div
      className="pointer-events-none absolute inset-y-0 right-0 hidden w-[62%] lg:block"
      aria-hidden
    >
      {imgFailed ? (
        <div className="relative h-full w-full" style={maskStyle}>
          <HeroPlaceholder />
        </div>
      ) : (
        <img
          src="/intake-hero.png"
          alt=""
          className="h-full w-full object-cover object-center"
          style={maskStyle}
          onError={() => setImgFailed(true)}
        />
      )}
    </div>
  );
}

function HeroPlaceholder() {
  // Stylized "satellite tile" mock — readable as the product's output without
  // needing a real screenshot. Replaced once /intake-hero.png is present.
  return (
    <svg
      viewBox="0 0 400 500"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 h-full w-full"
      aria-hidden
    >
      <defs>
        <pattern
          id="hero-grid"
          width="20"
          height="20"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1" cy="1" r="1" fill="rgba(24,23,21,0.07)" />
        </pattern>
        <linearGradient id="hero-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ece8de" />
          <stop offset="100%" stopColor="#e2dccd" />
        </linearGradient>
      </defs>

      <rect width="400" height="500" fill="url(#hero-sky)" />
      <rect width="400" height="500" fill="url(#hero-grid)" />

      {/* Roof silhouette from above */}
      <polygon
        points="80,170 320,170 340,260 320,360 80,360 60,260"
        fill="rgba(24,23,21,0.06)"
        stroke="rgba(24,23,21,0.45)"
        strokeWidth="1.5"
      />
      {/* Ridge line */}
      <line
        x1="80"
        y1="265"
        x2="320"
        y2="265"
        stroke="rgba(24,23,21,0.30)"
        strokeWidth="1"
        strokeDasharray="4 4"
      />

      {/* Solar panel grid — top half */}
      {Array.from({ length: 4 }).map((_, row) =>
        Array.from({ length: 6 }).map((_, col) => (
          <rect
            key={`t-${row}-${col}`}
            x={108 + col * 32}
            y={186 + row * 17}
            width="28"
            height="14"
            fill="rgba(24,23,21,0.78)"
            stroke="rgba(232,90,44,0.4)"
            strokeWidth="0.5"
          />
        )),
      )}
      {/* Solar panel grid — bottom half */}
      {Array.from({ length: 3 }).map((_, row) =>
        Array.from({ length: 6 }).map((_, col) => (
          <rect
            key={`b-${row}-${col}`}
            x={108 + col * 32}
            y={278 + row * 17}
            width="28"
            height="14"
            fill="rgba(24,23,21,0.78)"
            stroke="rgba(232,90,44,0.4)"
            strokeWidth="0.5"
          />
        )),
      )}

      {/* North arrow */}
      <g transform="translate(354 56)">
        <circle r="18" fill="none" stroke="rgba(24,23,21,0.25)" strokeWidth="1" />
        <path
          d="M 0,-12 L 5,4 L 0,1 L -5,4 Z"
          fill="rgba(232,90,44,1)"
        />
        <text
          x="0"
          y="14"
          textAnchor="middle"
          fontSize="9"
          fontFamily="monospace"
          fill="rgba(24,23,21,0.55)"
          letterSpacing="0.1em"
        >
          N
        </text>
      </g>

      {/* Stamp */}
      <g transform="translate(28 462)">
        <text
          fontSize="9"
          fontFamily="monospace"
          fill="rgba(24,23,21,0.40)"
          letterSpacing="0.18em"
        >
          ROOFEE · LAYOUT PREVIEW
        </text>
      </g>
    </svg>
  );
}

function FlowStepper({
  current,
  onJumpToAddress,
}: {
  current: "address" | "details" | "design";
  onJumpToAddress?: () => void;
}) {
  const dot = (
    <span className="text-ink/30" aria-hidden>
      ·
    </span>
  );
  return (
    <nav
      className="flex items-center gap-3 text-[11px] uppercase tracking-[0.16em]"
      aria-label="Progress"
    >
      {current === "address" || !onJumpToAddress ? (
        <span
          className={
            current === "address" ? "font-medium text-ink" : "text-ink/30"
          }
        >
          Address
        </span>
      ) : (
        <button
          type="button"
          onClick={onJumpToAddress}
          className="text-dust transition hover:text-ink"
        >
          ← Address
        </button>
      )}
      {dot}
      <span
        className={
          current === "details" ? "font-medium text-ink" : "text-ink/30"
        }
      >
        Details
      </span>
      {dot}
      <span
        className={
          current === "design" ? "font-medium text-ink" : "text-ink/30"
        }
      >
        Design
      </span>
    </nav>
  );
}
