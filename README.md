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
