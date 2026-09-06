from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from ..config import Settings
from ..storage import get_object_storage


def episode_audio_response(episode: dict, settings: Settings):
    """Return a public-safe response for an already publication-gated episode."""
    object_key = episode.get("audio_object_key")
    headers = {"Cache-Control": "public, max-age=3600"}
    storage = get_object_storage(settings)

    if object_key:
        signed_url = storage.presign_get(object_key)
        if signed_url:
            return RedirectResponse(signed_url, status_code=307, headers=headers)
        root = settings.upload_root.resolve()
        path = (root / object_key).resolve()
    else:
        path = Path(episode["audio_path"]).resolve()
        root = settings.upload_root.resolve()

    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Episode audio not found")

    return FileResponse(
        path,
        media_type=episode.get("audio_content_type") or "audio/mpeg",
        headers=headers,
    )
