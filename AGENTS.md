# AGENTS.md — homelab starter (idea → deployed app)

This is `fastapi/full-stack-fastapi-template` + everything needed to ship it as a **single
container** to the homelab `tunis` k3s cluster. Clone the `homelab` branch and you have a
running-locally, deployable full-stack app (FastAPI + React/Vite + Postgres) on day zero.

```bash
git clone -b homelab https://github.com/aabichou/full-stack-fastapi-template myapp
cd myapp && rm -rf .git && git init
```

## The pipeline: idea → deployed
1. **Scaffold your domain.** Add SQLModel entities, API routes, services, an Alembic migration,
   and frontend pages (see Conventions). Regenerate the TS client after backend changes.
2. **Run it locally.** `docker compose up -d` (or the dev servers). Iterate.
3. **Deploy.** Run the embedded skill **`deploy-fastapi-to-homelab-k8s`** (see below). It builds
   a single image → ghcr → Flux applies the manifests → your app is live at
   `https://<app>.ts.k8s.cloud.abichou.tn`.

That's the whole loop. Build features → deploy skill → shareable URL for the team.

## Project layout
```
backend/            FastAPI + SQLModel (Alembic migrations, JWT auth)
  app/models.py       all SQLModel entities (one file)
  app/api/routes/     one file per feature; register in app/api/main.py
  app/api/deps.py     SessionDep, CurrentUser, auth helpers
  app/services/       cross-feature business logic
  app/main.py         app + (homelab) SPA static serving
  scripts/start.sh    prod entrypoint: wait-db -> migrate -> seed -> serve
frontend/           React/Vite/TS, Tailwind + shadcn/ui, TanStack Router+Query
  src/routes/_layout/ file-based routes (pages)
  src/client/         AUTO-GENERATED API client (do not hand-edit)
Dockerfile          single-container image (SPA built + served by FastAPI)
.github/workflows/homelab-build.yml   CI: build & push ghcr image
deploy/k8s.yaml     templated Flux/Traefik/CNPG manifests (replace APPNAME)
.claude/skills/deploy-fastapi-to-homelab-k8s/   the deploy runbook + templates
```

## Conventions (match these)
- **Models** (`backend/app/models.py`): `XBase / XCreate / XUpdate / X(table=True) / XPublic /
  XsPublic`. UUID pks, `created_at` via the shared helper.
- **Routes**: `backend/app/api/routes/<feature>.py` → `APIRouter(prefix, tags)`, deps
  `SessionDep` / `CurrentUser`; register the router in `backend/app/api/main.py`.
- **Migrations**: `cd backend && alembic revision --autogenerate -m "..."`. **Native-enum trap**:
  `op.add_column` with `sa.Enum` does NOT emit `CREATE TYPE` — create the type explicitly
  (`sa.Enum(..., name=...).create(op.get_bind(), checkfirst=True)`, column `create_type=False`)
  and give new NOT-NULL columns a `server_default`.
- **Frontend**: pages under `src/routes/_layout/`; data via TanStack Query against the generated
  client. After changing backend endpoints, regenerate: `bash scripts/generate-client.sh`.
- **Same-origin in prod**: the SPA is served by FastAPI, so build with `VITE_API_URL=""` (empty).
  The Dockerfile/CI already do this — don't set it to `/api/v1` (double-prefixes) or a host.

## Deploying (the skill does this)
Invoke **`deploy-fastapi-to-homelab-k8s`** (embedded in `.claude/skills/`). It knows the cluster
constants and does: create the ghcr repo + CI build, copy `deploy/k8s.yaml` into the
`homelab-k3s` Flux repo (`clusters/tunis/services/<app>/`, replace `APPNAME`, set secrets/hosts),
register the app, push, reconcile Flux, verify.

**CI/CD is pull-based** (Flux image-automation, like kitchy): CI only builds & pushes
`ghcr.io/<owner>/<app>:main-<ts>-<sha>`; the cluster scans ghcr, rewrites the deployment's image
marker, commits it back, and rolls the pod. After the one-time setup, **every push to the app
repo auto-deploys** — no manual rollout.

Key facts it encodes (so you don't have to): Traefik `IngressRoute` + wildcard TLS (`tls: {}`),
CNPG Postgres in the `databases` namespace, Zot mirror at `10.43.205.186:5000` (public packages)
vs a pull secret for private, `ENVIRONMENT=staging` + real secrets (never `changethis`), and the
`wait: true` Flux gotcha. Full detail: `.claude/skills/deploy-fastapi-to-homelab-k8s/SKILL.md`
and `deploy/README.md`.
