import json
from types import SimpleNamespace

from backend.app.config import get_settings
from backend.app.db import get_connection
from backend.app.repositories import (
    create_job,
    get_trivia_item,
    replace_speaker_mapping,
    save_transcript,
    save_trivia_items,
    update_job_status,
)
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


def _seed_trivia_count(episode_id, count):
    items = [
        SimpleNamespace(
            model_dump=lambda index=index: {
                "type": "asked_question",
                "question": f"Question {index}?",
                "answer": f"Answer {index}.",
                "keywords": ["random"],
                "timestamps": {"start": index, "end": index + 1, "display": str(index)},
                "speaker_diarization": {},
                "confidence": "high",
            }
        )
        for index in range(count)
    ]
    with get_connection() as conn:
        save_trivia_items(conn, episode_id, items)


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


def _seed_custom_trivia(episode_id, items):
    trivia = [
        SimpleNamespace(
            model_dump=lambda item=item, index=index: {
                "type": "asked_question",
                "question": item["question"],
                "answer": item["answer"],
                "keywords": item.get("keywords", []),
                "timestamps": {"start": index, "end": index + 1, "display": str(index)},
                "speaker_diarization": {},
                "confidence": "high",
            }
        )
        for index, item in enumerate(items, start=1)
    ]
    with get_connection() as conn:
        save_trivia_items(conn, episode_id, trivia)


def test_admin_login_session_logout_and_route_protection(unauth_client):
    assert unauth_client.get("/speakers").status_code == 401
    assert unauth_client.get("/episodes/missing/speaker-labels/SPEAKER_00/sample").status_code == 401
    assert unauth_client.patch("/episodes/missing/publication", json={"is_published": True}).status_code == 401
    assert unauth_client.delete("/episodes/missing").status_code == 401
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


def test_admin_episode_list_is_paginated(client):
    speaker = _speaker(client)
    for index in range(31):
        _episode(client, [speaker["id"]])

    first = client.get("/episodes?page=1&page_size=30")
    assert first.status_code == 200
    payload = first.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 30
    assert payload["total_items"] == 31
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 30

    second = client.get("/episodes?page=2&page_size=30")
    assert second.status_code == 200
    payload = second.json()
    assert payload["page"] == 2
    assert payload["page_size"] == 30
    assert payload["total_items"] == 31
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 1


def test_public_episode_artwork_is_publication_gated_and_served_locally(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    settings = get_settings()
    artwork_key = f"episodes/{episode['id']}/artwork"
    artwork_path = settings.upload_root / artwork_key
    artwork_path.parent.mkdir(parents=True, exist_ok=True)
    artwork_path.write_bytes(b"episode artwork")
    with get_connection() as conn:
        conn.execute(
            """UPDATE episodes SET rss_artwork_url = ?, artwork_object_key = ?,
                      artwork_content_type = ?, artwork_size_bytes = ? WHERE id = ?""",
            ["https://example.com/artwork.jpg", artwork_key, "image/jpeg", len(b"episode artwork"), episode["id"]],
        )

    admin_artwork = client.get(f"/episodes/{episode['id']}/artwork")
    assert admin_artwork.status_code == 200
    assert admin_artwork.content == b"episode artwork"
    assert client.get(f"/public/episodes/{episode['id']}/artwork").status_code == 404
    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True}).status_code == 200

    public_episode = client.get(f"/public/episodes/{episode['id']}").json()
    assert public_episode["artwork_url"] == f"/public/episodes/{episode['id']}/artwork"
    assert "artwork_object_key" not in public_episode
    assert "rss_artwork_url" not in public_episode
    artwork = client.get(public_episode["artwork_url"])
    assert artwork.status_code == 200
    assert artwork.content == b"episode artwork"
    assert artwork.headers["content-type"] == "image/jpeg"


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


def test_public_episode_archive_is_paginated_without_changing_existing_list(client):
    speaker = _speaker(client)
    for number in range(1, 13):
        response = client.post(
            "/episodes",
            data={
                "episode_title": f"Episode {number}",
                "episode_number": number,
                "speaker_ids": json.dumps([speaker["id"]]),
            },
            files={"file": (f"episode-{number}.mp3", b"audio", "audio/mpeg")},
        )
        episode = response.json()
        assert client.patch(
            f"/episodes/{episode['id']}/publication",
            json={"is_published": True},
        ).status_code == 200

    first = client.get("/public/episodes/archive?page=1&page_size=10")
    assert first.status_code == 200
    assert first.json()["page"] == 1
    assert first.json()["page_size"] == 10
    assert first.json()["total_items"] == 12
    assert first.json()["total_pages"] == 2
    assert len(first.json()["items"]) == 10

    beyond_last = client.get("/public/episodes/archive?page=99&page_size=10").json()
    assert beyond_last["page"] == 2
    assert len(beyond_last["items"]) == 2
    assert len(client.get("/public/episodes").json()) == 12


def test_random_public_trivia_prefers_new_items_and_fills_small_pools(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    _seed_trivia_count(episode["id"], 6)
    assert client.patch(
        f"/episodes/{episode['id']}/publication",
        json={"is_published": True},
    ).status_code == 200

    first = client.get("/public/trivia/random?limit=4")
    assert first.status_code == 200
    first_items = first.json()
    assert len(first_items) == 4
    assert len({item["id"] for item in first_items}) == 4
    assert all("speaker_diarization" not in item for item in first_items)

    params = [("limit", "4"), *(("exclude_id", item["id"]) for item in first_items)]
    refreshed = client.get("/public/trivia/random", params=params).json()
    assert len(refreshed) == 4
    assert len({item["id"] for item in refreshed}) == 4
    assert len({item["id"] for item in refreshed} - {item["id"] for item in first_items}) == 2


def test_public_random_trivia_searches_published_items_with_all_terms(client):
    speaker = _speaker(client)
    published = _episode(client, [speaker["id"]])
    unpublished = _episode(client, [speaker["id"]])
    _seed_custom_trivia(
        published["id"],
        [
            {"question": "Which mission visited the Moon?", "answer": "Apollo 11.", "keywords": ["space"]},
            {"question": "Which mission visited the Moon?", "answer": "Artemis.", "keywords": ["future"]},
            {"question": "Which dish uses lentils?", "answer": "Dal.", "keywords": ["food"]},
        ],
    )
    _seed_custom_trivia(
        unpublished["id"],
        [{"question": "Which mission visited the Moon?", "answer": "A draft answer.", "keywords": ["space"]}],
    )
    assert client.patch(f"/episodes/{published['id']}/publication", json={"is_published": True}).status_code == 200

    response = client.get("/public/trivia/random", params={"limit": 4, "q": "moon space"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["episode_id"] == published["id"]
    assert items[0]["answer"] == "Apollo 11."
    assert all("speaker_diarization" not in item for item in items)


def test_public_random_trivia_search_refresh_excludes_current_items(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    _seed_custom_trivia(
        episode["id"],
        [
            {"question": f"Searchable planet question {index}?", "answer": f"Answer {index}.", "keywords": ["planet"]}
            for index in range(6)
        ],
    )
    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True}).status_code == 200

    first = client.get("/public/trivia/random", params={"limit": 4, "q": "planet"}).json()
    params = [("limit", "4"), ("q", "planet"), *(("exclude_id", item["id"]) for item in first)]
    refreshed = client.get("/public/trivia/random", params=params).json()

    assert len(refreshed) == 4
    assert len({item["id"] for item in refreshed}) == 4
    assert len({item["id"] for item in refreshed} - {item["id"] for item in first}) == 2


def test_admin_trivia_search_includes_unpublished_items_and_paginates(client):
    speaker = _speaker(client)
    published = _episode(client, [speaker["id"]])
    unpublished = _episode(client, [speaker["id"]])
    _seed_custom_trivia(
        published["id"],
        [{"question": "A hidden comet clue?", "answer": "Published answer.", "keywords": ["orbit"]}],
    )
    _seed_custom_trivia(
        unpublished["id"],
        [{"question": "A hidden comet clue?", "answer": "Draft answer.", "keywords": ["orbit"]}],
    )
    assert client.patch(f"/episodes/{published['id']}/publication", json={"is_published": True}).status_code == 200

    first = client.get("/trivia/search", params={"q": "hidden orbit", "page": 1, "page_size": 1})
    assert first.status_code == 200
    assert first.json()["total_items"] == 2
    assert first.json()["total_pages"] == 2

    second = client.get("/trivia/search", params={"q": "hidden orbit", "page": 2, "page_size": 1}).json()
    assert second["page"] == 2
    returned = [*first.json()["items"], *second["items"]]
    assert {item["episode"]["is_published"] for item in returned} == {True, False}
    assert {item["answer"] for item in returned} == {"Published answer.", "Draft answer."}


def test_trivia_search_uses_full_text_terms_without_episode_or_speaker_metadata(client):
    speaker = _speaker(client, "Nebula Guest")
    episode = _episode(client, [speaker["id"]])
    _seed_custom_trivia(
        episode["id"],
        [{"question": "Which planet has unusual rotation?", "answer": "Venus.", "keywords": ["orbit"]}],
    )
    assert client.patch(
        f"/episodes/{episode['id']}",
        json={
            "episode_title": "Nebula Special",
            "episode_number": episode["episode_number"],
            "episode_description": episode["episode_description"],
            "published_at": episode["published_at"],
            "source_url": episode["source_url"],
            "speaker_ids": [speaker["id"]],
            "is_published": True,
        },
    ).status_code == 200

    word_form_match = client.get("/public/trivia/random", params={"limit": 4, "q": "rotating planets"})
    assert word_form_match.status_code == 200
    assert [item["answer"] for item in word_form_match.json()] == ["Venus."]

    assert client.get("/public/trivia/random", params={"limit": 4, "q": "nebula"}).json() == []
    assert client.get("/trivia/search", params={"q": "nebula"}).json()["total_items"] == 0


def test_trivia_search_index_refreshes_after_edit_delete_and_publication_changes(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    trivia_id = _seed_trivia(episode["id"])
    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True}).status_code == 200

    assert client.get("/public/trivia/random", params={"limit": 4, "q": "original"}).json()[0]["id"] == trivia_id

    update = client.patch(
        f"/trivia/{trivia_id}",
        json={"question": "Edited asteroid question?", "answer": "Ceres.", "keywords": ["asteroid"]},
    )
    assert update.status_code == 200
    assert client.get("/trivia/search", params={"q": "asteroids"}).json()["total_items"] == 1
    assert client.get("/trivia/search", params={"q": "original"}).json()["total_items"] == 0

    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": False}).status_code == 200
    assert client.get("/public/trivia/random", params={"limit": 4, "q": "asteroid"}).json() == []
    assert client.get("/trivia/search", params={"q": "asteroid"}).json()["total_items"] == 1

    assert client.delete(f"/trivia/{trivia_id}").status_code == 204
    assert client.get("/trivia/search", params={"q": "asteroid"}).json()["total_items"] == 0


def test_trivia_candidate_generation_reviews_before_apply(client, monkeypatch):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    live_trivia_id = _seed_trivia(episode["id"])
    with get_connection() as conn:
        save_transcript(
            conn,
            episode["id"],
            "/tmp/transcript.json",
            {"segments": [{"start": 0, "end": 1, "text": "Candidate fact", "speaker": "SPEAKER_00"}]},
        )
        replace_speaker_mapping(conn, episode["id"], {"SPEAKER_00": speaker["id"]})
    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True}).status_code == 200

    def fake_run_trivia_extraction(transcript, episode_dir, request, settings):
        episode_dir.mkdir(parents=True, exist_ok=True)
        artifact = {
            "model": "gemini-test",
            "usage": {
                "estimated": {"input_tokens": 100, "estimated_input_cost_usd": 0.0001},
                "actual": {
                    "prompt_token_count": 100,
                    "candidates_token_count": 20,
                    "thoughts_token_count": 0,
                    "total_token_count": 120,
                    "actual_cost_usd": 0.0002,
                },
            },
            "trivia": [
                {
                    "type": "mentioned_trivia",
                    "question": "Candidate question?",
                    "answer": "Candidate answer.",
                    "keywords": ["candidate", "search"],
                    "timestamps": {"start": 0, "end": 1, "display": "00:00:00-00:00:01"},
                    "speaker_diarization": {"asker_speaker": "SPEAKER_00"},
                    "confidence": "high",
                }
            ],
        }
        path = episode_dir / "trivia.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        return [], path

    monkeypatch.setattr("backend.app.workers.run_trivia_extraction", fake_run_trivia_extraction)

    response = client.post(f"/episodes/{episode['id']}/trivia-candidates", json={})
    assert response.status_code == 202
    assert client.get(f"/jobs/{response.json()['job_id']}").json()["status"] == "succeeded"

    assert client.get(f"/episodes/{episode['id']}/trivia").json()[0]["id"] == live_trivia_id
    assert client.get(f"/episodes/{episode['id']}").json()["is_published"] is True

    review = client.get(f"/episodes/{episode['id']}/trivia-candidates/current").json()
    assert review["current_trivia"][0]["answer"] == "Original answer."
    assert review["candidate"]["status"] == "ready"
    assert review["candidate"]["release_version"] == "V2.1"
    assert review["candidate"]["trivia"][0]["answer"] == "Candidate answer."
    assert review["candidate"]["trivia"][0]["asker"] == speaker

    apply = client.post(f"/episodes/{episode['id']}/trivia-candidates/{review['candidate']['id']}/apply")
    assert apply.status_code == 200
    assert apply.json()["status"] == "applied"
    assert apply.json()["release_version"] == "V2.1"
    live = client.get(f"/episodes/{episode['id']}/trivia").json()
    assert len(live) == 1
    assert live[0]["id"] == f"{episode['id']}-trivia-0001"
    assert live[0]["answer"] == "Candidate answer."
    episode_detail = client.get(f"/episodes/{episode['id']}").json()
    assert episode_detail["is_published"] is False
    assert episode_detail["trivia_extraction"]["release_version"] == "V2.1"
    assert episode_detail["trivia_extraction"]["is_current_release"] is True
    assert episode_detail["trivia_extraction"]["source_candidate_id"] == review["candidate"]["id"]
    assert client.get("/trivia/search", params={"q": "candidate search"}).json()["total_items"] == 1


def test_trivia_candidate_discard_keeps_live_trivia(client, monkeypatch):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    _seed_trivia(episode["id"])
    with get_connection() as conn:
        save_transcript(
            conn,
            episode["id"],
            "/tmp/transcript.json",
            {"segments": [{"start": 0, "end": 1, "text": "Discard fact", "speaker": "SPEAKER_00"}]},
        )
        replace_speaker_mapping(conn, episode["id"], {"SPEAKER_00": speaker["id"]})

    def fake_run_trivia_extraction(transcript, episode_dir, request, settings):
        episode_dir.mkdir(parents=True, exist_ok=True)
        artifact = {
            "model": "gemini-test",
            "usage": {"estimated": {"input_tokens": 1, "estimated_input_cost_usd": 0}, "actual": {}},
            "trivia": [
                {
                    "type": "mentioned_trivia",
                    "question": "Discard candidate?",
                    "answer": "Discarded.",
                    "keywords": ["discard"],
                    "timestamps": {"start": 0, "end": 1, "display": "00:00:00-00:00:01"},
                    "speaker_diarization": {},
                    "confidence": "medium",
                }
            ],
        }
        path = episode_dir / "trivia.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        return [], path

    monkeypatch.setattr("backend.app.workers.run_trivia_extraction", fake_run_trivia_extraction)

    response = client.post(f"/episodes/{episode['id']}/trivia-candidates", json={})
    candidate = client.get(f"/episodes/{episode['id']}/trivia-candidates/current").json()["candidate"]
    discard = client.post(f"/episodes/{episode['id']}/trivia-candidates/{candidate['id']}/discard")

    assert response.status_code == 202
    assert discard.status_code == 200
    assert discard.json()["status"] == "discarded"
    assert client.get(f"/episodes/{episode['id']}/trivia").json()[0]["answer"] == "Original answer."


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
    episode_detail = client.get(f"/episodes/{episode['id']}").json()
    assert episode_detail["is_published"] is False
    assert episode_detail["trivia_extraction"]["release_version"] == "V2.1"
    assert episode_detail["trivia_extraction"]["is_current_release"] is True
    assert client.get(f"/public/episodes/{episode['id']}").status_code == 404


def test_episode_publication_and_permanent_delete(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    trivia_id = _seed_labeled_trivia(episode["id"], speaker["id"])
    with get_connection() as conn:
        save_transcript(
            conn,
            episode["id"],
            f"data/episodes/{episode['id']}/transcript.json",
            {"segments": [{"start": 0, "end": 1, "text": "Fact", "speaker": "SPEAKER_00"}]},
        )
        job = create_job(conn, episode["id"], "extract_trivia")
        update_job_status(conn, job["id"], "succeeded")
        conn.execute(
            "INSERT INTO gemini_usage VALUES (?, ?, ?, ?, 'v1', ?, ?, ?, ?, ?, ?)",
            ["usage-1", job["id"], episode["id"], "gemini-test", "transcript-hash", 10, 5, 0.01, 0.01, "2026-07-04"],
        )

    settings = get_settings()
    generated_dir = settings.episode_root / episode["id"]
    generated_dir.mkdir(parents=True)
    (generated_dir / "trivia.json").write_text("{}", encoding="utf-8")
    upload_dir = settings.upload_root / episode["id"]
    assert upload_dir.exists()

    publish = client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True})
    assert publish.status_code == 200
    assert publish.json()["is_published"] is True
    assert publish.json()["active_job"] is None
    public_episode = client.get(f"/public/episodes/{episode['id']}")
    assert public_episode.status_code == 200
    assert "trivia_extraction" not in public_episode.json()

    unpublish = client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": False})
    assert unpublish.status_code == 200
    assert client.get(f"/public/episodes/{episode['id']}").status_code == 404

    response = client.delete(f"/episodes/{episode['id']}")
    assert response.status_code == 204
    assert client.get(f"/episodes/{episode['id']}").status_code == 404
    assert not upload_dir.exists()
    assert not generated_dir.exists()
    with get_connection() as conn:
        for table in ("episodes", "episode_speakers", "episode_speaker_mappings", "episode_trivia_extractions", "transcripts", "trivia_items", "jobs"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {('id' if table == 'episodes' else 'episode_id')} = ?", [episode["id"]]).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM gemini_usage WHERE episode_id = ?", [episode["id"]]).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM speakers WHERE id = ?", [speaker["id"]]).fetchone()[0] == 1
    assert trivia_id


def test_active_episode_job_blocks_publication_and_deletion(client):
    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    with get_connection() as conn:
        job = create_job(conn, episode["id"], "transcribe")

    detail = client.get(f"/episodes/{episode['id']}")
    assert detail.status_code == 200
    assert detail.json()["active_job"]["id"] == job["id"]
    assert client.patch(f"/episodes/{episode['id']}/publication", json={"is_published": True}).status_code == 409
    assert client.delete(f"/episodes/{episode['id']}").status_code == 409

    with get_connection() as conn:
        update_job_status(conn, job["id"], "failed", "test complete")
    assert client.get(f"/episodes/{episode['id']}").json()["active_job"] is None


def test_episode_delete_cleans_object_storage_and_keeps_record_on_cleanup_failure(client, monkeypatch):
    from backend.app.routes import episodes as episode_routes

    class RecordingStorage:
        def __init__(self):
            self.objects = []
            self.prefixes = []
            self.fail = False

        def delete_object(self, key):
            if self.fail:
                raise RuntimeError("storage unavailable")
            self.objects.append(key)

        def delete_prefix(self, prefix):
            self.prefixes.append(prefix)

    speaker = _speaker(client)
    episode = _episode(client, [speaker["id"]])
    storage = RecordingStorage()
    monkeypatch.setattr(episode_routes, "get_object_storage", lambda settings: storage)
    with get_connection() as conn:
        conn.execute(
            "UPDATE episodes SET audio_path = ?, audio_object_key = ?, artwork_object_key = ? WHERE id = ?",
            [
                f"episodes/{episode['id']}/source.mp3",
                f"episodes/{episode['id']}/source.mp3",
                f"episodes/{episode['id']}/artwork",
                episode["id"],
            ],
        )
        job = create_job(conn, episode["id"], "transcribe")
        update_job_status(conn, job["id"], "succeeded")
        conn.execute("UPDATE jobs SET artifact_key = ? WHERE id = ?", [f"artifacts/{episode['id']}/transcript.json", job["id"]])

    storage.fail = True
    failed = client.delete(f"/episodes/{episode['id']}")
    assert failed.status_code == 500
    assert client.get(f"/episodes/{episode['id']}").status_code == 200

    storage.fail = False
    deleted = client.delete(f"/episodes/{episode['id']}")
    assert deleted.status_code == 204
    assert storage.objects == [
        f"episodes/{episode['id']}/source.mp3",
        f"episodes/{episode['id']}/artwork",
        f"artifacts/{episode['id']}/transcript.json",
    ]
    assert storage.prefixes == [f"artifacts/{episode['id']}/"]


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
