from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_admin
from ..config import get_settings
from ..db import get_connection
from ..repositories import (
    delete_trivia_item,
    get_speaker,
    get_trivia_item,
    speaker_ids_for_episode,
    update_trivia_item,
)
from ..schemas import TriviaItemOut, TriviaItemUpdate, TriviaRephraseOut
from ..services.rephrase import RephraseConfigurationError, RephraseProviderError, rephrase_trivia


router = APIRouter(prefix="/trivia", tags=["trivia"], dependencies=[Depends(require_admin)])


@router.patch("/{trivia_id}", response_model=TriviaItemOut)
def update_trivia(trivia_id: str, request: TriviaItemUpdate) -> dict:
    changes = request.model_dump(exclude_unset=True)
    for field in ("type", "confidence"):
        if field in changes:
            value = changes[field]
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(status_code=422, detail=f"{field} must be a non-empty string")
            changes[field] = value.strip()
    if "keywords" in changes:
        if changes["keywords"] is None:
            raise HTTPException(status_code=422, detail="keywords must be a list")
        changes["keywords"] = list(dict.fromkeys(word.strip() for word in changes["keywords"] if word.strip()))

    with get_connection() as conn:
        item = get_trivia_item(conn, trivia_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Trivia item not found")
        if "asker_speaker_id" in changes and changes["asker_speaker_id"] is not None:
            speaker_id = changes["asker_speaker_id"]
            if get_speaker(conn, speaker_id) is None:
                raise HTTPException(status_code=422, detail={"unknown_speaker_id": speaker_id})
            if speaker_id not in speaker_ids_for_episode(conn, item["episode_id"]):
                raise HTTPException(
                    status_code=422,
                    detail={"speaker_id_not_selected_for_episode": speaker_id},
                )
        updated = update_trivia_item(conn, trivia_id, changes)
    return updated


@router.delete("/{trivia_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trivia(trivia_id: str) -> None:
    with get_connection() as conn:
        if delete_trivia_item(conn, trivia_id) is None:
            raise HTTPException(status_code=404, detail="Trivia item not found")


@router.post("/{trivia_id}/rephrase", response_model=TriviaRephraseOut)
def rephrase_trivia_route(trivia_id: str) -> TriviaRephraseOut:
    with get_connection() as conn:
        item = get_trivia_item(conn, trivia_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Trivia item not found")
    try:
        return rephrase_trivia(item, get_settings())
    except RephraseConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RephraseProviderError as exc:
        raise HTTPException(status_code=502, detail="Trivia rephrasing failed") from exc
