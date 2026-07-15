from duckdb import DuckDBPyConnection


TRIVIA_SEARCH_TABLE = "trivia_search_documents"
TRIVIA_SEARCH_FIELDS = "question,answer,keywords_text"


def ensure_trivia_search(conn: DuckDBPyConnection) -> None:
    _load_fts(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TRIVIA_SEARCH_TABLE} (
            trivia_id VARCHAR PRIMARY KEY,
            episode_id VARCHAR NOT NULL,
            is_published BOOLEAN NOT NULL,
            question VARCHAR NOT NULL,
            answer VARCHAR NOT NULL,
            keywords_text VARCHAR NOT NULL
        )
        """
    )
    refresh_trivia_search_index(conn)


def refresh_trivia_search_index(conn: DuckDBPyConnection) -> None:
    _load_fts(conn)
    conn.execute(f"DELETE FROM {TRIVIA_SEARCH_TABLE}")
    conn.execute(
        f"""
        INSERT INTO {TRIVIA_SEARCH_TABLE}
        SELECT
            ti.id,
            ti.episode_id,
            e.is_published,
            COALESCE(ti.question, ''),
            COALESCE(ti.answer, ''),
            CAST(ti.keywords AS VARCHAR)
        FROM trivia_items ti
        JOIN episodes e ON e.id = ti.episode_id
        """
    )
    _create_trivia_fts_index(conn)


def trivia_search_score_sql(table_alias: str = "tsd") -> str:
    return (
        f"fts_main_{TRIVIA_SEARCH_TABLE}.match_bm25("
        f"{table_alias}.trivia_id, ?, fields := '{TRIVIA_SEARCH_FIELDS}', conjunctive := 1)"
    )


def _load_fts(conn: DuckDBPyConnection) -> None:
    try:
        conn.execute("INSTALL fts")
        conn.execute("LOAD fts")
    except Exception as exc:  # pragma: no cover - exact DuckDB exception type varies by install state
        raise RuntimeError("DuckDB FTS extension is required for trivia search") from exc


def _create_trivia_fts_index(conn: DuckDBPyConnection) -> None:
    conn.execute(
        f"""
        PRAGMA create_fts_index(
            '{TRIVIA_SEARCH_TABLE}',
            'trivia_id',
            'question',
            'answer',
            'keywords_text',
            stemmer='english',
            stopwords='english',
            ignore='(\\.|[^a-z])+',
            strip_accents=1,
            lower=1,
            overwrite=1
        )
        """
    )
