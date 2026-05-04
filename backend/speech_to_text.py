"""Speech-to-text using OpenAI Whisper with low-latency defaults."""

import os
import shutil

def _ensure_ffmpeg_on_path() -> None:
    """
    Whisper uses ffmpeg CLI under the hood. Ensure `ffmpeg` is discoverable.
    Winget installs FFmpeg under LOCALAPPDATA; we add its bin to PATH at runtime.
    """
    if shutil.which("ffmpeg"):
        return
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return
    winget_bin = os.path.join(
        local,
        "Microsoft",
        "WinGet",
        "Packages",
        "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
        "ffmpeg-8.1-full_build",
        "bin",
    )
    if os.path.isdir(winget_bin):
        os.environ["PATH"] = winget_bin + os.pathsep + os.environ.get("PATH", "")

try:
    import whisper
except Exception:
    whisper = None


_model = None
_model_name = None


def get_model():
    global _model, _model_name
    _ensure_ffmpeg_on_path()
    if whisper is None:
        return None
    # Default to tiny.en for lower latency on CPU; override via WHISPER_MODEL.
    name = (os.environ.get("WHISPER_MODEL") or "tiny.en").strip()
    if _model is None or _model_name != name:
        # Keep CPU inference responsive for interview turn-by-turn UX.
        _model = whisper.load_model(name, device="cpu")
        _model_name = name
    return _model


def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text."""
    _ensure_ffmpeg_on_path()
    model = get_model()
    if model is None:
        return "[Transcription unavailable: Whisper not installed]"
    try:
        result = model.transcribe(
            audio_path,
            fp16=False,
            language="en",
            task="transcribe",
            temperature=0.0,
            # Fast decode profile for near-real-time feedback.
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        text = (result.get("text") or "").strip()
        return text or "[No speech detected]"
    except Exception as e:
        return f"[Transcription failed: {e}]"
