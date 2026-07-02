from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..auth import require_admin
from ..config import get_settings
from ..db import get_connection
from ..schemas import FeedImportOut, FeedImportRequest
from ..services.rss_import import create_feed_import, get_feed_import, run_feed_import


router = APIRouter(prefix="/imports", tags=["imports"], dependencies=[Depends(require_admin)])


@router.post("/rss", response_model=FeedImportOut, status_code=status.HTTP_202_ACCEPTED)
def start_rss_import(request: FeedImportRequest, background_tasks: BackgroundTasks) -> dict:
    settings = get_settings()
    feed_url = str(request.feed_url) if request.feed_url else settings.rss_feed_url
    record = create_feed_import(feed_url, request.dry_run)
    background_tasks.add_task(run_feed_import, record["id"], settings)
    return record


@router.get("/rss/{import_id}", response_model=FeedImportOut)
def read_rss_import(import_id: str) -> dict:
    with get_connection() as conn:
        record = get_feed_import(conn, import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="RSS import not found")
    return record
