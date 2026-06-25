from fastapi import APIRouter, HTTPException

from ..db import get_connection
from ..repositories import get_job
from ..schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def read_job(job_id: str) -> dict:
    with get_connection() as conn:
        job = get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

