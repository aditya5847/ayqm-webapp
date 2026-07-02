import json
from types import SimpleNamespace

from backend.app.config import get_settings
from backend.app.db import get_connection
from backend.app.repositories import get_trivia_item, replace_speaker_mapping, save_transcript, save_trivia_items
from backend.app.schemas import TriviaRephraseOut
from backend.app.services.rephrase import RephraseConfigurationError, RephraseProviderError
from tests.conftest import TEST_PASSWORD


def _speaker(client, name="Ada"):
    response = client.post("/speakers", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _episode(client, speaker_ids):
    response = client.post(
        "/episodes",
        data={
            "episode_title": "Original title",
            "episode_number": 1,
            "speaker_ids": json.dumps(speaker_ids),
            "source_url": "https://example.com/listen",
        },
        files={"file": ("episode.mp3", b"audio", "audio/mpeg")},
    )
    assert response.status_code == 201
    return response.json()


def _seed_trivia(episode_id):
    item = SimpleNamespace(
        model_dump=lambda: {
            "type": "asked_question",
            "question": "Original question?",
            "answer": "Original answer.",
            "keywords": ["original"],
            "timestamps": {"start": 1, "end": 2, "display": "00:01-00:02"},
            "speaker_diarization": {},
            "confidence": "high",
        }
    )
    with get_connection() as conn:
        save_trivia_items(conn, episode_id, [item])
    return f"{episode_id}-trivia-0001"


def _seed_labeled_trivia(episode_id, speaker_id):
    item = SimpleNamespace(
        model_dump=lambda: {
            "type": "asked_question",
            "question": "Who asked?",
            "answer": "A host.",
            "keywords": [],
            "timestamps": {"start": 1, "end": 2, "display": "00:01-00:02"},
            "speaker_diarization": {"asker_speaker": "SPEAKER_00"},
            "confidence": "high",
        }
    )
    with get_connection() as conn:
        replace_speaker_mapping(conn, episode_id, {"SPEAKER_00": speaker_id})
        save_trivia_items(conn, episode_id, [item])
    return f"{episode_id}-trivia-0001"


def test_admin_login_session_logout_and_route_protection(unauth_client):
    assert unauth_client.get("/speakers").status_code == 401
    assert unauth_client.get("/episodes/missing/speaker-labels/SPEAKER_00/sample").status_code == 401
    assert unauth_client.get("/auth/session").json() == {"authenticated": False}
    assert unauth_client.post("/auth/login", json={"password": "wrong"}).status_code == 401

    login = unauth_client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=604800" in cookie
    assert unauth_client.get("/auth/session").json() == {"authenticated": True}

    assert unauth_client.post("/auth/logout").status_code == 204
    assert unauth_client.get("/speakers").status_code == 401


def test_episode_update_and_public_data_isolation(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])

    assert client.get("/public/episodes").json() == []
    update = client.patch(
        f"/episodes/{episode['id']}",
        json={
            "episode_title": "Published title",
            "episode_number": 2,
            "episode_description": "Public description",
            "published_at": "2026-07-01T12:00:00Z",
            "source_url": "https://example.com/published",
            "speaker_ids": [speaker["id"]],
            "is_published": True,
        },
    )
    assert update.status_code == 200
    assert update.json()["is_published"] is True

    public = client.get(f"/public/episodes/{episode['id']}")
    assert public.status_code == 200
    payload = public.json()
    assert payload["episode_title"] == "Published title"
    assert "audio_path" not in payload
    assert "extra_metadata" not in payload
    assert "transcript_status" not in payload
    assert "is_published" not in payload


def test_trivia_edit_rephrase_and_delete(client, monkeypatch):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    trivia_id = _seed_trivia(episode["id"])

    update = client.patch(
        f"/trivia/{trivia_id}",
        json={
            "question": "Edited question?",
            "answer": "Edited answer.",
            "keywords": ["edited", "edited"],
            "asker_speaker_id": speaker["id"],
        },
    )
    assert update.status_code == 200
    assert update.json()["question"] == "Edited question?"
    assert update.json()["keywords"] == ["edited"]
    assert update.json()["asker"] == speaker

    monkeypatch.setattr(
        "backend.app.routes.trivia.rephrase_trivia",
        lambda item, settings: TriviaRephraseOut(question="Suggested question?", answer="Suggested answer."),
    )
    suggestion = client.post(f"/trivia/{trivia_id}/rephrase")
    assert suggestion.json() == {"question": "Suggested question?", "answer": "Suggested answer."}
    assert client.get(f"/episodes/{episode['id']}/trivia").json()[0]["question"] == "Edited question?"

    assert client.delete(f"/trivia/{trivia_id}").status_code == 204
    assert client.get(f"/episodes/{episode['id']}/trivia").json() == []


def test_rephrase_configuration_and_provider_errors(client, monkeypatch):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    trivia_id = _seed_trivia(episode["id"])

    monkeypatch.setattr(
        "backend.app.routes.trivia.rephrase_trivia",
        lambda item, settings: (_ for _ in ()).throw(RephraseConfigurationError("missing key")),
    )
    assert client.post(f"/trivia/{trivia_id}/rephrase").status_code == 503

    monkeypatch.setattr(
        "backend.app.routes.trivia.rephrase_trivia",
        lambda item, settings: (_ for _ in ()).throw(RephraseProviderError("provider failed")),
    )
    response = client.post(f"/trivia/{trivia_id}/rephrase")
    assert response.status_code == 502
    assert response.json()["detail"] == "Trivia rephrasing failed"


def test_public_trivia_excludes_raw_diarization(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    _seed_trivia(episode["id"])
    response = client.patch(
        f"/episodes/{episode['id']}",
        json={
            "episode_title": episode["episode_title"],
            "episode_number": episode["episode_number"],
            "episode_description": None,
            "published_at": None,
            "source_url": episode["source_url"],
            "speaker_ids": [speaker["id"]],
            "is_published": True,
        },
    )
    assert response.status_code == 200

    trivia = client.get(f"/public/episodes/{episode['id']}/trivia")
    assert trivia.status_code == 200
    assert len(trivia.json()) == 1
    assert "speaker_diarization" not in trivia.json()[0]


def test_manual_asker_survives_remap_and_clears_when_speaker_is_deselected(client):
    mapped_speaker = _speaker(client, "Ada")
    manual_speaker = _speaker(client, "Grace")
    episode = _episode(client, [mapped_speaker["id"], manual_speaker["id"]])
    trivia_id = _seed_labeled_trivia(episode["id"], mapped_speaker["id"])

    response = client.patch(f"/trivia/{trivia_id}", json={"asker_speaker_id": manual_speaker["id"]})
    assert response.json()["asker"] == manual_speaker
    with get_connection() as conn:
        replace_speaker_mapping(conn, episode["id"], {"SPEAKER_00": mapped_speaker["id"]})
        assert get_trivia_item(conn, trivia_id)["asker"] == manual_speaker

    update = client.patch(
        f"/episodes/{episode['id']}",
        json={
            "episode_title": episode["episode_title"],
            "episode_number": episode["episode_number"],
            "episode_description": episode["episode_description"],
            "published_at": episode["published_at"],
            "source_url": episode["source_url"],
            "speaker_ids": [mapped_speaker["id"]],
            "is_published": False,
        },
    )
    assert update.status_code == 200
    assert client.get(f"/episodes/{episode['id']}/trivia").json()[0]["asker"] == mapped_speaker


def test_starting_trivia_extraction_unpublishes_episode(client, monkeypatch):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    with get_connection() as conn:
        save_transcript(
            conn,
            episode["id"],
            "/tmp/transcript.json",
            {"segments": [{"start": 0, "end": 1, "text": "Fact", "speaker": "SPEAKER_00"}]},
        )
        replace_speaker_mapping(conn, episode["id"], {"SPEAKER_00": speaker["id"]})

    publish = client.patch(
        f"/episodes/{episode['id']}",
        json={
            "episode_title": episode["episode_title"],
            "episode_number": episode["episode_number"],
            "episode_description": None,
            "published_at": None,
            "source_url": episode["source_url"],
            "speaker_ids": [speaker["id"]],
            "is_published": True,
        },
    )
    assert publish.status_code == 200
    assert client.get(f"/public/episodes/{episode['id']}").status_code == 200

    monkeypatch.setattr(
        "backend.app.workers.run_trivia_extraction",
        lambda transcript, episode_dir, request, settings: ([], episode_dir / "trivia.json"),
    )
    extraction = client.post(f"/episodes/{episode['id']}/extract-trivia", json={})
    assert extraction.status_code == 202
    assert client.get(f"/episodes/{episode['id']}").json()["is_published"] is False
    assert client.get(f"/public/episodes/{episode['id']}").status_code == 404


def test_missing_auth_configuration_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(tmp_path / "missing-auth.duckdb"))
    monkeypatch.setenv("AYQM_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("AYQM_SESSION_SECRET", "")
    get_settings.cache_clear()
    from backend.app.main import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as test_client:
        assert test_client.get("/health").status_code == 200
        assert test_client.get("/speakers").status_code == 503
        assert test_client.get("/auth/session").status_code == 503
    get_settings.cache_clear()
