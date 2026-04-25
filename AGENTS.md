# Roofee Project Context

Roofee is a hackathon project for Reonic. It is a web application for planning and selling solar panel and home energy systems.

The primary user is a solar or energy system seller who needs a practical interface for assessing a home, preparing a bill of materials, and showing a credible result to a potential customer. The app should feel professional enough for customer-facing demos while still optimizing for seller workflows.

## Architecture

This repository is a monorepo with:

- `frontend/`: Next.js frontend
- `backend/`: Python FastAPI backend

The frontend should provide the main interactive experience: address entry, model upload, roof visualization, solar layout review, and BOM comparison. The backend should own geospatial lookup, model processing, deterministic calculations, external API integrations, and BOM generation.

## Core Product Flow

Users can start in one of two ways:

1. Enter an address.
2. Upload their own 3D model file.

For address-based flows, the backend should identify and fetch the exact house using Google APIs, including Google Maps API and Google Tiles API. The goal is to retrieve satellite imagery and 3D/building data precise enough to analyze the roof.

Once a house model is available, the system should determine usable roof area. This must account for obstructions and unusable surfaces such as windows, chimneys, roof fixtures, skylights, and other geometry that prevents panel placement.

The backend then applies deterministic calculations and rules, supported by external APIs such as PVGIS where useful. Inputs may include:

- available roof surface
- roof geometry and orientation
- model-derived square footage
- household size
- roof size
- location and solar irradiation data
- selected product/material constraints

The output should include a bill of materials generated from a fixed catalog of possible materials. This includes solar panels and related installation components. Panel count and panel dimensions must be constrained by what actually fits on the free roof surface.

When the BOM is ready, the app should present a few viable solar panel size/count variations. These options should all be physically plausible and fit on the available roof geometry.

Finally, the selected solar panel construction should be drawn onto the exact free roof space in the 3D model, so the seller and customer can inspect the proposed installation visually.

## Domain Principles

- Prefer deterministic calculations and explicit rules for engineering and BOM decisions.
- Treat AI or heuristic logic, if added later, as assistive only; do not let it silently override deterministic constraints.
- Keep a fixed, inspectable material catalog for BOM generation.
- Never propose panel layouts that do not fit the computed free roof area.
- Preserve traceability from user/model inputs to calculations, layout decisions, and BOM output.
- External APIs should be isolated behind backend services so they can be mocked or replaced.

## Frontend Principles

- Build a real working tool, not a marketing landing page.
- The interface should be useful for sellers first, but polished enough to show to potential customers.
- Prioritize clear workflows, direct manipulation of the model where possible, and comparison of viable system options.
- Use visualizations to make roof area, obstructions, panel placement, and BOM tradeoffs understandable.
- Keep customer-facing screens clean, credible, and visually refined.

## Backend Principles

- Keep geospatial lookup, model processing, solar calculations, and BOM generation in separate services/modules.
- Make calculation code testable with deterministic fixtures.
- Prefer typed request/response models for API contracts.
- Validate uploaded 3D files and address-derived model data before running placement or BOM calculations.
- Isolate Google Maps/Tiles, PVGIS, and other external API clients behind clear interfaces.

## Current Stack

- Frontend: Next.js, TypeScript
- Backend: Python, FastAPI
- Backend API docs should be available from the local FastAPI server at `/docs`.

## Development Notes

- This is a hackathon project, so favor simple, coherent vertical slices over speculative abstraction.
- Keep code organized so the prototype can evolve into a production architecture.
- When adding frontend code, also check `frontend/AGENTS.md` for Next.js-specific instructions.
- When adding backend code, prioritize clear service boundaries and testable calculation logic.
