from fastapi import FastAPI

from .config import get_settings
from .db import initialize_database
from .routes.episodes import router as episodes_router
from .routes.jobs import router as jobs_router
from .routes.speakers import router as speakers_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.ensure_storage()
    initialize_database(settings.database_path)

    app = FastAPI(title="AYQM Webapp API", version="0.1.0")
    app.include_router(episodes_router)
    app.include_router(jobs_router)
    app.include_router(speakers_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
