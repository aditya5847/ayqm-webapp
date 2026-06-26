from backend.app.services.speaker_labels import ensure_sample_clip, summarize_speaker_labels


def test_summarize_speaker_labels_uses_segments_and_words():
    transcript = {
        "segments": [
            {"start": 0, "end": 4, "text": "Hello", "speaker": "SPEAKER_00"},
            {
                "start": 5,
                "end": 8,
                "text": "Word-level speaker",
                "words": [{"start": 5.5, "end": 6.5, "word": "Word", "speaker": "SPEAKER_01"}],
            },
        ]
    }

    labels = summarize_speaker_labels(transcript)

    assert [item["label"] for item in labels] == ["SPEAKER_00", "SPEAKER_01"]
    assert labels[0]["segment_count"] == 1
    assert labels[0]["samples"][0]["text"] == "Hello"
    assert labels[1]["first_seen"] == 5.5


def test_ensure_sample_clip_caps_duration_at_three_seconds(tmp_path, monkeypatch):
    seen = {}

    def fake_run(args, check, capture_output):
        seen["args"] = args
        seen["check"] = check
        seen["capture_output"] = capture_output
        output_path = tmp_path / "SPEAKER_00.mp3"
        output_path.write_bytes(b"clip")

    monkeypatch.setattr("backend.app.services.speaker_labels.subprocess.run", fake_run)

    path = ensure_sample_clip(
        ffmpeg_path="ffmpeg",
        audio_path="/tmp/source.mp3",
        output_dir=tmp_path,
        label="SPEAKER_00",
        start=10,
        end=20,
    )

    assert path == tmp_path / "SPEAKER_00.mp3"
    assert seen["args"][seen["args"].index("-t") + 1] == "3.000"
    assert seen["check"] is True
    assert seen["capture_output"] is True


def test_ensure_sample_clip_supports_indexed_filenames(tmp_path, monkeypatch):
    def fake_run(args, check, capture_output):
        output_path = tmp_path / "SPEAKER_00-2.mp3"
        output_path.write_bytes(b"clip")

    monkeypatch.setattr("backend.app.services.speaker_labels.subprocess.run", fake_run)

    path = ensure_sample_clip(
        ffmpeg_path="ffmpeg",
        audio_path="/tmp/source.mp3",
        output_dir=tmp_path,
        label="SPEAKER_00",
        start=10,
        end=11,
        sample_index=2,
    )

    assert path == tmp_path / "SPEAKER_00-2.mp3"
