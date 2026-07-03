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
- **Registry + deploy model**: build → `ghcr.io/aabichou/<app>` (packages are **private**).
  Deploy is **pull-based via Flux image-automation** (like kitchy): CI pushes a sortable tag
  `main-<ts>-<sha>`; an `ImageRepository`/`ImagePolicy`/`ImageUpdateAutomation` in `flux-system`
  scans ghcr, picks the newest, rewrites the `$imagepolicy` marker on the deployment's image
  line, commits it back to the `homelab-k3s` main branch, and Flux rolls the pod. **No CI
  reaches into the cluster; a push auto-deploys.** Pods pull ghcr directly using a `ghcr-pull`
  docker-registry secret (a read:packages PAT), created out-of-band in both `flux-system`
  (shared — already exists, for scanning) and the app namespace (for the pod).
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
`main`/`master`, build the root `Dockerfile` and push two tags —
`ghcr.io/${{ github.repository }}:main-<ts>-<sha>` (sortable, what the ImagePolicy selects)
and `:latest`. Built-in `GITHUB_TOKEN` (`packages: write`). Prune the compose/VM template
workflows; keep `build`, `test-backend`, `playwright`, `pre-commit`, `zizmor` (kitchy's set).

## Step 3 — k8s manifests (infra repo)
Create `~/code/infra/mainframe/k8s/clusters/tunis/services/<app>/` from `templates/k8s.yaml`
(one file, split it or keep it — it spans the `<app>` + `databases` namespaces, so **do NOT set
a kustomization `namespace:` transformer**; each resource names its own namespace). Replace the
`APPNAME` token and set hostnames + a real (non-`changethis`) `SECRET_KEY`/passwords. Resources:
namespace, `Secret` (SECRET_KEY, FIRST_SUPERUSER_PASSWORD, POSTGRES_PASSWORD), CNPG `Cluster`
+ its bootstrap secret (databases ns), Deployment (env incl. `POSTGRES_SERVER=<app>-pg-rw.databases`,
health probes on `/api/v1/utils/health-check/`, image line with the `$imagepolicy` marker +
`imagePullSecrets: [ghcr-pull]`), Service (:8000), IngressRoute, the **image-automation CRs**
(flux-system), kustomization (list `image-automation.yaml`). Then register: add `- <app>` to
`clusters/tunis/services/kustomization.yaml`.

## Step 4 — Go live (gh is authed as aabichou)
```bash
# 1. App repo -> CI builds the first main-<ts>-<sha> image
cd <app-src>
gh repo create aabichou/<app> --private --source=. --remote=origin --push
gh run watch                                   # wait for "Build & Push" to go green
TAG=$(gh api /user/packages/container/<app>/versions \
       -q '[.[].metadata.container.tags[]|select(startswith("main-"))]|sort|last')

# 2. Pod pull secret in the app namespace (scan secret already exists in flux-system)
export KUBECONFIG=~/code/infra/mainframe/k8s/kubeconfigs/k3s-k8s.yaml
kubectl create namespace <app> --dry-run=client -o yaml | kubectl apply -f -
kubectl -n <app> create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io --docker-username=aabichou --docker-password="$(gh auth token)" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Seed the deployment image line with $TAG (keep the marker), then push infra
sed -i '' "s#image: ghcr.io/aabichou/<app>:[^ ]*#image: ghcr.io/aabichou/<app>:${TAG}#" \
  ~/code/infra/mainframe/k8s/clusters/tunis/services/<app>/deployment.yaml
cd ~/code/infra/mainframe/k8s
git add clusters/tunis/services/<app> clusters/tunis/services/kustomization.yaml
git commit -m "services: add <app>" && git push
kubectl annotate --overwrite gitrepository flux-system -n flux-system reconcile.fluxcd.io/requestedAt="$(date +%s)"
kubectl annotate --overwrite kustomization services   -n flux-system fluxcd.io/reconcileAt="$(date +%s)"
```
From here it's **hands-off**: every push to the app repo builds a newer `main-<ts>-<sha>`, and
Flux image-automation bumps the marker + rolls the pod (~5–10m).

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
- **Private ghcr package needs a `ghcr-pull` secret in TWO places** (the packages are private,
  matching kitchy): one in `flux-system` for the `ImageRepository` scan (shared — already exists),
  one in the app namespace for the pod. Both are docker-registry secrets with a `read:packages`
  PAT, created out-of-band (a `gh auth token` works but can rotate — a dedicated PAT is more
  durable):
  ```bash
  kubectl -n flux-system create secret docker-registry ghcr-pull --docker-server=ghcr.io \
    --docker-username=aabichou --docker-password="$(gh auth token)"   # already present
  kubectl -n <app>       create secret docker-registry ghcr-pull --docker-server=ghcr.io \
    --docker-username=aabichou --docker-password="$(gh auth token)"
  ```
  (The old Zot mirror `10.43.205.186:5000/...` only serves **public** `aabichou/**` — kitchy
  dropped it because it's unreachable for private images; we pull ghcr directly instead.)
- **Seed the image tag.** The `$imagepolicy` marker line needs a real `main-<ts>-<sha>` tag to
  start (so the pod pulls before the automation's first ~5m scan). Grab it from
  `gh api /user/packages/container/<app>/versions` after the first CI build.
- **Image tags must match the ImagePolicy** `^main-(?P<ts>[0-9]+)-[0-9a-f]+$` (the CI produces
  exactly this); `:latest` is pushed too but the policy ignores it.
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
**Just push to the app repo.** CI builds a newer `main-<ts>-<sha>`; Flux image-automation
selects it, commits the marker bump to `homelab-k3s`, and rolls the pod automatically (~5–10m).
Nothing manual. (To force it: `kubectl -n flux-system annotate imagerepository/<app> --overwrite
reconcile.fluxcd.io/requestedAt="$(date +%s)"`.)

## Reusable base
`git clone -b homelab https://github.com/aabichou/full-stack-fastapi-template <new>` gives you a
current template with all the app-side boilerplate (Dockerfile, start.sh, static serving, CI) and
a `deploy/` folder of manifest templates already in place.
