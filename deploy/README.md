# Homelab (tunis k3s) deploy base

This branch (`homelab`) is `fastapi/full-stack-fastapi-template` + the boilerplate to deploy it
as a **single container** to the homelab `tunis` cluster. Start a new project by cloning it:

```bash
git clone -b homelab https://github.com/aabichou/full-stack-fastapi-template myapp
cd myapp && rm -rf .git && git init
```

## What's added on top of upstream
- **`Dockerfile`** (root): bun builds the SPA → FastAPI serves it same-origin. Build with
  `VITE_API_URL=""` (empty ⇒ the generated client calls `/api/v1` on the same host).
- **`backend/scripts/start.sh`**: wait-for-db → `alembic upgrade head` → seed → `fastapi run`.
  (Container CMD.)
- **`backend/app/main.py`**: appended SPA static serving (guarded by `backend/static/` existing,
  so local dev is unaffected).
- **`.dockerignore`**, **`.github/workflows/homelab-build.yml`** (builds + pushes
  `ghcr.io/<owner>/<repo>:{sha,latest}`).
- **`deploy/k8s.yaml`**: templated Flux/Traefik/CNPG manifests (replace `APPNAME`).

## Deploy
Full procedure, cluster constants, go-live commands, and gotchas are in the Claude Code skill
**`deploy-fastapi-to-homelab-k8s`** (`~/.claude/skills/`). In short:
1. Push the app repo → CI builds & pushes `ghcr.io/<owner>/<app>:main-<ts>-<sha>` to ghcr.
2. Copy `deploy/k8s.yaml` → `homelab-k3s` repo `clusters/tunis/services/APPNAME/`, replace
   `APPNAME` + secrets/hosts, register it in `services/kustomization.yaml`, push → Flux deploys.
3. App comes up at `https://APPNAME.ts.k8s.cloud.abichou.tn`.

**Deploy is pull-based** (Flux image-automation): after that one-time setup, every push to the
app repo builds a newer `main-<ts>-<sha>`; the cluster picks it up, bumps the deployment marker,
and rolls the pod automatically (~5–10m). No manual redeploy.

Gotchas worth knowing up front: keep `VITE_API_URL` empty; deploy with `ENVIRONMENT=staging`
and real (non-`changethis`) secrets; a private ghcr package needs a pull secret (or make it
public); the `services` Flux Kustomization's `wait: true` can pin the old revision if a pod is
unhealthy (suspend/resume to unstick). See the skill for details.
