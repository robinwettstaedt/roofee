"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Profile } from "@/types/api";
import { SecondaryInputs } from "./SecondaryInputs";
import {
  loadGoogleMaps,
  type AutocompleteSessionToken,
  type AutocompleteSuggestion,
  type GoogleMapsNamespace,
} from "@/lib/google-maps";

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
    <div className="flex h-screen w-screen flex-col">
      <header className="flex h-14 items-center px-6">
        <span className="text-[15px] font-semibold tracking-tight text-ink">
          Roofee
        </span>
      </header>

      {step === 1 ? (
        <main className="flex flex-1 items-center justify-center px-6">
          <div className="w-full max-w-[640px] -mt-12">
            <h1
              className="rise text-center text-[34px] md:text-[40px] font-medium leading-[1.15] tracking-tight text-ink"
              style={{ animationDelay: "20ms" }}
            >
              Let&rsquo;s design your solar system.
            </h1>
            <p
              className="rise mt-4 text-center text-[15px] text-dust"
              style={{ animationDelay: "100ms" }}
            >
              Start with the home&rsquo;s address.
            </p>

            <div
              className="rise mt-12 relative z-30"
              style={{ animationDelay: "180ms" }}
            >
              <div ref={wrapRef} className="relative">
                <input
                  ref={inputRef}
                  className="input-hero text-[26px] md:text-[30px]"
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

            <div
              className="rise mt-10 flex justify-center"
              style={{ animationDelay: "260ms" }}
            >
              <button
                type="button"
                disabled={!ready || disabled}
                onClick={continueToStep2}
                className="inline-flex items-center gap-2 rounded-full bg-ink px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-signal disabled:cursor-not-allowed disabled:bg-ink/25"
              >
                Continue
                <span aria-hidden>→</span>
              </button>
            </div>

            <div
              className="rise mt-10 text-center"
              style={{ animationDelay: "340ms" }}
            >
              <label className="cursor-pointer text-[13px] text-dust underline-offset-4 hover:text-ink hover:underline">
                <input
                  type="file"
                  accept=".glb,.gltf,model/gltf-binary,model/gltf+json"
                  className="hidden"
                  onChange={(e) =>
                    setFileName(e.target.files?.[0]?.name ?? null)
                  }
                />
                {fileName ? `Selected: ${fileName}` : "or upload your own 3D model"}
              </label>
            </div>
          </div>
        </main>
      ) : (
        <main className="flex flex-1 items-start justify-center px-6 py-8">
          <div className="w-full max-w-[640px]">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rise text-[13px] text-dust transition hover:text-ink"
              style={{ animationDelay: "20ms" }}
            >
              ← {address}
            </button>

            <h1
              className="rise mt-6 text-[28px] font-medium leading-tight tracking-tight text-ink"
              style={{ animationDelay: "60ms" }}
            >
              A few details about the home.
            </h1>
            <p
              className="rise mt-2 text-[14px] text-dust"
              style={{ animationDelay: "120ms" }}
            >
              We use these to size the system. You can change everything later.
            </p>

            <div
              className="rise mt-10"
              style={{ animationDelay: "180ms" }}
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
              />
            </div>

            <div className="mt-10 flex items-center justify-end gap-4">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="text-[13px] text-dust transition hover:text-ink"
              >
                Back
              </button>
              <button
                type="button"
                disabled={!ready || disabled}
                onClick={submit}
                className="inline-flex items-center gap-2 rounded-full bg-signal px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
              >
                Design my system
                <span aria-hidden>→</span>
              </button>
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
