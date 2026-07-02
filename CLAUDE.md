# CLAUDE.md

Homelab starter: FastAPI + React + Postgres, single-container deployable to the `tunis` k3s
cluster. **Read `AGENTS.md`** for the full project layout, conventions, and the idea→deployed
pipeline — this file adds the Claude Code specifics.

## Deploying — use the embedded skill
This repo ships the skill **`deploy-fastapi-to-homelab-k8s`** in `.claude/skills/`. When the user
asks to deploy / preview / ship this app to the homelab (or add it to the `homelab-k3s` Flux
repo), **invoke that skill** — do not improvise. It carries the cluster constants, the go-live
commands, and the non-obvious gotchas (Flux `wait: true`, private-package pulls, the
`changethis`/`ENVIRONMENT` guard, empty `VITE_API_URL`, the `tags=["spa"]` requirement).

## The loop
1. Build the domain (models → routes → services → migration → frontend pages). Match the
   patterns in `AGENTS.md`.
2. Verify locally: `docker compose up -d`, then exercise the API/UI.
3. Deploy via the skill → app is live at `https://<app>.ts.k8s.cloud.abichou.tn`.

## Working notes
- **Regenerate the client** after any backend endpoint/model change:
  `bash scripts/generate-client.sh` (needs the API reachable). The frontend imports from
  `frontend/src/client` — never hand-edit those `.gen.ts` files.
- **Migrations, not create_all.** Add an Alembic revision for every model change; mind the
  native-enum `CREATE TYPE` trap and `server_default` for NOT-NULL columns (see `AGENTS.md`).
- **Prod is same-origin**: keep `VITE_API_URL` empty; FastAPI serves the built SPA (`app/main.py`)
  and the API under `/api/v1`.
- **Secrets**: deploy with `ENVIRONMENT=staging` and real values — the config *rejects*
  `changethis` outside `local`.
- Don't commit real secrets to git here beyond the preview-grade placeholders in `deploy/k8s.yaml`.
