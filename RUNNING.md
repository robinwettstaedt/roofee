# Running Roofee Locally

Practical, copy-paste instructions for getting both servers up. Pairs with
`README.md` (overview) and `backend/README.md` (architecture).

## Prerequisites

- **Node.js** matching `.tool-versions` (currently `nodejs 22.21.1`). If you use
  `asdf`, run `asdf install` from the repo root once.
- **Python 3.11+**. The backend currently builds its venv with whatever
  `python3` resolves to on `PATH`. Python 3.13 is known good.
- A working internet connection on first install (PyPI, npm, Hugging Face).

## One-time setup

From the repo root (`roofee/`):

```bash
npm install                  # frontend deps
npm run install:backend      # creates backend/.venv and installs backend[dev]
```

Then create the two env files (both are git-ignored):

**`backend/.env`** — copy from `backend/.env.example` and fill in:

```bash
ROOFEE_GOOGLE_API_KEY="<server-side Google API key>"
ROOFEE_GOOGLE_MAPS_API_KEY="<same key, or a separate Maps-only key>"
```

The key needs **Geocoding API**, **Solar API**, and **Map Tiles API** enabled
in the Google Cloud project. The remaining `ROOFEE_*` defaults in
`.env.example` are fine to keep.

**`frontend/.env.local`**:

```bash
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY="<browser-restricted Maps JS / Places key>"
BACKEND_URL="http://localhost:8000"
```

Use a **separate, browser-restricted** key here because `NEXT_PUBLIC_*` values
are bundled into the client.

## Run the dev loop

Two terminals, repo root in both:

```bash
# terminal 1
npm run dev:backend     # FastAPI on http://localhost:8000

# terminal 2
npm run dev:frontend    # Next.js on http://localhost:3000
```

Smoke-test the backend:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

Interactive API docs: <http://localhost:8000/docs>.

## Backend tests

```bash
npm run test:backend
```

This runs `backend/.venv/bin/pytest`. Some tests in `test_recommendations.py`
depend on the local 3D-Modell GLB fixtures under `backend/data/Exp 3D-Modells/`
and will fail if those aren't present — that's a fixture problem, not a code
regression.

## Why `npm run dev:backend` is now wired through `.venv/bin/uvicorn`

The repo previously used a bare `uvicorn ...` in `dev:backend`. On a machine
with a system-wide `uvicorn` on `PATH` (e.g. `/Library/Frameworks/Python.framework/Versions/3.12/bin/uvicorn`)
that copy was picked instead of the venv's, leading to:

```
ModuleNotFoundError: No module named 'pydantic_settings'
```

…even though `backend/.venv` had everything installed. The script now invokes
`backend/.venv/bin/uvicorn` (and `backend/.venv/bin/pytest` for tests)
explicitly, so the venv is always used regardless of `PATH`.

If you ever see that error again, the venv is likely missing or stale —
reinstall with:

```bash
rm -rf backend/.venv
npm run install:backend
```

## Common gotchas

- **Port 8000 already in use.** A previous `--reload` parent process can stay
  alive after a crash. Kill it:
  ```bash
  lsof -ti:8000 | xargs kill -9
  ```
- **Frontend logs `503` on `/api/catalog`, `/api/recommendations`, etc.**
  The Next.js routes proxy to `BACKEND_URL`. Either the backend isn't running
  or `BACKEND_URL` in `frontend/.env.local` doesn't match the address uvicorn
  is bound to.
- **`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY not set` in the browser console.** Set it
  in `frontend/.env.local` and restart `npm run dev:frontend` (Next.js only
  reads env files at startup).
- **`asdf: No version is set for command node`.** You're missing the Node
  version pinned in `.tool-versions`. Run `asdf install` from the repo root,
  or install Node 22.21.1 some other way.
- **Heavy ML deps (TensorFlow, ultralytics).** First import after a fresh venv
  may take a while. The RID obstruction model only loads on the first
  `POST /api/roof/obstructions` request, not at server startup.

## Useful endpoints to verify the stack

```bash
# health
curl http://localhost:8000/api/health

# building lookup (Google Solar API; needs ROOFEE_GOOGLE_*_API_KEY)
curl -X POST http://localhost:8000/api/location/building \
  -H 'Content-Type: application/json' \
  -d '{"address":"1600 Amphitheatre Parkway, Mountain View, CA"}'
```

If the building lookup returns `400 missing api key`, the backend isn't
reading `backend/.env` — confirm the file exists and you restarted uvicorn
after editing it.
