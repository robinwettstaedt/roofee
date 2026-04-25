# Roofee

Hackathon monorepo with a Next.js frontend and a FastAPI backend.

## Structure

- `frontend`: Next.js app with TypeScript, App Router, Tailwind, and ESLint
- `backend`: FastAPI REST API
- `backend/data`: local data files consumed by backend services

## Getting started

Install frontend dependencies:

```bash
npm install
```

Install backend dependencies:

```bash
npm run install:backend
```

Run the apps in separate terminals:

```bash
npm run dev:frontend
npm run dev:backend
```

Frontend: `http://localhost:3000`

Backend: `http://localhost:8000`

API docs: `http://localhost:8000/docs`

## What's where

```
frontend/
  src/app/                 Next.js App Router entry + global styles + mock /api/design,/api/refine
  src/components/          AddressIntake, Designer, BomSidebar, Scene/House/RoofPlacedPanels (3D), …
  src/lib/                 catalog, format helpers, client-side variant synthesizer
  src/types/api.ts         Shared API contract (Profile, Design, DesignResponse, BomLine, …)
  public/house.glb         Demo 3D model used by Scene
backend/
  app/api/routes/          FastAPI routers (health, catalog, recommendations)
  app/services/            project input validation, component catalog, PVGIS client
  app/models/              Pydantic request/response models
  data/                    Local data the catalog service consumes
```

The frontend currently produces the BOM via mock routes in `frontend/src/app/api/` — see [CLAUDE.md](CLAUDE.md) for the seam where the real backend will plug in.
