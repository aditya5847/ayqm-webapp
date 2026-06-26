import json
from pathlib import Path
from types import SimpleNamespace


def create_speaker(client, name="Ada"):
    response = client.post("/speakers", json={"name": name})
    assert response.status_code == 201
    return response.json()


def upload_episode(client, speaker_ids=None, extra_data=None):
    speakers = speaker_ids or [create_speaker(client)["id"]]
    data = {
        "episode_title": "Episode 1",
        "episode_number": 1,
        "episode_description": "A test episode.",
        "source_url": "https://example.com/episode-1",
        "speaker_ids": json.dumps(speakers),
        "extra_metadata": json.dumps(extra_data or {"season": "test"}),
    }
    return client.post(
        "/episodes",
        data=data,
        files={"file": ("episode.mp3", b"fake audio", "audio/mpeg")},
    )


def test_speaker_crud(client):
    speaker = create_speaker(client, "Ada")

    list_response = client.get("/speakers")
    assert list_response.status_code == 200
    assert list_response.json() == [speaker]

    update_response = client.patch(f"/speakers/{speaker['id']}", json={"name": "Grace"})
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Grace"

    delete_response = client.delete(f"/speakers/{speaker['id']}")
    assert delete_response.status_code == 204


def test_upload_episode_persists_metadata_and_speakers(client):
    speaker = create_speaker(client, "Ada")
    response = upload_episode(client, [speaker["id"]])

    assert response.status_code == 201
    episode = response.json()
    assert episode["episode_title"] == "Episode 1"
    assert episode["episode_number"] == 1
    assert episode["episode_description"] == "A test episode."
    assert episode["extra_metadata"] == {"season": "test"}
    assert episode["speakers"] == [speaker]
    assert episode["transcript_status"] == "missing"
    assert episode["trivia_status"] == "missing"
    assert "title" not in episode
    assert "show_name" not in episode
    assert "show_title" not in episode

    list_response = client.get("/episodes")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_upload_requires_non_empty_existing_speaker_ids(client):
    empty_response = client.post(
        "/episodes",
        data={
            "episode_title": "Episode 1",
            "episode_number": 1,
            "speaker_ids": "[]",
        },
        files={"file": ("episode.mp3", b"fake audio", "audio/mpeg")},
    )
    assert empty_response.status_code == 422

    unknown_response = upload_episode(client, ["missing-speaker-id"])
    assert unknown_response.status_code == 422
    assert unknown_response.json()["detail"]["unknown_speaker_ids"] == ["missing-speaker-id"]


def test_upload_requires_integer_episode_number(client):
    speaker = create_speaker(client)
    response = client.post(
        "/episodes",
        data={
            "episode_title": "Episode 1",
            "episode_number": "one",
            "speaker_ids": json.dumps([speaker["id"]]),
        },
        files={"file": ("episode.mp3", b"fake audio", "audio/mpeg")},
    )

    assert response.status_code == 422


def test_invalid_upload_json_returns_400(client):
    response = client.post(
        "/episodes",
        data={
            "episode_title": "Episode 1",
            "episode_number": 1,
            "speaker_ids": "{not-json",
        },
        files={"file": ("episode.mp3", b"fake audio", "audio/mpeg")},
    )

    assert response.status_code == 400


def test_delete_speaker_in_use_returns_409(client):
    speaker = create_speaker(client)
    upload_episode(client, [speaker["id"]])

    response = client.delete(f"/speakers/{speaker['id']}")

    assert response.status_code == 409


def test_extract_before_transcript_returns_409(client):
    episode_id = upload_episode(client).json()["id"]

    response = client.post(f"/episodes/{episode_id}/extract-trivia", json={})

    assert response.status_code == 409


def test_transcription_job_saves_transcript_and_uses_speaker_count(client, monkeypatch):
    speaker_1 = create_speaker(client, "Ada")
    speaker_2 = create_speaker(client, "Grace")
    episode_id = upload_episode(client, [speaker_1["id"], speaker_2["id"]]).json()["id"]
    seen_request = {}

    def fake_run_transcription(audio_path, episode_dir, request, settings):
        seen_request["diarize"] = request.diarize
        seen_request["min_speakers"] = request.min_speakers
        seen_request["max_speakers"] = request.max_speakers
        transcript_path = episode_dir / "transcript.json"
        return {"segments": [{"start": 0, "end": 1, "text": "Question?", "speaker": "SPEAKER_00"}]}, transcript_path

    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr("backend.app.workers.run_transcription", fake_run_transcription)

    response = client.post(f"/episodes/{episode_id}/transcribe", json={})

    assert response.status_code == 202
    job = client.get(f"/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "succeeded"
    assert seen_request == {"diarize": True, "min_speakers": 2, "max_speakers": 2}

    transcript = client.get(f"/episodes/{episode_id}/transcript")
    assert transcript.status_code == 200
    assert transcript.json()["transcript"]["segments"][0]["text"] == "Question?"


def test_transcription_requires_hf_token_by_default(client, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    episode_id = upload_episode(client).json()["id"]

    response = client.post(f"/episodes/{episode_id}/transcribe", json={})

    assert response.status_code == 422
    assert "HF_TOKEN" in response.json()["detail"]


def test_transcription_can_disable_diarization(client, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    episode_id = upload_episode(client).json()["id"]
    seen_request = {}

    def fake_run_transcription(audio_path, episode_dir, request, settings):
        seen_request["diarize"] = request.diarize
        return {"segments": [{"start": 0, "end": 1, "text": "No labels"}]}, episode_dir / "transcript.json"

    monkeypatch.setattr("backend.app.workers.run_transcription", fake_run_transcription)

    response = client.post(f"/episodes/{episode_id}/transcribe", json={"diarize": False})

    assert response.status_code == 202
    assert client.get(f"/jobs/{response.json()['job_id']}").json()["status"] == "succeeded"
    assert seen_request == {"diarize": False}


def test_failed_transcription_job_records_error(client, monkeypatch):
    episode_id = upload_episode(client).json()["id"]

    def fake_run_transcription(audio_path, episode_dir, request, settings):
        raise RuntimeError("transcription failed")

    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr("backend.app.workers.run_transcription", fake_run_transcription)

    response = client.post(f"/episodes/{episode_id}/transcribe", json={})

    assert response.status_code == 202
    job = client.get(f"/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert "transcription failed" in job["error"]


def test_process_endpoint_requires_transcribe_map_extract_flow(client, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-token")
    episode_id = upload_episode(client).json()["id"]

    response = client.post(f"/episodes/{episode_id}/process", json={})

    assert response.status_code == 409
    assert "speaker mapping" in response.json()["detail"]


def test_speaker_labels_mapping_and_trivia_flow(client, monkeypatch):
    speaker = create_speaker(client, "Ada")
    episode_id = upload_episode(client, [speaker["id"]]).json()["id"]

    def fake_run_transcription(audio_path, episode_dir, request, settings):
        transcript_path = episode_dir / "transcript.json"
        return {
            "segments": [
                {"start": 0, "end": 5, "text": "A fact.", "speaker": "SPEAKER_00"},
                {"start": 6, "end": 8, "text": "Another fact.", "speaker": "SPEAKER_00"},
            ]
        }, transcript_path

    def fake_run_trivia_extraction(transcript, episode_dir, request, settings):
        trivia = [
            SimpleNamespace(
                model_dump=lambda: {
                    "id": "trivia_001",
                    "type": "asked_question",
                    "question": "What was mentioned?",
                    "answer": "A fact.",
                    "keywords": ["fact"],
                    "timestamps": {"start": 0.0, "end": 2.0, "display": "00:00:00-00:00:02"},
                    "speaker_diarization": {"asker_speaker": "SPEAKER_00"},
                    "confidence": "high",
                }
            )
        ]
        return trivia, episode_dir / "trivia.json"

    def fake_ensure_sample_clip(**kwargs):
        suffix = f"-{kwargs['sample_index']}" if kwargs.get("sample_index") is not None else ""
        output_path = Path(kwargs["output_dir"]) / f"{kwargs['label']}{suffix}.mp3"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"fake mp3 {suffix}".encode())
        return output_path

    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr("backend.app.workers.run_transcription", fake_run_transcription)
    monkeypatch.setattr("backend.app.workers.run_trivia_extraction", fake_run_trivia_extraction)
    monkeypatch.setattr("backend.app.routes.episodes.ensure_sample_clip", fake_ensure_sample_clip)

    transcribe_response = client.post(f"/episodes/{episode_id}/transcribe", json={})

    assert transcribe_response.status_code == 202
    job = client.get(f"/jobs/{transcribe_response.json()['job_id']}").json()
    assert job["status"] == "succeeded"

    blocked_trivia_response = client.post(f"/episodes/{episode_id}/extract-trivia", json={})
    assert blocked_trivia_response.status_code == 409
    assert blocked_trivia_response.json()["detail"] == {"unmapped_speaker_labels": ["SPEAKER_00"]}

    labels_response = client.get(f"/episodes/{episode_id}/speaker-labels")
    assert labels_response.status_code == 200
    labels = labels_response.json()
    assert labels["speakers"] == [speaker]
    assert labels["labels"][0]["label"] == "SPEAKER_00"
    assert labels["labels"][0]["segment_count"] == 2
    assert labels["labels"][0]["sample_clip_url"] == f"/episodes/{episode_id}/speaker-labels/SPEAKER_00/sample"
    assert labels["labels"][0]["samples"][0]["sample_clip_url"] == (
        f"/episodes/{episode_id}/speaker-labels/SPEAKER_00/samples/0"
    )
    assert labels["labels"][0]["samples"][1]["sample_clip_url"] == (
        f"/episodes/{episode_id}/speaker-labels/SPEAKER_00/samples/1"
    )

    sample_response = client.get(f"/episodes/{episode_id}/speaker-labels/SPEAKER_00/sample")
    assert sample_response.status_code == 200
    assert sample_response.content == b"fake mp3 "

    indexed_sample_response = client.get(f"/episodes/{episode_id}/speaker-labels/SPEAKER_00/samples/1")
    assert indexed_sample_response.status_code == 200
    assert indexed_sample_response.content == b"fake mp3 -1"

    mapping_response = client.put(
        f"/episodes/{episode_id}/speaker-mapping",
        json={"mappings": {"SPEAKER_00": speaker["id"]}},
    )
    assert mapping_response.status_code == 200
    assert mapping_response.json()["mappings"]["SPEAKER_00"] == speaker

    trivia_response = client.post(f"/episodes/{episode_id}/extract-trivia", json={})
    assert trivia_response.status_code == 202
    trivia_job = client.get(f"/jobs/{trivia_response.json()['job_id']}").json()
    assert trivia_job["status"] == "succeeded"

    mapped_trivia = client.get(f"/episodes/{episode_id}/trivia")
    assert mapped_trivia.status_code == 200
    assert mapped_trivia.json()[0]["answer"] == "A fact."
    assert mapped_trivia.json()[0]["asker"] == speaker
