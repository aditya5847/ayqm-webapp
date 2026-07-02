from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_admin
from ..db import get_connection
from ..repositories import (
    create_speaker,
    delete_speaker,
    get_speaker,
    list_speakers,
    speaker_reference_count,
    update_speaker,
)
from ..schemas import SpeakerCreate, SpeakerOut, SpeakerUpdate

router = APIRouter(prefix="/speakers", tags=["speakers"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[SpeakerOut])
def read_speakers() -> list[dict]:
    with get_connection() as conn:
        return list_speakers(conn)


@router.post("", response_model=SpeakerOut, status_code=status.HTTP_201_CREATED)
def create_speaker_route(request: SpeakerCreate) -> dict:
    with get_connection() as conn:
        return create_speaker(conn, request.name)


@router.get("/{speaker_id}", response_model=SpeakerOut)
def read_speaker(speaker_id: str) -> dict:
    with get_connection() as conn:
        speaker = get_speaker(conn, speaker_id)
    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return speaker


@router.patch("/{speaker_id}", response_model=SpeakerOut)
def update_speaker_route(speaker_id: str, request: SpeakerUpdate) -> dict:
    with get_connection() as conn:
        speaker = update_speaker(conn, speaker_id, request.name)
    if speaker is None:
        raise HTTPException(status_code=404, detail="Speaker not found")
    return speaker


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker_route(speaker_id: str) -> None:
    with get_connection() as conn:
        if get_speaker(conn, speaker_id) is None:
            raise HTTPException(status_code=404, detail="Speaker not found")
        if speaker_reference_count(conn, speaker_id) > 0:
            raise HTTPException(status_code=409, detail="Speaker is in use")
        delete_speaker(conn, speaker_id)
