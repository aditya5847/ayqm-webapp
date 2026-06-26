from backend.app.db import connect, initialize_database
from backend.app.repositories import create_episode, create_job, create_speaker, get_job, list_trivia_items, save_trivia_items
from backend.app.schemas import EpisodeMetadata


def test_database_initialization_and_basic_crud(tmp_path):
    database_path = tmp_path / "test.duckdb"
    initialize_database(database_path)

    conn = connect(database_path)
    try:
        speaker = create_speaker(conn, "Ada")
        episode = create_episode(
            conn,
            EpisodeMetadata(
                episode_title="Episode 1",
                episode_number=1,
                speaker_ids=[speaker["id"]],
                extra_metadata={"topic": "trivia"},
            ),
            audio_path="/tmp/audio.mp3",
            audio_content_type="audio/mpeg",
        )
        job = create_job(conn, episode["id"], "transcribe")
        fetched = get_job(conn, job["id"])

        assert episode["episode_title"] == "Episode 1"
        assert episode["episode_number"] == 1
        assert episode["speakers"] == [speaker]
        assert episode["extra_metadata"] == {"topic": "trivia"}
        assert fetched["status"] == "queued"
    finally:
        conn.close()


def test_trivia_ids_are_scoped_by_episode(tmp_path):
    database_path = tmp_path / "test.duckdb"
    initialize_database(database_path)

    conn = connect(database_path)
    try:
        speaker = create_speaker(conn, "Ada")
        episode_1 = create_episode(
            conn,
            EpisodeMetadata(episode_title="Episode 1", episode_number=1, speaker_ids=[speaker["id"]]),
            audio_path="/tmp/audio-1.mp3",
            audio_content_type="audio/mpeg",
        )
        episode_2 = create_episode(
            conn,
            EpisodeMetadata(episode_title="Episode 2", episode_number=2, speaker_ids=[speaker["id"]]),
            audio_path="/tmp/audio-2.mp3",
            audio_content_type="audio/mpeg",
        )
        trivia = [
            {
                "id": "1",
                "type": "asked_question",
                "question": "Question?",
                "answer": "Answer.",
                "timestamps": {"start": 0, "end": 1, "display": "00:00:00-00:00:01"},
                "speaker_diarization": {},
                "confidence": "high",
            }
        ]

        save_trivia_items(conn, episode_1["id"], trivia)
        save_trivia_items(conn, episode_2["id"], trivia)

        episode_1_trivia = list_trivia_items(conn, episode_1["id"])
        episode_2_trivia = list_trivia_items(conn, episode_2["id"])
        assert episode_1_trivia[0]["id"] == f"{episode_1['id']}-trivia-0001"
        assert episode_2_trivia[0]["id"] == f"{episode_2['id']}-trivia-0001"
    finally:
        conn.close()
