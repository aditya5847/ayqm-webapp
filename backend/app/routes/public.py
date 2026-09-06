from fastapi import APIRouter, HTTPException, Query

from ..config import get_settings
from ..db import get_connection
from ..repositories import (
    get_episode,
    get_published_episode,
    list_public_trivia,
    list_published_episode_page,
    list_published_episodes,
    list_random_public_trivia,
    list_speakers,
)
from ..schemas import PublicEpisodeOut, PublicEpisodePageOut, PublicTriviaItemOut, SpeakerOut
from ..services.artwork import episode_artwork_response
from ..services.audio import episode_audio_response


router = APIRouter(prefix="/public", tags=["public"])


@router.get("/episodes", response_model=list[PublicEpisodeOut])
def public_episodes() -> list[dict]:
    with get_connection() as conn:
        return list_published_episodes(conn)


@router.get("/speakers", response_model=list[SpeakerOut])
def public_speakers() -> list[dict]:
    with get_connection() as conn:
        return list_speakers(conn)


@router.get("/episodes/archive", response_model=PublicEpisodePageOut)
def public_episode_archive(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    with get_connection() as conn:
        return list_published_episode_page(conn, page=page, page_size=page_size)


@router.get("/episodes/{episode_id}", response_model=PublicEpisodeOut)
def public_episode(episode_id: str) -> dict:
    with get_connection() as conn:
        episode = get_published_episode(conn, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/episodes/{episode_id}/artwork", response_model=None)
def public_episode_artwork(episode_id: str):
    settings = get_settings()
    with get_connection() as conn:
        episode = get_episode(conn, episode_id)
    if episode is None or not episode["is_published"] or not episode.get("artwork_object_key"):
        raise HTTPException(status_code=404, detail="Episode artwork not found")

    return episode_artwork_response(episode, settings)


@router.get("/episodes/{episode_id}/audio", response_model=None)
def public_episode_audio(episode_id: str):
    settings = get_settings()
    with get_connection() as conn:
        episode = get_episode(conn, episode_id)
    if episode is None or not episode["is_published"]:
        raise HTTPException(status_code=404, detail="Episode audio not found")

    return episode_audio_response(episode, settings)


@router.get("/episodes/{episode_id}/trivia", response_model=list[PublicTriviaItemOut])
def public_episode_trivia(episode_id: str) -> list[dict]:
    with get_connection() as conn:
        if get_published_episode(conn, episode_id) is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        return list_public_trivia(conn, episode_id=episode_id)


@router.get("/trivia", response_model=list[PublicTriviaItemOut])
def public_trivia(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    with get_connection() as conn:
        return list_public_trivia(conn, limit=limit, offset=offset)


@router.get("/trivia/random", response_model=list[PublicTriviaItemOut])
def random_public_trivia(
    limit: int = Query(default=4, ge=1, le=24),
    exclude_id: list[str] = Query(default=[]),
    q: str | None = Query(default=None, min_length=1),
) -> list[dict]:
    query = q.strip() if q and q.strip() else None
    with get_connection() as conn:
        return list_random_public_trivia(conn, limit=limit, exclude_ids=exclude_id, query=query)
