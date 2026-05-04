"""Voice tone analysis using Librosa: pitch, pauses, nervous detection, energy."""

try:
    import librosa
except Exception:
    librosa = None
try:
    import numpy as np
except Exception:
    np = None


def _fallback():
    """Safe fallback when audio cannot be loaded or analyzed. Never crashes."""
    return {
        "tone": "unknown",
        "confidence": "low",
        "pauses": 0,
        "energy": 0,
        "pitch_mean_hz": 0,
        "pitch_variance": 0,
        "speaking_rate": 0,
        "silence_duration_sec": 0,
        "silence_ratio": 0,
        "energy_mean": 0,
        "nervous_score": 50,
        "summary": "Could not load audio for analysis.",
    }


def analyze_voice(audio_path: str) -> dict:
    """Analyze voice for pitch, pauses, nervous indicators, and energy."""
    if librosa is None or np is None:
        data = _fallback()
        data["summary"] = "Voice analysis skipped: librosa/numpy not installed."
        return data
    try:
        y, sr = librosa.load(audio_path, sr=None)
    except Exception:
        return _fallback()

    try:
        duration = len(y) / sr
        if duration < 0.5:
            return {
                "tone": "unknown",
                "confidence": "low",
                "pauses": 0,
                "energy": 0,
                "pitch_mean_hz": 0,
                "pitch_variance": 0,
                "speaking_rate": 0,
                "silence_duration_sec": 0,
                "silence_ratio": 0,
                "energy_mean": 0,
                "nervous_score": 50,
                "summary": "Audio too short for analysis.",
            }

        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_hz = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            p = pitches[index, t]
            if p > 0:
                pitch_hz.append(float(p))

        pitch_mean = float(np.mean(pitch_hz)) if pitch_hz else 0
        pitch_var = float(np.var(pitch_hz)) if len(pitch_hz) > 1 else 0

        try:
            intervals = librosa.effects.split(y, top_db=25)
        except Exception:
            intervals = []
        speech_duration = sum((e - s) / sr for s, e in intervals)
        silence_duration = max(0, duration - speech_duration)
        silence_ratio = silence_duration / duration if duration > 0 else 0

        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        speaking_rate = float(tempo) if not np.isnan(tempo) else 0

        # Pitch variance can explode on noisy inputs; use a bounded jitter proxy.
        pitch_std = float(np.sqrt(max(0.0, pitch_var)))
        jitter_ratio = pitch_std / (pitch_mean + 1e-6) if pitch_mean > 0 else 0.0  # ~0.05–0.30 typical
        jitter_ratio = float(min(1.0, max(0.0, jitter_ratio)))  # bound

        # Nervousness heuristic: balance pauses + jitter, avoid pegging at 100.
        nervous_score = 25.0 + (silence_ratio * 55.0) + (jitter_ratio * 35.0)
        nervous_score = float(min(100.0, max(0.0, nervous_score)))

        summary_parts = []
        if pitch_mean > 0:
            summary_parts.append(f"Average pitch: {pitch_mean:.1f} Hz.")
        if silence_ratio > 0.3:
            summary_parts.append("Noticeable pauses; consider speaking more steadily.")
        elif silence_ratio < 0.1 and duration > 5:
            summary_parts.append("Steady speaking pace with few long pauses.")
        if nervous_score > 65:
            summary_parts.append("Some variation in tone suggests nervousness; deep breaths can help.")
        elif nervous_score < 45:
            summary_parts.append("Calm, consistent tone detected.")
        if energy_mean < 0.01:
            summary_parts.append("Low volume; try speaking slightly louder.")
        else:
            summary_parts.append("Energy level is adequate.")

        return {
            "tone": "analyzed",
            "confidence": "high" if pitch_hz else "low",
            "pauses": round(silence_duration, 2),
            "energy": round(energy_mean, 4),
            "pitch_mean_hz": round(pitch_mean, 2),
            "pitch_variance": round(pitch_var, 2),
            "speaking_rate": round(speaking_rate, 2),
            "silence_duration_sec": round(silence_duration, 2),
            "silence_ratio": round(silence_ratio, 2),
            "energy_mean": round(energy_mean, 4),
            "nervous_score": round(min(100, max(0, nervous_score)), 1),
            "summary": " ".join(summary_parts) if summary_parts else "Voice analysis complete.",
        }
    except Exception:
        return _fallback()
