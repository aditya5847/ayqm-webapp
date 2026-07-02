from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
from duckdb import DuckDBPyConnection

from .config import get_settings


def connect(database_path: Path | str | None = None) -> DuckDBPyConnection:
    path = database_path or get_settings().database_path
    return duckdb.connect(str(path))


@contextmanager
def get_connection() -> Iterator[DuckDBPyConnection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def initialize_database(database_path: Path | str | None = None) -> None:
    conn = connect(database_path)
    try:
        _migrate_episodes(conn)
        _migrate_trivia_items(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes (
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
                finished_at TIMESTAMP
            )
            """
        )
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
    finally:
        conn.close()


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
