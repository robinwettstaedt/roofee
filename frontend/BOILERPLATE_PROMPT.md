## --- BEGIN PROMPT ---

Build a Next.js 15 + React 19 + TypeScript + Tailwind hackathon demo app: an
AI-powered residential solar + battery designer for the German market. The
user enters a small set of facts about their home, clicks "Generate Design",
watches a streaming "AI is thinking" narrative, then sees their house in 3D
with solar panels rendered on the roof, plus a results panel with system
size, cost, and payback. Frontend is real; backend is mocked but typed
against the contract that real backends (Google Solar API + LLM design
selection) will return.

Build the whole thing end-to-end. No TODOs, no placeholders left for "later".

## Stack — pin these versions (peer deps fragile)

- next@15
- react@19, react-dom@19
- three@^0.170
- @react-three/fiber@^9
- @react-three/drei@^10
- @react-three/postprocessing@^2.16
- typescript, tailwindcss, @types/three

In `next.config.js` add `transpilePackages: ['three']`. Required to fix the
most common build error.

## Folder structure

```
app/
  page.tsx                  // server component, dynamic-imports the scene
  api/
    design/route.ts         // mock backend — returns full design + panels
    refine/route.ts         // mock — accepts a refinement intent, returns updated design
components/
  DesignerApp.tsx           // 'use client' — full layout (form + canvas)
  Scene.tsx                 // Canvas + lighting + postprocessing
  House.tsx                 // useGLTF loader for the house
  SolarPanels.tsx           // instanced panels from {position, normal}[]
  InputForm.tsx             // left sidebar form (5 fields + optional file upload area)
  ResultsPanel.tsx          // shows kWp, kWh battery, cost, payback, BOM
  ProcessingNarrative.tsx   // streaming "AI is analyzing..." reveal sequence
  RefineChat.tsx            // bottom-anchored chat input for refinement
types/
  api.ts                    // THE contract — shared with backend
lib/
  mock/
    sample-design.json      // hand-crafted realistic mock response
    reonic-catalog.ts       // typed Reonic package catalog (subset)
public/
  house.glb                 // placeholder, see "Placeholder GLB" below
```

## Critical SSR pattern (mandatory — will crash without)

Three.js touches `window` at module scope. `'use client'` is not enough —
must wrap in `next/dynamic` with `ssr: false`:

```tsx
// app/page.tsx — server component
import dynamic from 'next/dynamic'

const DesignerApp = dynamic(() => import('@/components/DesignerApp'), {
  ssr: false,
  loading: () => (
    <div className="h-screen grid place-items-center text-zinc-500">Loading…</div>
  ),
})

export default function Page() {
  return <DesignerApp />
}
```

## Layout

Two-column flex, full viewport height. Left sidebar ~380px, white background,
border-right `border-zinc-200`, padding 24px. Holds InputForm above and
(after generation) ResultsPanel below. Right side: 3D Canvas, full bleed,
soft gradient fallback background.

Bottom of right column (overlaid on canvas, z-index above): RefineChat input —
visible only after a design has been generated.

## InputForm — 5 fields + optional file upload

Defaults are pre-filled so the demo can run with zero typing.

1. **Address** — text input, autocomplete optional. Default "Hauptstraße 1, 10827 Berlin".
2. **Monthly electricity bill in €** — number input. Default 180.
3. **People in the household** — number input, min 1, max 12. Default 2.
4. **Current heating** — select, options:
   `gas | oil | district | electric | heatpump | none`. Default `gas`.
5. **Electric vehicle?** — toggle (no/yes). Default no. If yes, show optional
   "km per year" slider, default 12000.

Below the fields: a thin file dropzone "Optional: drop your Energieausweis or
Stromrechnung for a more accurate design (PDF)" — accepts the file but does
nothing with it for now (display the file name as confirmation, no processing).

CTA button: "Generate Design" — full-width, accent color, disabled if address
is empty.

On click: POST profile to `/api/design`, transition to ProcessingNarrative,
then on response render Scene + ResultsPanel.

## ProcessingNarrative — the reveal sequence

Full-screen overlay (semi-transparent dark backdrop) shown for 4-6 seconds
while the mock backend "thinks". Streams these lines sequentially with a
fade-in and a green checkmark when done, ~700ms apart:

1. ✓ Reading roof geometry from satellite
2. ✓ Analyzing sun exposure across 365 days
3. ✓ Detecting obstructions (chimneys, skylights, vents)
4. ✓ Loading 3D building model
5. ✓ Matching to 1,593 similar German homes
6. ✓ Selecting components from catalog
7. ✓ Optimizing for your priorities

Then: 300ms delay → fade out narrative → reveal Scene + ResultsPanel.

Mock backend `/api/design` should `await new Promise(r => setTimeout(r, 4500))`
so the narrative actually has time to play.

## API contract — `types/api.ts`

This shape mirrors what Google Solar API's buildingInsights returns plus what
an LLM design step would add. Frontend imports from here; backend will too.

```ts
export type Vec3 = [number, number, number]
export type LatLng = { lat: number; lng: number }

export type RoofSegment = {
  id: string
  pitchDegrees: number
  azimuthDegrees: number    // 180 = south-facing
  areaMeters2: number       // actual surface area, tilted
  groundAreaMeters2: number // projected footprint
  centerLatLng: LatLng
  planeHeightMeters: number
}

export type Obstruction = {
  id: string
  type: 'chimney' | 'skylight' | 'vent' | 'antenna' | 'dormer'
  polygonLatLng: LatLng[]
  confidence: number
}

export type PanelPlacement = {
  id: string
  position: Vec3   // world-space meters, relative to GLB origin
  normal: Vec3     // unit vector, roof-face up direction
  orientation: 'LANDSCAPE' | 'PORTRAIT'
  segmentId: string
  yearlyEnergyKwh: number
}

export type BomLine = {
  category: 'module' | 'inverter' | 'battery' | 'mounting' | 'wallbox' | 'heatpump' | 'service'
  name: string
  brand?: string
  quantity: number
  unitPriceEur: number
}

export type Design = {
  packageId: string                       // e.g. "sigenergy_10_8_9"
  pv: { kwp: number; panelCount: number; positions: PanelPlacement[] }
  battery: { kwh: number; brand: string; model: string } | null
  heatpump: { kw: number; brand: string; model: string } | null
  wallbox: { kw: number; brand: string } | null
  bom: BomLine[]
  metrics: {
    annualGenerationKwh: number
    systemCostEur: number
    paybackYears: number
    co2SavedKgPerYear: number
    selfConsumptionPct: number
  }
  reasoning: { pv: string; battery: string; heatpump?: string }
}

export type Profile = {
  address: string
  monthlyBillEur: number
  inhabitants: number
  heating: 'gas' | 'oil' | 'district' | 'electric' | 'heatpump' | 'none'
  hasEv: boolean
  evKmPerYear?: number
}

export type DesignResponse = {
  location: { latLng: LatLng; buildingFootprint: LatLng[] }
  roof: { segments: RoofSegment[] }
  obstructions: Obstruction[]
  design: Design
}

export type RefineRequest = {
  currentDesign: Design
  intent: string  // free-form, e.g. "remove the battery", "make it cheaper"
}
```

## Mock backend — `app/api/design/route.ts`

POST handler that:

1. Reads the `Profile` body.
2. Sleeps 4500ms (lets the narrative play).
3. Returns a hardcoded but realistic `DesignResponse` for an Hauptstraße-style
   home: Sigenergy 10.8kWp + 9kWh package, 24 panels on a south-facing roof.
4. Vary panel count 16/20/24 by `monthlyBillEur` brackets so the demo can show
   different sizes.

For the panel positions: generate a 6×4 grid centered at world-space
`[0, 3, 0]`, spacing 1.65m × 1.05m. All have `normal = [0, 0.866, 0.5]`
(south-facing 30° slope). IDs `panel-0` through `panel-23`.

For the BOM, populate from the Reonic catalog (next section) — wrapper +
modules + inverter + battery + mounting + standard service fees, with
realistic prices. Sum to ~€22,500.

## `lib/mock/reonic-catalog.ts` — typed subset of the real catalog

```ts
export const PACKAGES = [
  {
    id: 'sigenergy_10_8_9',
    brand: 'Sigenergy',
    pvKwp: 10.8,
    batteryKwh: 9,
    inverterKw: 10,
    targetDemandKwh: [4500, 8000],
    estimatedPriceEur: [22000, 25000],
  },
  {
    id: 'goodwe_6_3_5',
    brand: 'GoodWe',
    pvKwp: 6.3,
    batteryKwh: 5,
    inverterKw: 5,
    targetDemandKwh: [0, 3500],
    estimatedPriceEur: [14000, 16000],
  },
  {
    id: 'sigenergy_13_5_9',
    brand: 'Sigenergy',
    pvKwp: 13.5,
    batteryKwh: 9,
    inverterKw: 12,
    targetDemandKwh: [6000, 12000],
    estimatedPriceEur: [26000, 30000],
  },
] as const

export const STANDARD_SERVICES = [
  { name: 'Travel & Logistics Flat Rate', priceEur: 350 },
  { name: 'Planning & Consulting', priceEur: 600 },
  { name: 'Install Inverter', priceEur: 480 },
  { name: 'AC Surge Protection', priceEur: 220 },
  { name: 'Grid Registration', priceEur: 180 },
  { name: 'Delivery to Site', priceEur: 290 },
  { name: 'Site Setup / Safety', priceEur: 340 },
]

export const MOUNTING_PER_PANEL_EUR = 50  // concrete tile default
export const PANEL_PRICE_EUR = 140         // 463W TOPCon glass-glass
```

## Mock backend — `app/api/refine/route.ts`

POST handler that takes `RefineRequest`, sleeps 1500ms, and returns an
adjusted `Design`. Implement three deterministic intents (string match,
case-insensitive):

- "remove battery" / "no battery" → set `design.battery = null`, drop battery
  + battery-install lines from BOM, reduce cost by €4,200, drop
  selfConsumption from 78% → 32%, leave panels untouched.
- "make it cheaper" / "cheaper" → swap to GoodWe 6.3kWp + 5kWh package,
  reduce panel count by ~half.
- "add EV charger" / "wallbox" → add a Wallbox 11kW v2 line (~€900 hardware +
  €700 install).

Anything else: return current design unchanged, with a `note` field saying
"Refinement understood as no-op for the prototype."

## Scene.tsx (the core)

```tsx
'use client'
import { Canvas } from '@react-three/fiber'
import { Suspense } from 'react'
import {
  OrbitControls, Environment, ContactShadows, Bounds, Html, useProgress
} from '@react-three/drei'
import {
  EffectComposer, N8AO, Bloom, Vignette, SMAA
} from '@react-three/postprocessing'
import { House } from './House'
import { SolarPanels } from './SolarPanels'
import type { PanelPlacement } from '@/types/api'

function Loader() {
  const { progress } = useProgress()
  return <Html center className="text-white">{progress.toFixed(0)}%</Html>
}

export function Scene({ panels, modelUrl }: { panels: PanelPlacement[]; modelUrl: string }) {
  return (
    <Canvas shadows dpr={[1, 2]} camera={{ position: [8, 5, 10], fov: 45 }} gl={{ antialias: true }}>
      <color attach="background" args={['#e8f0f7']} />
      <Suspense fallback={<Loader />}>
        <Bounds fit clip observe margin={1.3}>
          <House url={modelUrl} />
          <SolarPanels panels={panels} />
        </Bounds>
        <Environment preset="sunset" />
        <ContactShadows position={[0, -0.01, 0]} opacity={0.55} blur={2.5} scale={30} far={10} />
        <EffectComposer>
          <N8AO halfRes aoRadius={0.5} intensity={1.2} />
          <Bloom intensity={0.3} luminanceThreshold={1} mipmapBlur />
          <Vignette eskil={false} offset={0.1} darkness={0.6} />
          <SMAA />
        </EffectComposer>
      </Suspense>
      <OrbitControls makeDefault enableDamping maxPolarAngle={Math.PI / 2.1} target={[0, 1.5, 0]} />
    </Canvas>
  )
}
```

## House.tsx

```tsx
import { useGLTF } from '@react-three/drei'
export function House({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  return <primitive object={scene} />
}
```

## SolarPanels.tsx — instanced, oriented by normal, lifted 5cm

```tsx
import * as THREE from 'three'
import { Instances, Instance } from '@react-three/drei'
import { useMemo } from 'react'
import type { PanelPlacement } from '@/types/api'

const UP = new THREE.Vector3(0, 1, 0)

export function SolarPanels({ panels }: { panels: PanelPlacement[] }) {
  const poses = useMemo(() => panels.map(p => {
    const n = new THREE.Vector3(...p.normal).normalize()
    const q = new THREE.Quaternion().setFromUnitVectors(UP, n)
    const e = new THREE.Euler().setFromQuaternion(q)
    const pos = new THREE.Vector3(...p.position).addScaledVector(n, 0.05)  // anti z-fight
    return { id: p.id, pos: pos.toArray() as [number, number, number], rot: [e.x, e.y, e.z] as [number, number, number] }
  }), [panels])

  if (poses.length === 0) return null

  return (
    <Instances limit={500} range={poses.length} castShadow receiveShadow>
      <boxGeometry args={[1.65, 0.04, 1.0]} />
      <meshStandardMaterial color="#1a1a3e" metalness={0.85} roughness={0.3} envMapIntensity={1.2} />
      {poses.map(p => <Instance key={p.id} position={p.pos} rotation={p.rot} />)}
    </Instances>
  )
}
```

## ResultsPanel — what to display

Three hero numbers at the top, big and bold:
- `metrics.systemCostEur` formatted as €22,500
- `metrics.paybackYears` as "9.2 years"
- `metrics.annualGenerationKwh` as "9,800 kWh/yr"

Below, four expandable cards:
- **PV** — kWp, panel count, brand
- **Battery** — kWh, brand, model (or "No battery" if null)
- **Heat pump** — show only if recommended
- **Wallbox** — show only if recommended

Below that, a "Bill of Materials" disclosure (collapsed by default) listing
`bom[]` grouped by category.

Reasoning text from `design.reasoning.pv` etc. shown as a small italic line
under each card: *"Recommended 10.8 kWp because…"*

## RefineChat — bottom-overlaid

Single-line input, placeholder "Try: 'remove the battery' or 'make it cheaper'".
On submit, POST to `/api/refine` with currentDesign + intent. Brief inline
spinner while waiting (~1.5s). Update Design state; Scene re-renders panels;
ResultsPanel updates numbers.

Above the input, show a thin row of suggestion chips that just submit the
same text: "Remove battery" · "Make it cheaper" · "Add EV charger".

## Placeholder GLB

If no real house GLB is ready, use this Khronos sample:
`https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Avocado/glTF-Binary/Avocado.glb`

(Yes it's an avocado. Replace `public/house.glb` with a real house model
before demoing. The avocado proves the pipeline works.)

For a better placeholder while the team finds a real model, search Sketchfab
for "low poly house" CC0 — many usable options.

## Visual style

- Canvas: soft gradient background, dark accent.
- Sidebar: white #FFFFFF, borders zinc-200, text zinc-900, subtle shadows.
- Accent color: #00C853 (renewable green) for buttons, checkmarks, CTAs.
- Typography: Inter via `next/font/google`, weights 400/500/700.
- Numbers in the results panel: tabular-nums, large (40-56px for hero
  numbers).
- Cards: rounded-xl, subtle border, slight hover lift.

## Out of scope — DO NOT IMPLEMENT

- Real Google Maps / Solar API calls (mock all of it via /api/design).
- Real PDF extraction (file dropzone is decorative).
- Drag-and-drop panel repositioning.
- Authentication, database, save/load.
- Mobile responsive design.
- Multiple language support (German UI labels are fine where natural, but
  don't build a translation system).

## Self-test before declaring done

After scaffolding, the following must all work:

1. `npm run dev` starts without errors.
2. Page loads, sidebar visible, 3D canvas visible with the placeholder model
   centered and orbitable.
3. Clicking "Generate Design" without changing defaults: the narrative plays
   for ~5 seconds, then 24 panels appear on the roof, ResultsPanel populates
   with numbers, RefineChat appears.
4. Typing "remove the battery" in RefineChat: brief spinner, then ResultsPanel
   updates (battery card shows "No battery"), payback updates, panels
   unchanged.
5. Page can be reloaded freely without SSR crashes.
6. No console errors, no peer dep warnings.

Ship working code with no TODOs.

## --- END PROMPT ---
