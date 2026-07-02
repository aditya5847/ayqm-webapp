from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import initialize_database
from .db import get_connection
from .routes.episodes import router as episodes_router
from .routes.auth import router as auth_router
from .routes.jobs import router as jobs_router
from .routes.imports import router as imports_router
from .routes.public import router as public_router
from .routes.speakers import router as speakers_router
from .routes.trivia import router as trivia_router
from .routes.worker import router as worker_router
from .services.rss_import import resume_pending_feed_imports
from .services.backups import start_backup_scheduler


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_runtime()
    settings.ensure_storage()
    initialize_database(settings.database_path)

    app = FastAPI(title="AYQM Webapp API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def reject_untrusted_browser_origins(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            settings.environment == "production"
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and origin not in settings.cors_origins
        ):
            return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
        return await call_next(request)
    app.include_router(auth_router)
    app.include_router(episodes_router)
    app.include_router(jobs_router)
    app.include_router(imports_router)
    app.include_router(speakers_router)
    app.include_router(trivia_router)
    app.include_router(public_router)
    app.include_router(worker_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness() -> dict[str, str]:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready", "storage": settings.storage_backend}

    if settings.environment == "production":
        resume_pending_feed_imports(settings)
        if settings.backup_enabled:
            start_backup_scheduler(settings)

    return app


app = create_app()
