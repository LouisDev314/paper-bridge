# paper-bridge

Monorepo with a single Next.js frontend app and an untouched FastAPI backend.

## Repository layout

- `apps/web`: Next.js app (App Router)
- `backend`: FastAPI backend
- `pnpm-workspace.yaml`: workspace definition
- `pnpm-lock.yaml`: single workspace lockfile

## Frontend local development

1. Install dependencies from repo root:

```bash
pnpm -w install
```

2. Configure frontend env:

```bash
cp apps/web/.env.example apps/web/.env.local
```

3. Set required env value in `apps/web/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

4. Run the frontend from repo root:

```bash
pnpm -w dev
```

5. Production checks from repo root:

```bash
pnpm -w lint
pnpm -w typecheck
pnpm -w test
pnpm -w build
```

## Frontend env vars

Required:

- `NEXT_PUBLIC_API_BASE_URL`: Base URL of the FastAPI backend. Browser code calls only `/api/pb/*`; server proxy forwards to this backend URL.

## Vercel deployment (monorepo)

Use Vercel project settings:

- Framework Preset: `Next.js`
- Root Directory: `apps/web`
- Install Command: `pnpm -w install`
- Build Command: `pnpm -w build`
- Output Directory: leave default (Next.js `.next`)
- Node.js: 20+

Also add environment variable in Vercel project settings:

- `NEXT_PUBLIC_API_BASE_URL` = your deployed backend URL

No `vercel.json` is required for this setup.
