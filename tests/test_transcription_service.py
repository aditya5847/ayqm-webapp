from backend.app.config import Settings
from backend.app.schemas import TranscriptionRequest
from backend.app.services import transcription


def test_run_transcription_adds_whisperx_diarization_pipeline_compatibility(tmp_path, monkeypatch):
    seen = {}
    original = getattr(transcription.whisperx, "DiarizationPipeline", None)
    if original is not None:
        monkeypatch.delattr(transcription.whisperx, "DiarizationPipeline", raising=False)

    class FakePipeline:
        pass

    def fake_transcribe_audio(**kwargs):
        seen["has_pipeline"] = hasattr(transcription.whisperx, "DiarizationPipeline")
        return {"segments": []}

    monkeypatch.setattr("whisperx.diarize.DiarizationPipeline", FakePipeline)
    monkeypatch.setattr("backend.app.services.transcription.transcribe_audio", fake_transcribe_audio)

    run_result, _path = transcription.run_transcription(
        audio_path="/tmp/audio.mp3",
        episode_dir=tmp_path,
        request=TranscriptionRequest(diarize=True, hf_token="token"),
        settings=Settings(),
    )

    assert run_result == {"segments": []}
    assert seen["has_pipeline"] is True
    assert transcription.whisperx.DiarizationPipeline is FakePipeline
