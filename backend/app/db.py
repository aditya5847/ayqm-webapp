from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
from threading import RLock

import duckdb
from duckdb import DuckDBPyConnection

from .config import get_settings
from .search import ensure_trivia_search


_database_lock = RLock()


def connect(database_path: Path | str | None = None) -> DuckDBPyConnection:
    path = database_path or get_settings().database_path
    return duckdb.connect(str(path))


@contextmanager
def get_connection() -> Iterator[DuckDBPyConnection]:
    with _database_lock:
        conn = connect()
        try:
            yield conn
        finally:
            conn.close()


def initialize_database(database_path: Path | str | None = None) -> None:
    with _database_lock:
        conn = connect(database_path)
        try:
            _migrate_episodes(conn)
            _migrate_trivia_items(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id VARCHAR PRIMARY KEY,
                    episode_title VARCHAR NOT NULL,
                    episode_number INTEGER,
                    episode_description VARCHAR,
                    published_at TIMESTAMP,
                    source_url VARCHAR,
                    extra_metadata JSON NOT NULL,
                    audio_path VARCHAR NOT NULL,
                    audio_content_type VARCHAR,
                    is_published BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    episode_kind VARCHAR NOT NULL DEFAULT 'main',
                    rss_guid VARCHAR,
                    rss_enclosure_url VARCHAR,
                    audio_object_key VARCHAR,
                    audio_sha256 VARCHAR,
                    audio_size_bytes BIGINT,
                    duration_seconds DOUBLE,
                    rss_imported_at TIMESTAMP,
                    rss_artwork_url VARCHAR,
                    artwork_object_key VARCHAR,
                    artwork_content_type VARCHAR,
                    artwork_size_bytes BIGINT
                )
                """
            )
            _migrate_production_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS speakers (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_speakers (
                    episode_id VARCHAR NOT NULL,
                    speaker_id VARCHAR NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (episode_id, speaker_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_speaker_mappings (
                    episode_id VARCHAR NOT NULL,
                    diarization_label VARCHAR NOT NULL,
                    speaker_id VARCHAR NOT NULL,
                    PRIMARY KEY (episode_id, diarization_label)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id VARCHAR PRIMARY KEY,
                    episode_id VARCHAR NOT NULL,
                    kind VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    error VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    payload JSON NOT NULL DEFAULT '{}',
                    progress_stage VARCHAR,
                    progress_current DOUBLE,
                    progress_total DOUBLE,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_token VARCHAR,
                    lease_expires_at TIMESTAMP,
                    artifact_key VARCHAR,
                    artifact_sha256 VARCHAR,
                    updated_at TIMESTAMP
                )
                """
            )
            _migrate_job_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    episode_id VARCHAR PRIMARY KEY,
                    transcript_path VARCHAR NOT NULL,
                    transcript_json JSON NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trivia_items (
                    id VARCHAR PRIMARY KEY,
                    episode_id VARCHAR NOT NULL,
                    type VARCHAR NOT NULL,
                    question VARCHAR,
                    answer VARCHAR,
                    keywords JSON NOT NULL,
                    timestamp_start DOUBLE NOT NULL,
                    timestamp_end DOUBLE NOT NULL,
                    timestamp_display VARCHAR NOT NULL,
                    speaker_diarization JSON NOT NULL,
                    asker_speaker_id VARCHAR,
                    asker_is_manual BOOLEAN NOT NULL DEFAULT FALSE,
                    confidence VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_imports (
                    id VARCHAR PRIMARY KEY,
                    feed_url VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    dry_run BOOLEAN NOT NULL,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    imported_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    error VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backup_records (
                    id VARCHAR PRIMARY KEY,
                    object_key VARCHAR NOT NULL,
                    sha256 VARCHAR NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gemini_usage (
                    id VARCHAR PRIMARY KEY,
                    job_id VARCHAR NOT NULL,
                    episode_id VARCHAR NOT NULL,
                    model VARCHAR NOT NULL,
                    prompt_version VARCHAR NOT NULL,
                    transcript_sha256 VARCHAR NOT NULL,
                    input_tokens BIGINT NOT NULL,
                    output_tokens BIGINT NOT NULL,
                    estimated_cost_usd DOUBLE NOT NULL,
                    actual_cost_usd DOUBLE NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sunday_quizzes (
                    id VARCHAR PRIMARY KEY,
                    quiz_date DATE NOT NULL,
                    theme VARCHAR NOT NULL,
                    status VARCHAR NOT NULL DEFAULT 'draft',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sunday_quiz_questions (
                    id VARCHAR PRIMARY KEY,
                    quiz_id VARCHAR NOT NULL,
                    position INTEGER NOT NULL,
                    question VARCHAR,
                    options JSON NOT NULL DEFAULT '[]',
                    correct_option INTEGER,
                    correct_answer VARCHAR,
                    incorrect_answers JSON NOT NULL DEFAULT '[]',
                    explanation VARCHAR,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE(quiz_id, position)
                )
                """
            )
            _migrate_sunday_quiz_question_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sunday_quiz_assets (
                    id VARCHAR PRIMARY KEY,
                    quiz_id VARCHAR NOT NULL,
                    question_id VARCHAR,
                    kind VARCHAR NOT NULL,
                    object_key VARCHAR NOT NULL,
                    content_type VARCHAR,
                    size_bytes BIGINT,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sunday_quiz_attempts (
                    id VARCHAR PRIMARY KEY,
                    quiz_id VARCHAR NOT NULL,
                    score INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    selected_answers JSON NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS episodes_rss_guid_idx ON episodes(rss_guid)"
            )
            ensure_trivia_search(conn)
        finally:
            conn.close()


def database_lock() -> RLock:
    return _database_lock


def _ensure_column(conn: DuckDBPyConnection, table: str, name: str, definition: str) -> None:
    if name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_production_columns(conn: DuckDBPyConnection) -> None:
    if not _table_exists(conn, "episodes"):
        return
    table_info = conn.execute("PRAGMA table_info('episodes')").fetchall()
    number_column = next((row for row in table_info if row[1] == "episode_number"), None)
    if number_column and number_column[3]:
        conn.execute("ALTER TABLE episodes ALTER COLUMN episode_number DROP NOT NULL")
    _ensure_column(conn, "episodes", "episode_kind", "VARCHAR DEFAULT 'main'")
    conn.execute("UPDATE episodes SET episode_kind = 'main' WHERE episode_kind IS NULL")
    _ensure_column(conn, "episodes", "rss_guid", "VARCHAR")
    _ensure_column(conn, "episodes", "rss_enclosure_url", "VARCHAR")
    _ensure_column(conn, "episodes", "audio_object_key", "VARCHAR")
    _ensure_column(conn, "episodes", "audio_sha256", "VARCHAR")
    _ensure_column(conn, "episodes", "audio_size_bytes", "BIGINT")
    _ensure_column(conn, "episodes", "duration_seconds", "DOUBLE")
    _ensure_column(conn, "episodes", "rss_imported_at", "TIMESTAMP")
    _ensure_column(conn, "episodes", "rss_artwork_url", "VARCHAR")
    _ensure_column(conn, "episodes", "artwork_object_key", "VARCHAR")
    _ensure_column(conn, "episodes", "artwork_content_type", "VARCHAR")
    _ensure_column(conn, "episodes", "artwork_size_bytes", "BIGINT")


def _migrate_job_columns(conn: DuckDBPyConnection) -> None:
    if not _table_exists(conn, "jobs"):
        return
    _ensure_column(conn, "jobs", "payload", "JSON DEFAULT '{}'")
    conn.execute("UPDATE jobs SET payload = '{}'::JSON WHERE payload IS NULL")
    _ensure_column(conn, "jobs", "progress_stage", "VARCHAR")
    _ensure_column(conn, "jobs", "progress_current", "DOUBLE")
    _ensure_column(conn, "jobs", "progress_total", "DOUBLE")
    _ensure_column(conn, "jobs", "attempts", "INTEGER DEFAULT 0")
    conn.execute("UPDATE jobs SET attempts = 0 WHERE attempts IS NULL")
    _ensure_column(conn, "jobs", "lease_token", "VARCHAR")
    _ensure_column(conn, "jobs", "lease_expires_at", "TIMESTAMP")
    _ensure_column(conn, "jobs", "artifact_key", "VARCHAR")
    _ensure_column(conn, "jobs", "artifact_sha256", "VARCHAR")
    _ensure_column(conn, "jobs", "updated_at", "TIMESTAMP")


def _migrate_sunday_quiz_question_columns(conn: DuckDBPyConnection) -> None:
    if not _table_exists(conn, "sunday_quiz_questions"):
        return
    _ensure_column(conn, "sunday_quiz_questions", "correct_answer", "VARCHAR")
    _ensure_column(conn, "sunday_quiz_questions", "incorrect_answers", "JSON DEFAULT '[]'")
    rows = conn.execute(
        """
        SELECT id, options, correct_option
        FROM sunday_quiz_questions
        WHERE correct_answer IS NULL
          AND correct_option IS NOT NULL
          AND options IS NOT NULL
        """
    ).fetchall()
    for question_id, options_json, correct_option in rows:
        if isinstance(options_json, str):
            options = json.loads(options_json)
        else:
            options = options_json
        if not isinstance(options, list) or correct_option < 0 or correct_option >= len(options):
            continue
        correct_answer = options[correct_option]
        incorrect_answers = [option for index, option in enumerate(options) if index != correct_option]
        conn.execute(
            """
            UPDATE sunday_quiz_questions
            SET correct_answer = ?, incorrect_answers = ?::JSON
            WHERE id = ?
            """,
            [correct_answer, json.dumps(incorrect_answers), question_id],
        )


def _table_exists(conn: DuckDBPyConnection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _table_columns(conn: DuckDBPyConnection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()}


def _table_column_types(conn: DuckDBPyConnection, table_name: str) -> dict[str, str]:
    if not _table_exists(conn, table_name):
        return {}
    return {row[1]: row[2].upper() for row in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()}


def _migrate_episodes(conn: DuckDBPyConnection) -> None:
    columns = _table_columns(conn, "episodes")
    column_types = _table_column_types(conn, "episodes")
    episode_number_is_int = column_types.get("episode_number") in {"INTEGER", "INT4", "INT"}
    if (
        not columns
        or {"episode_title", "episode_description"}.issubset(columns)
        and "show_name" not in columns
        and episode_number_is_int
        and "is_published" in columns
    ):
        return

    conn.execute(
        """
        CREATE TABLE episodes_migrated (
            id VARCHAR PRIMARY KEY,
            episode_title VARCHAR NOT NULL,
            episode_number INTEGER NOT NULL,
            episode_description VARCHAR,
            published_at TIMESTAMP,
            source_url VARCHAR,
            extra_metadata JSON NOT NULL,
            audio_path VARCHAR NOT NULL,
            audio_content_type VARCHAR,
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """
    )
    title_expr = "episode_title" if "episode_title" in columns else "title"
    episode_number_expr = (
        "COALESCE(TRY_CAST(episode_number AS INTEGER), 1)" if "episode_number" in columns else "1"
    )
    description_expr = "episode_description" if "episode_description" in columns else "NULL"
    is_published_expr = "COALESCE(is_published, FALSE)" if "is_published" in columns else "FALSE"
    conn.execute(
        f"""
        INSERT INTO episodes_migrated
        SELECT
            id,
            {title_expr},
            {episode_number_expr},
            {description_expr},
            published_at,
            source_url,
            extra_metadata,
            audio_path,
            audio_content_type,
            {is_published_expr},
            created_at,
            updated_at
        FROM episodes
        """
    )
    conn.execute("DROP TABLE episodes")
    conn.execute("ALTER TABLE episodes_migrated RENAME TO episodes")


def _migrate_trivia_items(conn: DuckDBPyConnection) -> None:
    columns = _table_columns(conn, "trivia_items")
    if not columns or {"asker_speaker_id", "asker_is_manual"}.issubset(columns):
        return

    asker_expr = "asker_speaker_id" if "asker_speaker_id" in columns else "NULL"
    conn.execute(
        """
        CREATE TABLE trivia_items_migrated (
            id VARCHAR PRIMARY KEY,
            episode_id VARCHAR NOT NULL,
            type VARCHAR NOT NULL,
            question VARCHAR,
            answer VARCHAR,
            keywords JSON NOT NULL,
            timestamp_start DOUBLE NOT NULL,
            timestamp_end DOUBLE NOT NULL,
            timestamp_display VARCHAR NOT NULL,
            speaker_diarization JSON NOT NULL,
            asker_speaker_id VARCHAR,
            asker_is_manual BOOLEAN NOT NULL DEFAULT FALSE,
            confidence VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        INSERT INTO trivia_items_migrated
        SELECT
            id, episode_id, type, question, answer, keywords,
            timestamp_start, timestamp_end, timestamp_display,
            speaker_diarization,
            {asker_expr},
            FALSE,
            confidence,
            created_at
        FROM trivia_items
        """
    )
    conn.execute("DROP TABLE trivia_items")
    conn.execute("ALTER TABLE trivia_items_migrated RENAME TO trivia_items")
