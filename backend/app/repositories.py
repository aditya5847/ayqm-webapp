import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from duckdb import DuckDBPyConnection

from .schemas import EpisodeMetadata, EpisodeUpdate, JobKind, JobStatus


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _loads_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def create_episode(
    conn: DuckDBPyConnection,
    metadata: EpisodeMetadata,
    audio_path: str,
    audio_content_type: str | None,
) -> dict[str, Any]:
    episode_id = str(uuid4())
    timestamp = now_utc()
    conn.execute(
        """
        INSERT INTO episodes (
            id, episode_title, episode_number, episode_description, published_at,
            source_url, extra_metadata, audio_path, audio_content_type, is_published,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?::JSON, ?, ?, ?, ?, ?)
        """,
        [
            episode_id,
            metadata.episode_title,
            metadata.episode_number,
            metadata.episode_description,
            metadata.published_at.replace(tzinfo=None) if metadata.published_at else None,
            str(metadata.source_url) if metadata.source_url else None,
            json.dumps(metadata.extra_metadata),
            audio_path,
            audio_content_type,
            False,
            timestamp,
            timestamp,
        ],
    )
    replace_episode_speakers(conn, episode_id, metadata.speaker_ids)
    episode = get_episode(conn, episode_id)
    if episode is None:
        raise RuntimeError(f"Episode was not created: {episode_id}")
    return episode


def get_episode(conn: DuckDBPyConnection, episode_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            e.id,
            e.episode_title,
            e.episode_number,
            e.episode_description,
            e.published_at,
            e.source_url,
            e.extra_metadata,
            e.audio_path,
            e.audio_content_type,
            e.is_published,
            CASE WHEN t.episode_id IS NULL THEN 'missing' ELSE 'completed' END AS transcript_status,
            CASE WHEN COUNT(ti.id) = 0 THEN 'missing' ELSE 'completed' END AS trivia_status,
            COUNT(ti.id) AS trivia_count,
            e.created_at,
            e.updated_at
        FROM episodes e
        LEFT JOIN transcripts t ON t.episode_id = e.id
        LEFT JOIN trivia_items ti ON ti.episode_id = e.id
        WHERE e.id = ?
        GROUP BY
            e.id, e.episode_title, e.episode_number, e.episode_description, e.published_at,
            e.source_url, e.extra_metadata, e.audio_path, e.audio_content_type, e.is_published,
            t.episode_id, e.created_at, e.updated_at
        """,
        [episode_id],
    ).fetchone()
    if row is None:
        return None
    return _episode_from_row(conn, row)


def list_episodes(conn: DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            e.id,
            e.episode_title,
            e.episode_number,
            e.episode_description,
            e.published_at,
            e.source_url,
            e.extra_metadata,
            e.audio_path,
            e.audio_content_type,
            e.is_published,
            CASE WHEN t.episode_id IS NULL THEN 'missing' ELSE 'completed' END AS transcript_status,
            CASE WHEN COUNT(ti.id) = 0 THEN 'missing' ELSE 'completed' END AS trivia_status,
            COUNT(ti.id) AS trivia_count,
            e.created_at,
            e.updated_at
        FROM episodes e
        LEFT JOIN transcripts t ON t.episode_id = e.id
        LEFT JOIN trivia_items ti ON ti.episode_id = e.id
        GROUP BY
            e.id, e.episode_title, e.episode_number, e.episode_description, e.published_at,
            e.source_url, e.extra_metadata, e.audio_path, e.audio_content_type, e.is_published,
            t.episode_id, e.created_at, e.updated_at
        ORDER BY e.created_at DESC
        """
    ).fetchall()
    return [_episode_from_row(conn, row) for row in rows]


def update_episode(conn: DuckDBPyConnection, episode_id: str, request: EpisodeUpdate) -> dict[str, Any] | None:
    if get_episode(conn, episode_id) is None:
        return None
    speaker_placeholders = ", ".join("?" for _ in request.speaker_ids)
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            """
            UPDATE episodes
            SET episode_title = ?, episode_number = ?, episode_description = ?,
                published_at = ?, source_url = ?, is_published = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                request.episode_title,
                request.episode_number,
                request.episode_description,
                request.published_at.replace(tzinfo=None) if request.published_at else None,
                str(request.source_url) if request.source_url else None,
                request.is_published,
                now_utc(),
                episode_id,
            ],
        )
        replace_episode_speakers(conn, episode_id, request.speaker_ids)
        conn.execute(
            f"""
            DELETE FROM episode_speaker_mappings
            WHERE episode_id = ? AND speaker_id NOT IN ({speaker_placeholders})
            """,
            [episode_id, *request.speaker_ids],
        )
        conn.execute(
            f"""
            UPDATE trivia_items
            SET asker_speaker_id = NULL, asker_is_manual = FALSE
            WHERE episode_id = ? AND asker_speaker_id IS NOT NULL
              AND asker_speaker_id NOT IN ({speaker_placeholders})
            """,
            [episode_id, *request.speaker_ids],
        )
        recompute_trivia_askers(conn, episode_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_episode(conn, episode_id)


def set_episode_published(conn: DuckDBPyConnection, episode_id: str, published: bool) -> None:
    conn.execute(
        "UPDATE episodes SET is_published = ?, updated_at = ? WHERE id = ?",
        [published, now_utc(), episode_id],
    )


def get_published_episode(conn: DuckDBPyConnection, episode_id: str) -> dict[str, Any] | None:
    episode = get_episode(conn, episode_id)
    if episode is None or not episode["is_published"]:
        return None
    return _public_episode(episode)


def list_published_episodes(conn: DuckDBPyConnection) -> list[dict[str, Any]]:
    episode_ids = conn.execute(
        """
        SELECT id FROM episodes
        WHERE is_published = TRUE
        ORDER BY COALESCE(published_at, created_at) DESC, episode_number DESC, id
        """
    ).fetchall()
    return [
        _public_episode(episode)
        for (episode_id,) in episode_ids
        if (episode := get_episode(conn, episode_id)) is not None
    ]


def _public_episode(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        key: episode[key]
        for key in (
            "id",
            "episode_title",
            "episode_number",
            "episode_description",
            "published_at",
            "source_url",
            "speakers",
            "trivia_count",
        )
    }


def _episode_from_row(conn: DuckDBPyConnection, row: tuple[Any, ...]) -> dict[str, Any]:
    episode_id = row[0]
    return {
        "id": episode_id,
        "episode_title": row[1],
        "episode_number": row[2],
        "episode_description": row[3],
        "published_at": row[4],
        "source_url": row[5],
        "extra_metadata": _loads_json(row[6], {}),
        "audio_path": row[7],
        "audio_content_type": row[8],
        "is_published": row[9],
        "transcript_status": row[10],
        "trivia_status": row[11],
        "trivia_count": row[12],
        "created_at": row[13],
        "updated_at": row[14],
        "speakers": list_episode_speakers(conn, episode_id),
    }


def create_speaker(conn: DuckDBPyConnection, name: str) -> dict[str, Any]:
    speaker_id = str(uuid4())
    conn.execute("INSERT INTO speakers VALUES (?, ?)", [speaker_id, name])
    speaker = get_speaker(conn, speaker_id)
    if speaker is None:
        raise RuntimeError(f"Speaker was not created: {speaker_id}")
    return speaker


def get_speaker(conn: DuckDBPyConnection, speaker_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT id, name FROM speakers WHERE id = ?", [speaker_id]).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1]}


def list_speakers(conn: DuckDBPyConnection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, name FROM speakers ORDER BY name, id").fetchall()
    return [{"id": row[0], "name": row[1]} for row in rows]


def update_speaker(conn: DuckDBPyConnection, speaker_id: str, name: str) -> dict[str, Any] | None:
    conn.execute("UPDATE speakers SET name = ? WHERE id = ?", [name, speaker_id])
    return get_speaker(conn, speaker_id)


def speaker_reference_count(conn: DuckDBPyConnection, speaker_id: str) -> int:
    episode_count = conn.execute(
        "SELECT COUNT(*) FROM episode_speakers WHERE speaker_id = ?",
        [speaker_id],
    ).fetchone()[0]
    mapping_count = conn.execute(
        "SELECT COUNT(*) FROM episode_speaker_mappings WHERE speaker_id = ?",
        [speaker_id],
    ).fetchone()[0]
    return int(episode_count + mapping_count)


def delete_speaker(conn: DuckDBPyConnection, speaker_id: str) -> bool:
    if get_speaker(conn, speaker_id) is None:
        return False
    conn.execute("DELETE FROM speakers WHERE id = ?", [speaker_id])
    return True


def list_episode_speakers(conn: DuckDBPyConnection, episode_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.id, s.name
        FROM episode_speakers es
        JOIN speakers s ON s.id = es.speaker_id
        WHERE es.episode_id = ?
        ORDER BY es.position, s.name, s.id
        """,
        [episode_id],
    ).fetchall()
    return [{"id": row[0], "name": row[1]} for row in rows]


def replace_episode_speakers(
    conn: DuckDBPyConnection,
    episode_id: str,
    speaker_ids: list[str],
) -> None:
    conn.execute("DELETE FROM episode_speakers WHERE episode_id = ?", [episode_id])
    for position, speaker_id in enumerate(speaker_ids):
        conn.execute(
            "INSERT INTO episode_speakers VALUES (?, ?, ?)",
            [episode_id, speaker_id, position],
        )


def missing_speaker_ids(conn: DuckDBPyConnection, speaker_ids: list[str]) -> list[str]:
    missing = []
    for speaker_id in speaker_ids:
        if get_speaker(conn, speaker_id) is None:
            missing.append(speaker_id)
    return missing


def speaker_ids_for_episode(conn: DuckDBPyConnection, episode_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT speaker_id FROM episode_speakers WHERE episode_id = ? ORDER BY position",
        [episode_id],
    ).fetchall()
    return [row[0] for row in rows]


def create_job(conn: DuckDBPyConnection, episode_id: str, kind: JobKind) -> dict[str, Any]:
    job_id = str(uuid4())
    timestamp = now_utc()
    conn.execute(
        """
        INSERT INTO jobs
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [job_id, episode_id, kind, "queued", None, timestamp, None, None],
    )
    job = get_job(conn, job_id)
    if job is None:
        raise RuntimeError(f"Job was not created: {job_id}")
    return job


def get_job(conn: DuckDBPyConnection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, episode_id, kind, status, error, created_at, started_at, finished_at
        FROM jobs
        WHERE id = ?
        """,
        [job_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "episode_id": row[1],
        "kind": row[2],
        "status": row[3],
        "error": row[4],
        "created_at": row[5],
        "started_at": row[6],
        "finished_at": row[7],
    }


def update_job_status(
    conn: DuckDBPyConnection,
    job_id: str,
    status: JobStatus,
    error: str | None = None,
) -> None:
    timestamp = now_utc()
    if status == "running":
        conn.execute(
            "UPDATE jobs SET status = ?, started_at = ?, error = NULL WHERE id = ?",
            [status, timestamp, job_id],
        )
    elif status in {"succeeded", "failed"}:
        conn.execute(
            "UPDATE jobs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
            [status, timestamp, error, job_id],
        )
    else:
        conn.execute("UPDATE jobs SET status = ?, error = ? WHERE id = ?", [status, error, job_id])


def save_transcript(
    conn: DuckDBPyConnection,
    episode_id: str,
    transcript_path: str,
    transcript: dict[str, Any],
) -> None:
    timestamp = now_utc()
    conn.execute(
        """
        INSERT OR REPLACE INTO transcripts
        VALUES (?, ?, ?::JSON, ?)
        """,
        [episode_id, transcript_path, json.dumps(transcript), timestamp],
    )
    touch_episode(conn, episode_id)


def get_transcript(conn: DuckDBPyConnection, episode_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT transcript_json FROM transcripts WHERE episode_id = ?",
        [episode_id],
    ).fetchone()
    if row is None:
        return None
    return _loads_json(row[0], {})


def get_speaker_mapping(conn: DuckDBPyConnection, episode_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT esm.diarization_label, s.id, s.name
        FROM episode_speaker_mappings esm
        JOIN speakers s ON s.id = esm.speaker_id
        WHERE esm.episode_id = ?
        ORDER BY esm.diarization_label
        """,
        [episode_id],
    ).fetchall()
    return {row[0]: {"id": row[1], "name": row[2]} for row in rows}


def _speaker_id_mapping(conn: DuckDBPyConnection, episode_id: str) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT diarization_label, speaker_id
        FROM episode_speaker_mappings
        WHERE episode_id = ?
        """,
        [episode_id],
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def replace_speaker_mapping(
    conn: DuckDBPyConnection,
    episode_id: str,
    mappings: dict[str, str],
) -> dict[str, dict[str, Any]]:
    conn.execute("DELETE FROM episode_speaker_mappings WHERE episode_id = ?", [episode_id])
    for label, speaker_id in mappings.items():
        conn.execute(
            "INSERT INTO episode_speaker_mappings VALUES (?, ?, ?)",
            [episode_id, label, speaker_id],
        )
    recompute_trivia_askers(conn, episode_id)
    touch_episode(conn, episode_id)
    return get_speaker_mapping(conn, episode_id)


def _speaker_diarization_dict(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("speaker_diarization") or {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _asker_label(data: dict[str, Any]) -> str | None:
    value = _speaker_diarization_dict(data).get("asker_speaker")
    return str(value) if value else None


def save_trivia_items(
    conn: DuckDBPyConnection,
    episode_id: str,
    trivia_items: list[Any],
) -> None:
    timestamp = now_utc()
    mapping = _speaker_id_mapping(conn, episode_id)
    set_episode_published(conn, episode_id, False)
    conn.execute("DELETE FROM trivia_items WHERE episode_id = ?", [episode_id])
    for index, item in enumerate(trivia_items, start=1):
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        timestamps = data.get("timestamps") or {}
        item_id = f"{episode_id}-trivia-{index:04d}"
        speaker_diarization = _speaker_diarization_dict(data)
        conn.execute(
            """
            INSERT INTO trivia_items (
                id, episode_id, type, question, answer, keywords, timestamp_start,
                timestamp_end, timestamp_display, speaker_diarization,
                asker_speaker_id, asker_is_manual, confidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?::JSON, ?, ?, ?, ?::JSON, ?, ?, ?, ?)
            """,
            [
                item_id,
                episode_id,
                data.get("type"),
                data.get("question"),
                data.get("answer"),
                json.dumps(data.get("keywords") or []),
                float(timestamps.get("start") or 0),
                float(timestamps.get("end") or 0),
                str(timestamps.get("display") or ""),
                json.dumps(speaker_diarization),
                mapping.get(_asker_label(data)),
                False,
                data.get("confidence") or "medium",
                timestamp,
            ],
        )
    touch_episode(conn, episode_id)


def recompute_trivia_askers(conn: DuckDBPyConnection, episode_id: str) -> None:
    mapping = _speaker_id_mapping(conn, episode_id)
    rows = conn.execute(
        "SELECT id, speaker_diarization FROM trivia_items WHERE episode_id = ? AND asker_is_manual = FALSE",
        [episode_id],
    ).fetchall()
    for trivia_id, speaker_diarization_json in rows:
        speaker_diarization = _loads_json(speaker_diarization_json, {})
        speaker_id = mapping.get(speaker_diarization.get("asker_speaker"))
        conn.execute(
            "UPDATE trivia_items SET asker_speaker_id = ? WHERE id = ?",
            [speaker_id, trivia_id],
        )


def list_trivia_items(conn: DuckDBPyConnection, episode_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            ti.id, ti.episode_id, ti.type, ti.question, ti.answer, ti.keywords,
            ti.timestamp_start, ti.timestamp_end, ti.timestamp_display,
            ti.speaker_diarization, ti.asker_speaker_id, s.name, ti.confidence, ti.created_at
        FROM trivia_items ti
        LEFT JOIN speakers s ON s.id = ti.asker_speaker_id
        WHERE ti.episode_id = ?
        ORDER BY ti.timestamp_start, ti.id
        """,
        [episode_id],
    ).fetchall()
    return [_trivia_from_row(row) for row in rows]


def get_trivia_item(conn: DuckDBPyConnection, trivia_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            ti.id, ti.episode_id, ti.type, ti.question, ti.answer, ti.keywords,
            ti.timestamp_start, ti.timestamp_end, ti.timestamp_display,
            ti.speaker_diarization, ti.asker_speaker_id, s.name, ti.confidence, ti.created_at
        FROM trivia_items ti
        LEFT JOIN speakers s ON s.id = ti.asker_speaker_id
        WHERE ti.id = ?
        """,
        [trivia_id],
    ).fetchone()
    return _trivia_from_row(row) if row else None


def update_trivia_item(
    conn: DuckDBPyConnection,
    trivia_id: str,
    changes: dict[str, Any],
) -> dict[str, Any] | None:
    item = get_trivia_item(conn, trivia_id)
    if item is None:
        return None
    assignments: list[str] = []
    values: list[Any] = []
    for field in ("type", "question", "answer", "confidence"):
        if field in changes:
            assignments.append(f"{field} = ?")
            values.append(changes[field])
    if "keywords" in changes:
        assignments.append("keywords = ?::JSON")
        values.append(json.dumps(changes["keywords"]))
    if "asker_speaker_id" in changes:
        assignments.extend(["asker_speaker_id = ?", "asker_is_manual = TRUE"])
        values.append(changes["asker_speaker_id"])
    if assignments:
        conn.execute(
            f"UPDATE trivia_items SET {', '.join(assignments)} WHERE id = ?",
            [*values, trivia_id],
        )
        touch_episode(conn, item["episode_id"])
    return get_trivia_item(conn, trivia_id)


def delete_trivia_item(conn: DuckDBPyConnection, trivia_id: str) -> str | None:
    item = get_trivia_item(conn, trivia_id)
    if item is None:
        return None
    conn.execute("DELETE FROM trivia_items WHERE id = ?", [trivia_id])
    touch_episode(conn, item["episode_id"])
    return item["episode_id"]


def list_public_trivia(
    conn: DuckDBPyConnection,
    *,
    episode_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    filters = ["e.is_published = TRUE"]
    params: list[Any] = []
    if episode_id is not None:
        filters.append("ti.episode_id = ?")
        params.append(episode_id)
    rows = conn.execute(
        f"""
        SELECT
            ti.id, ti.episode_id, ti.type, ti.question, ti.answer, ti.keywords,
            ti.timestamp_start, ti.timestamp_end, ti.timestamp_display,
            ti.speaker_diarization, ti.asker_speaker_id, s.name, ti.confidence, ti.created_at
        FROM trivia_items ti
        JOIN episodes e ON e.id = ti.episode_id
        LEFT JOIN speakers s ON s.id = ti.asker_speaker_id
        WHERE {' AND '.join(filters)}
        ORDER BY COALESCE(e.published_at, e.created_at) DESC,
                 ti.timestamp_start, ti.id
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [_public_trivia(_trivia_from_row(row)) for row in rows]


def _trivia_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "episode_id": row[1],
        "type": row[2],
        "question": row[3],
        "answer": row[4],
        "keywords": _loads_json(row[5], []),
        "timestamps": {"start": row[6], "end": row[7], "display": row[8]},
        "speaker_diarization": _loads_json(row[9], {}),
        "asker": {"id": row[10], "name": row[11]} if row[10] else None,
        "confidence": row[12],
        "created_at": row[13],
    }


def _public_trivia(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "speaker_diarization"}


def touch_episode(conn: DuckDBPyConnection, episode_id: str) -> None:
    conn.execute("UPDATE episodes SET updated_at = ? WHERE id = ?", [now_utc(), episode_id])
