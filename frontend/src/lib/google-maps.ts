type PlaceFields = {
  displayName?: string;
  formattedAddress?: string;
  location?: { lat: () => number; lng: () => number };
  id?: string;
};

type Place = PlaceFields & {
  fetchFields: (opts: { fields: string[] }) => Promise<{ place: PlaceFields }>;
};

type PredictionTextSpan = {
  text: string;
  matches?: { startOffset: number; endOffset: number }[];
};

type PlacePrediction = {
  placeId: string;
  text: PredictionTextSpan;
  structuredFormat?: {
    mainText: PredictionTextSpan;
    secondaryText?: PredictionTextSpan;
  };
  toPlace: () => Place;
};

type AutocompleteSuggestion = {
  placePrediction?: PlacePrediction;
};

type AutocompleteSessionToken = object;

type SessionTokenCtor = new () => AutocompleteSessionToken;

type FetchAutocompleteRequest = {
  input: string;
  sessionToken?: AutocompleteSessionToken;
  includedRegionCodes?: string[];
  language?: string;
  region?: string;
  includedPrimaryTypes?: string[];
};

type AutocompleteSuggestionStatic = {
  fetchAutocompleteSuggestions: (
    req: FetchAutocompleteRequest,
  ) => Promise<{ suggestions: AutocompleteSuggestion[] }>;
};

type GoogleMapsNamespace = {
  maps: {
    importLibrary: (name: string) => Promise<unknown>;
    places: {
      AutocompleteSuggestion: AutocompleteSuggestionStatic;
      AutocompleteSessionToken: SessionTokenCtor;
    };
  };
};

declare global {
  interface Window {
    google?: GoogleMapsNamespace;
  }
}

export type {
  GoogleMapsNamespace,
  Place,
  PlacePrediction,
  AutocompleteSuggestion,
  AutocompleteSessionToken,
};

let loader: Promise<GoogleMapsNamespace> | null = null;

export function loadGoogleMaps(apiKey: string): Promise<GoogleMapsNamespace> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("loadGoogleMaps called during SSR"));
  }
  if (window.google?.maps?.places) {
    return Promise.resolve(window.google);
  }
  if (loader) return loader;

  loader = new Promise((resolve, reject) => {
    const callbackName = `__gmaps_cb_${Math.random().toString(36).slice(2)}`;
    (window as unknown as Record<string, () => void>)[callbackName] = () => {
      delete (window as unknown as Record<string, unknown>)[callbackName];
      if (window.google) resolve(window.google);
      else reject(new Error("Google Maps loaded but window.google is missing"));
    };

    const script = document.createElement("script");
    const params = new URLSearchParams({
      key: apiKey,
      libraries: "places",
      callback: callbackName,
      v: "weekly",
      loading: "async",
    });
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
    script.async = true;
    script.defer = true;
    script.onerror = () => {
      loader = null;
      reject(new Error("Google Maps script failed to load"));
    };
    document.head.appendChild(script);
  });

  return loader;
}
