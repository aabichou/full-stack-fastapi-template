import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


# ── Homelab single-container deploy: serve the built SPA same-origin ──────────
# The Docker image copies frontend/dist -> backend/static; FastAPI serves it and
# falls back to index.html for client-side routes. Guarded so local dev (separate
# Vite server) is unaffected. tags=["spa"] is required by custom_generate_unique_id.
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles as _StaticFiles  # noqa: E402
from starlette.responses import FileResponse as _FileResponse  # noqa: E402

_static_dir = _Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount(
        "/assets", _StaticFiles(directory=_static_dir / "assets"), name="assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False, tags=["spa"])
    async def serve_spa(full_path: str) -> _FileResponse:
        candidate = _static_dir / full_path
        if full_path and candidate.is_file():
            return _FileResponse(candidate)
        return _FileResponse(_static_dir / "index.html")
