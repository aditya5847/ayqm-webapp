from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from ..config import Settings
from ..storage import get_object_storage


def episode_artwork_response(episode: dict, settings: Settings):
    object_key = episode.get("artwork_object_key")
    if not object_key:
        raise HTTPException(status_code=404, detail="Episode artwork not found")

    storage = get_object_storage(settings)
    signed_url = storage.presign_get(object_key)
    headers = {"Cache-Control": "public, max-age=300"}
    if signed_url:
        return RedirectResponse(signed_url, status_code=307, headers=headers)

    root = settings.upload_root.resolve()
    path = (root / object_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Episode artwork not found")
    return FileResponse(
        path,
        media_type=episode.get("artwork_content_type") or "application/octet-stream",
        headers=headers,
    )
