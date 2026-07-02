---
name: deploy-fastapi-to-homelab-k8s
description: Deploy a full-stack FastAPI + React (+Postgres) app — one based on fastapi/full-stack-fastapi-template — to the homelab `tunis` k3s cluster as a single-container preview. Covers the boilerplate to add (single-container Dockerfile, start.sh, SPA static serving, GitHub Actions build to ghcr) and the Flux GitOps manifests (namespace, CNPG Postgres, Traefik IngressRoute, wildcard TLS), plus the exact go-live steps and the non-obvious gotchas. Use when deploying/previewing a FastAPI-template app to the homelab, adding a new app to the homelab-k3s Flux repo, or writing its CI. A ready-to-clone base lives on the `homelab` branch of aabichou/full-stack-fastapi-template.
---

# Deploy a FastAPI-template app to the homelab k8s (`tunis`)

Turns a `fastapi/full-stack-fastapi-template`-based repo (FastAPI backend + React/Vite
frontend + Postgres) into a **single container** (FastAPI serves the built SPA same-origin),
built by GitHub Actions to ghcr, and deployed to the `tunis` k3s cluster via Flux.

Boilerplate templates ship with this skill under `templates/`. A pre-baked base is the
**`homelab` branch of `aabichou/full-stack-fastapi-template`** — clone that to skip the
app-side setup.

## Cluster facts (constants — don't re-discover)
- **GitOps**: Flux. Sync repo `github.com/aabichou/homelab-k3s`, path `clusters/tunis`.
  Local working copy: `~/code/infra/mainframe/k8s`. Apps live in `clusters/tunis/services/<app>/`
  and are registered by adding `- <app>` to `clusters/tunis/services/kustomization.yaml`.
- **Ingress**: Traefik `IngressRoute` (`traefik.io/v1alpha1`), entrypoint `websecure`, `tls: {}`.
  No per-app cert — a cluster wildcard cert (`internal-wildcard-tls`, cert-manager +
  `letsencrypt-cloudflare`) is served via the default `TLSStore`.
- **Hostnames**: `<app>.ts.k8s.cloud.abichou.tn` (Tailscale-private, what the team uses) and/or
  `<app>.external.k8s.cloud.abichou.tn` (public via frpc tunnel). Same wildcard cert covers both.
- **Registry**: build → `ghcr.io/aabichou/<app>`. In-cluster Zot mirror at
  `10.43.205.186:5000` **only serves PUBLIC `aabichou/**` packages anonymously**. So either
  make the ghcr package **public** and use `image: 10.43.205.186:5000/aabichou/<app>:latest`
  (no pull secret — the convention), **or** keep it private and pull `ghcr.io/aabichou/<app>`
  directly with an `imagePullSecret` (see Gotchas).
- **Postgres**: CloudNative-PG operator. Create a `Cluster` CR in the **`databases`** namespace;
  reach it at `<name>-rw.databases:5432`.
- **Storage**: `local-path` (default). **Secrets**: plaintext committed `Secret` (no SOPS yet)
  — fine for previews, rotate before anything real.
- **Kubeconfig**: `~/code/infra/mainframe/k8s/kubeconfigs/k3s-k8s.yaml` (needs Tailscale up).

## Step 1 — Make the app a single container (app repo)
Copy from `templates/` (already present if you cloned the `homelab` fork branch):
- **`Dockerfile`** (repo root): bun builds the SPA → FastAPI serves it. Build arg
  `VITE_API_URL=""` (empty ⇒ same-origin `/api/v1`; the generated client already prefixes
  `/api/v1`, so a non-empty base double-prefixes — keep it empty).
- **`backend/scripts/start.sh`**: wait-for-db → `alembic upgrade head` → seed
  (`python app/initial_data.py`) → `fastapi run`. Used as the container CMD.
- **`.dockerignore`**.
- **Serve the SPA from FastAPI** — append to `backend/app/main.py` (after `include_router`):
  ```python
  from pathlib import Path
  from fastapi.staticfiles import StaticFiles
  from starlette.responses import FileResponse
  _static = Path(__file__).resolve().parent.parent / "static"
  if _static.is_dir():
      app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")
      @app.get("/{full_path:path}", include_in_schema=False, tags=["spa"])  # tags REQUIRED
      async def serve_spa(full_path: str) -> FileResponse:
          f = _static / full_path
          return FileResponse(f if full_path and f.is_file() else _static / "index.html")
  ```
  The `tags=["spa"]` is mandatory if the app sets a `generate_unique_id_function` that reads
  `route.tags[0]` (the template does) — without it startup crashes with `IndexError`.

## Step 2 — CI to ghcr (app repo)
Add **`.github/workflows/build.yml`** (from `templates/github-build.yml`): on push to
`main`/`master`, build the root `Dockerfile` and push `ghcr.io/${{ github.repository }}:{sha,latest}`.
Uses the built-in `GITHUB_TOKEN` (`packages: write`).

## Step 3 — k8s manifests (infra repo)
Create `~/code/infra/mainframe/k8s/clusters/tunis/services/<app>/` from `templates/k8s.yaml`
(one file, split it or keep it — it spans the `<app>` + `databases` namespaces, so **do NOT set
a kustomization `namespace:` transformer**; each resource names its own namespace). Replace the
`APPNAME` token and set hostnames + a real (non-`changethis`) `SECRET_KEY`/passwords. Resources:
namespace, `Secret` (SECRET_KEY, FIRST_SUPERUSER_PASSWORD, POSTGRES_PASSWORD), CNPG `Cluster`
+ its bootstrap secret (databases ns), Deployment (env incl. `POSTGRES_SERVER=<app>-pg-rw.databases`,
health probes on `/api/v1/utils/health-check/`), Service (:8000), IngressRoute, kustomization.
Then register: add `- <app>` to `clusters/tunis/services/kustomization.yaml`.

## Step 4 — Go live (gh is authed as aabichou)
```bash
# App repo -> triggers CI to build the image
cd <app-src>
gh repo create aabichou/<app> --private --source=. --remote=origin --push
gh run watch                                   # wait for "Build and Push" to go green

# Infra repo -> Flux deploys
cd ~/code/infra/mainframe/k8s
git add clusters/tunis/services/<app> clusters/tunis/services/kustomization.yaml
git commit -m "services: add <app>" && git push

export KUBECONFIG=~/code/infra/mainframe/k8s/kubeconfigs/k3s-k8s.yaml
kubectl annotate --overwrite gitrepository flux-system -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
kubectl annotate --overwrite kustomization services   -n flux-system fluxcd.io/reconcileAt="$(date +%s)"
```

## Step 5 — Verify
```bash
kubectl -n databases get cluster <app>-pg          # "Cluster in healthy state"
kubectl -n <app> get pods                          # 1/1 Running
kubectl -n <app> logs deploy/<app> | tail          # upgrade -> seeding -> Uvicorn running
curl -sI https://<app>.ts.k8s.cloud.abichou.tn/    # 200 (serves the SPA; Tailscale required)
```

## Gotchas (all learned the hard way)
- **`wait: true` blocks new revisions.** The `services` Kustomization waits for health; a
  crash-looping/ImagePullBackOff pod pins Flux at the *old* revision, so pushes don't apply.
  Unstick: `kubectl patch kustomization services -n flux-system --type merge -p '{"spec":{"suspend":true}}'`
  then the same with `false`, then re-annotate to reconcile.
- **Private ghcr package won't pull via the Zot mirror** (`unauthorized`/`NotFound`). Either:
  (a) make the package **public** (Package settings → Change visibility — GitHub has **no REST
  endpoint** for this, UI only) and use the `10.43.205.186:5000/...` mirror image; or
  (b) keep private and pull ghcr directly:
  ```bash
  kubectl create secret docker-registry ghcr-<app> -n <app> \
    --docker-server=ghcr.io --docker-username=aabichou --docker-password="$(gh auth token)"
  ```
  then set `image: ghcr.io/aabichou/<app>:latest` + `imagePullSecrets: [{name: ghcr-<app>}]`.
  The gh CLI token has `read:packages` and works; note it's not GitOps-tracked and can expire —
  the durable choice is a public package.
- **`ENVIRONMENT` vs `changethis`.** The template's config *raises* (not warns) on any
  `changethis` secret unless `ENVIRONMENT=local`. Deploy with `ENVIRONMENT=staging` and real
  values for `SECRET_KEY`, `POSTGRES_PASSWORD`, `FIRST_SUPERUSER_PASSWORD`.
- **`VITE_API_URL` must be empty** for same-origin (see Step 1).
- **Alembic + native enums**: `op.add_column` with a `sa.Enum` does NOT emit `CREATE TYPE`
  (only `create_table` does). Create the enum type explicitly (`sa.Enum(..., name=...).create(op.get_bind(), checkfirst=True)`)
  and mark the column `create_type=False`. Also give new NOT-NULL columns a `server_default`
  so the migration is safe on populated tables.
- **`.ts.` host needs Tailscale**; `.external.` is public via frpc (may need per-host tunnel/DNS
  wiring — verify before telling a non-tailnet team to use it).

## Redeploy after a code change
Push to `main` → CI rebuilds `:latest` → `kubectl -n <app> rollout restart deploy/<app>`
(pod re-pulls `:latest`). More deterministic: pin `image:` to the new `:<sha>` and commit the
infra repo (GitOps drives the rollout).

## Reusable base
`git clone -b homelab https://github.com/aabichou/full-stack-fastapi-template <new>` gives you a
current template with all the app-side boilerplate (Dockerfile, start.sh, static serving, CI) and
a `deploy/` folder of manifest templates already in place.
