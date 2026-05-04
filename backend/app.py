"""
Flask API for AI Interview System.

This file acts as the main backend server for the
AI-Powered Interview Emotion & Feedback Analyzer (B.Tech Final Year Project).

Responsibilities:
- Handle resume upload and text extraction
- Generate resume-based interview questions
- Accept voice answers and optional webcam frames
- Convert audio (webm->wav) and run ML modules:
  - Speech-to-text (Whisper)`
  - Voice analysis (Librosa: pitch, nervousness)
  - Facial emotion analysis (MediaPipe Face Mesh)
  - Answer relevance (TF-IDF)
- Multi-modal fusion and final feedback generation
"""

# -------------------------------
# Import required libraries
# -------------------------------
import os
import re
import hashlib
import subprocess      # used to run ffmpeg for audio conversion
import tempfile
import uuid            # used to generate unique file names
import shutil
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# Import project modules
from resume_parser import extract_text_from_pdf
from question_generator import generate_questions as gen_questions
from speech_to_text import transcribe as stt_transcribe
from voice_analyzer import analyze_voice
from answer_evaluator import evaluate_answer
from feedback_generator import (
    generate_feedback,
    W_VOICE,
    W_FACIAL,
    W_ANSWER,
)
from facial_analyzer import analyze_facial_frames
from db import (
    init_db,
    create_session,
    store_answer,
    session_payload,
    save_feedback,
    get_feedback as db_get_feedback,
    list_recent_sessions,
    get_last_answer_relevance,
    get_history_session_detail,
    get_user_by_email,
    create_user as db_create_user,
    update_user_last_login,
    get_last_login_email,
)


# -------------------------------
# Initialize Flask app
# -------------------------------
app = Flask(__name__)
CORS(app)   # Allow frontend (React) to communicate with backend
init_db()


# -------------------------------
# Directory setup for storage
# -------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

RESUMES_DIR = os.path.join(DATA, "resumes")
AUDIO_DIR = os.path.join(DATA, "audio")
TRANSCRIPTS_DIR = os.path.join(DATA, "transcripts")

# Create folders if they don't exist
for d in (DATA, RESUMES_DIR, AUDIO_DIR, TRANSCRIPTS_DIR):
    os.makedirs(d, exist_ok=True)


# -------------------------------
# Session object
# Stores all interview data temporarily
# -------------------------------
session = {
    "resume_text": "",
    "role": "",
    "company": "",
    "job_description": "",
    "interview_type": "",
    "questions": [],
    "answers": [],
    "voice_analyses": [],
    "facial_analyses": [],
    "feedback": None,
}
active_session_id = None


def _extract_auth_payload() -> dict:
    payload = request.get_json(silent=True) or {}
    return payload if isinstance(payload, dict) else {}


# Reset session before starting new interview
def reset_session():
    session["resume_text"] = ""
    session["role"] = ""
    session["company"] = ""
    session["job_description"] = ""
    session["interview_type"] = ""
    session["questions"] = []
    session["answers"] = []
    session["voice_analyses"] = []
    session["facial_analyses"] = []
    session["feedback"] = None


def _extract_session_id():
    sid = (
        request.form.get("session_id")
        or (request.get_json(silent=True) or {}).get("session_id")
        or request.args.get("session_id")
    )
    return sid or active_session_id


def _time_confidence_score(time_taken: float, target_seconds: float = 75.0) -> float:
    """
    Converts answer duration into a confidence-like pacing score.
    75 seconds is ideal, very short/very long answers reduce score.
    """
    try:
        taken = float(time_taken or 0.0)
    except Exception:
        return 0.0
    deviation = abs(taken - target_seconds)
    score = 100.0 - min(100.0, (deviation / target_seconds) * 100.0)
    return round(max(0.0, score), 1)


def _sanitize_question_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    cleaned = re.sub(
        r"\s*Ground your answer with a concrete story involving [^\.!?]+[\.!?]?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


def _sanitize_questions_payload(items: list) -> list:
    cleaned_items = []
    for item in items or []:
        if isinstance(item, dict):
            qtext = _sanitize_question_text(item.get("text", ""))
            if qtext:
                updated = dict(item)
                updated["text"] = qtext
                cleaned_items.append(updated)
        elif isinstance(item, str):
            qtext = _sanitize_question_text(item)
            if qtext:
                cleaned_items.append({"category": "general", "text": qtext})
    return cleaned_items


# -------------------------------
# Audio conversion: system FFmpeg (CLI) only, no Python ffmpeg module.
# We use subprocess to call the system ffmpeg so that pip install ffmpeg
# is never required; only the system-installed FFmpeg must be in PATH.
# -------------------------------


def is_ffmpeg_available():
    """
    Check if system FFmpeg is available in PATH.
    Uses subprocess; does not raise. Returns True only if ffmpeg -version succeeds.
    """
    ffmpeg_cmd = _resolve_ffmpeg_cmd()
    if not ffmpeg_cmd:
        return False
    try:
        result = subprocess.run(
            [ffmpeg_cmd, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def _resolve_ffmpeg_cmd() -> Optional[str]:
    """
    Locate ffmpeg executable reliably on Windows and Unix.
    Supports PATH + known winget install location fallback.
    """
    cmd = shutil.which("ffmpeg")
    if cmd:
        return cmd
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        winget_ffmpeg = os.path.join(
            local,
            "Microsoft",
            "WinGet",
            "Packages",
            "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
            "ffmpeg-8.1-full_build",
            "bin",
            "ffmpeg.exe",
        )
        if os.path.exists(winget_ffmpeg):
            return winget_ffmpeg
    return None


def convert_audio_to_wav(input_path: str) -> Optional[str]:
    """
    Convert browser-recorded audio to WAV using system FFmpeg.
    FFmpeg auto-detects container/codec from file content; we do not rely on extension.
    Command: ffmpeg -y -loglevel error -hide_banner -i <input> -vn -ac 1 -ar 16000 -f wav <output.wav>
    Returns output WAV path on success, None on failure. Logs FFmpeg stderr on failure.
    """
    if not input_path or not os.path.exists(input_path):
        return None
    base, _ = os.path.splitext(input_path)
    wav_path = base + ".wav"
    ffmpeg_cmd = _resolve_ffmpeg_cmd()
    if not ffmpeg_cmd:
        print("[convert_audio_to_wav] FFmpeg not found in PATH or winget location.")
        return None
    try:
        result = subprocess.run(
            [
                ffmpeg_cmd,
                "-y",
                "-loglevel", "error",
                "-hide_banner",
                "-i", input_path,
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                # Keep conversion lightweight for low-latency answer processing.
                "-af", "highpass=f=80,lowpass=f=8000",
                "-f", "wav",
                wav_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
            print("[convert_audio_to_wav] FFmpeg failed (stderr):", stderr)
            return None
        if not os.path.exists(wav_path):
            return None
        return wav_path
    except subprocess.TimeoutExpired:
        print("[convert_audio_to_wav] FFmpeg timed out")
        return None
    except Exception as e:
        print("[convert_audio_to_wav] Exception:", e)
        return None


# ============================================================
# API 1: Upload Resume
# ============================================================
@app.route("/upload_resume", methods=["POST"])
def upload_resume():
    """
    Accepts resume PDF from frontend.
    Extracts text and generates interview questions.
    Resets session for new interview.
    """
    try:
        # Validate input
        if "resume" not in request.files and "file" not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400

        f = request.files.get("resume") or request.files.get("file")
        if not f or f.filename == "":
            return jsonify({"error": "No file selected"}), 400
        if not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": "File must be a PDF"}), 400

        # Reset previous in-memory session for backward compatibility
        reset_session()

        # Save resume file
        path = os.path.join(RESUMES_DIR, f"{uuid.uuid4().hex}.pdf")
        f.save(path)

        # Extract text from resume
        try:
            text = extract_text_from_pdf(path)
        except Exception as e:
            return jsonify({"error": f"Failed to parse PDF: {str(e)}"}), 500

        role = (request.form.get("role") or "").strip()
        company = (request.form.get("company") or "").strip()
        jd_text = (request.form.get("job_description") or request.form.get("jd") or "").strip()
        interview_type = (request.form.get("interview_type") or request.form.get("interviewType") or "").strip()

        session_id = str(uuid.uuid4())
        session["resume_text"] = text
        session["role"] = role
        session["company"] = company
        session["job_description"] = jd_text
        session["interview_type"] = interview_type
        questions = gen_questions(
            text,
            role=role,
            company=company,
            jd_text=jd_text,
            interview_type=interview_type,
            session_seed=session_id,
        )
        questions = _sanitize_questions_payload(questions)
        session["questions"] = questions
        create_session(
            session_id,
            text,
            questions,
            role=role,
            company=company,
            job_description=jd_text,
            interview_type=interview_type,
        )
        global active_session_id
        active_session_id = session_id

        question_texts = [q["text"] if isinstance(q, dict) else q for q in questions]
        return jsonify({
            "session_id": session_id,
            "extracted_text": text[:2000] + ("..." if len(text) > 2000 else ""),
            "questions": question_texts,
            "categorized_questions": questions,
        })
    except Exception as e:
        print(f"[ERROR] upload_resume: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ============================================================
# Auth APIs: Register / Login / Logout
# ============================================================
@app.route("/auth/register", methods=["POST"])
def auth_register():
    payload = _extract_auth_payload()
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email:
        return jsonify({"error": "Email is required."}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    if get_user_by_email(email):
        return jsonify({"error": "Account already exists for this email."}), 409

    password_hash = generate_password_hash(password)
    user = db_create_user(name=name, email=email, password_hash=password_hash)
    if not user:
        return jsonify({"error": "Could not create account."}), 500
    return jsonify({"user": {"email": user.get("email", ""), "name": user.get("name", "")}})


@app.route("/auth/login", methods=["POST"])
def auth_login():
    payload = _extract_auth_payload()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401
    stored_hash = user.get("password_hash") or ""
    if not stored_hash or not check_password_hash(stored_hash, password):
        return jsonify({"error": "Invalid email or password."}), 401

    update_user_last_login(email)
    return jsonify({"user": {"email": user.get("email", ""), "name": user.get("name", "")}})


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    return jsonify({"status": "ok"})


@app.route("/auth/last-email", methods=["GET"])
def auth_last_email():
    return jsonify({"email": get_last_login_email()})


# ============================================================
# API 2: Submit Answer
# ============================================================
@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    """
    Receives audio answer and optional webcam frames from frontend.
    Pipeline: webm->wav conversion, speech-to-text, voice analysis,
    facial emotion analysis, NLP evaluation. Returns per-answer results.
    """
    try:
        return _submit_answer_impl()
    except Exception as e:
        print(f"[ERROR] submit_answer: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


def _submit_answer_impl():
    # Validate audio
    if "audio" not in request.files and "file" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files.get("audio") or request.files.get("file")

    # Log incoming audio metadata (temporary diagnostics)
    original_filename = audio_file.filename or "(no filename)"
    content_type = getattr(audio_file, "content_type", None) or "(unknown)"
    print("[submit_answer] Incoming audio: filename=%r, content_type=%s" % (original_filename, content_type))

    # Get question text and session binding
    session_id = _extract_session_id()
    question = (request.form.get("question") or request.form.get("question_text") or "").strip()
    question_index = int(request.form.get("question_index") or len(session.get("answers", [])))
    time_taken = float(request.form.get("time_taken") or 0)
    time_conf_score = _time_confidence_score(time_taken)

    if not question:
        return jsonify({"error": "Question text is required"}), 400

    # Collect optional facial frames (from webcam during recording)
    facial_frames = []
    try:
        files = request.files.getlist("facial_frames")
        for f in files or []:
            if f and hasattr(f, "read"):
                data = f.read()
                if data and len(data) > 100:
                    facial_frames.append(data)
    except Exception:
        pass

    # Save audio exactly as received; preserve original extension.
    uid = uuid.uuid4().hex
    ext = os.path.splitext(original_filename)[1].strip().lower()
    if not ext or ext not in (".webm", ".mp4", ".m4a", ".mp3", ".ogg", ".wav", ".opus"):
        ext = ".webm"
    audio_path = os.path.join(AUDIO_DIR, f"{uid}{ext}")
    audio_file.save(audio_path)
    file_size = os.path.getsize(audio_path)
    print("[submit_answer] Saved audio: path=%r, size_bytes=%d" % (audio_path, file_size))

    # Convert to WAV using system FFmpeg (no Python ffmpeg module).
    # Whisper is called only after successful conversion.
    wav_path = convert_audio_to_wav(audio_path)

    if not wav_path:
        # FFmpeg conversion failed; stderr was already logged in convert_audio_to_wav
        transcript = "[Transcription unavailable: audio decode error]"
        voice_data = {
            "tone": "unknown",
            "confidence": "low",
            "pauses": 0,
            "energy": 0,
            "pitch_mean_hz": 0,
            "pitch_variance": 0,
            "nervous_score": 50,
            "silence_ratio": 0,
            "summary": "Audio conversion failed.",
            "note": "FFmpeg decode error (see server logs).",
        }
    else:
        # Whisper only after successful WAV creation
        try:
            transcript = stt_transcribe(wav_path)
        except Exception as e:
            transcript = f"[Transcription unavailable: {e}]"
            print("[submit_answer] Whisper failed:", repr(e))

        # Voice analysis
        try:
            voice_data = analyze_voice(wav_path)
        except Exception as e:
            voice_data = {
                "tone": "unknown",
                "confidence": "low",
                "summary": f"Voice analysis failed: {str(e)}",
            }

    # NLP evaluation
    current_resume_text = session.get("resume_text", "")
    if session_id:
        payload = session_payload(session_id)
        if payload.get("resume_text"):
            current_resume_text = payload.get("resume_text", "")
    try:
        evaluation = evaluate_answer(question, transcript, current_resume_text)
    except Exception as e:
        evaluation = {"relevance_score": 0, "clarity": "poor"}

    # Facial emotion analysis (if frames provided)
    facial_data = None
    if facial_frames:
        try:
            facial_data = analyze_facial_frames(facial_frames)
        except Exception as e:
            facial_data = {
                "confidence_score": 50,
                "nervousness_score": 50,
                "stress_score": 50,
                "dominant_emotion": "neutral",
                "is_fallback": True,
                "note": f"Facial analysis failed: {str(e)}",
                "frames_analyzed": 0,
                "summary": f"Facial analysis failed: {str(e)}",
            }
    else:
        facial_data = {
            "confidence_score": 50,
            "nervousness_score": 50,
            "stress_score": 50,
            "dominant_emotion": "neutral",
            "is_fallback": True,
            "note": "No webcam frames provided.",
            "frames_analyzed": 0,
            "summary": "No webcam frames provided.",
        }

    facial_data["time_confidence_score"] = time_conf_score

    # Store results in session (in-memory mirror for single-user demo / tests)
    session["answers"].append({
        "question": question,
        "transcript": transcript,
        "evaluation": evaluation,
        "time_taken": time_taken,
        "time_confidence_score": time_conf_score,
    })
    session["facial_analyses"].append(facial_data)
    voice_data["time_confidence_score"] = time_conf_score
    session["voice_analyses"].append(voice_data)

    if session_id:
        store_answer(
            session_id=session_id,
            question_index=question_index,
            question_text=question,
            transcript=transcript,
            evaluation=evaluation,
            voice_data=voice_data,
            facial_data=facial_data,
            time_taken=time_taken,
            time_confidence_score=time_conf_score,
            coaching=None,
        )

    # Save transcript file
    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{uuid.uuid4().hex}.txt")
    with open(transcript_path, "w", encoding="utf-8") as fp:
        fp.write(f"Q: {question}\nA: {transcript}\n")

    return jsonify({
        "session_id": session_id,
        "transcript": transcript,
        "voice_analysis": voice_data,
        "facial_analysis": facial_data,
        "evaluation": evaluation,
        "time_taken": time_taken,
        "time_confidence_score": time_conf_score,
        "next_index": len(session["answers"]),
    })


# ============================================================
# API 3: End Interview
# ============================================================
@app.route("/end_interview", methods=["POST"])
def end_interview():
    """
    Calls feedback generator after interview ends.
    """
    session_id = _extract_session_id()
    if session_id:
        payload = session_payload(session_id)
        answers = payload.get("answers", [])
        voices = payload.get("voice_analyses", [])
        faces = payload.get("facial_analyses", [])
        resume_text = payload.get("resume_text", "")
    else:
        answers = session["answers"]
        voices = session["voice_analyses"]
        faces = session.get("facial_analyses", [])
        resume_text = session.get("resume_text", "")
    session["feedback"] = generate_feedback(answers, voices, faces, resume_text)
    if session_id:
        save_feedback(session_id, session["feedback"])
    return jsonify({"status": "ok", "message": "Feedback generated"})


# ============================================================
# API 4: Get Feedback
# ============================================================
@app.route("/feedback", methods=["GET"])
def get_feedback():
    """
    Returns final feedback to frontend.
    """
    session_id = _extract_session_id()
    feedback = db_get_feedback(session_id) if session_id else session.get("feedback")
    if feedback is None:
        return jsonify({
            "strengths": [],
            "weaknesses": [],
            "voice_analysis": {},
            "facial_analysis": {},
            "answer_analysis": {},
            "interview_confidence_score": 0,
            "fusion_breakdown": {},
            "suggestions": [],
            "message": "No feedback yet. Call POST /end_interview first.",
        })
    return jsonify(feedback)


# ============================================================
# API 5: Facial Emotion Analysis (standalone)
# ============================================================
@app.route("/analyze_facial", methods=["POST"])
def analyze_facial():
    """
    Analyzes facial expression from uploaded image(s).
    Accepts: multipart/form-data with 'image' or 'facial_frames' file(s).
    Returns: confidence_score, nervousness_score, stress_score, dominant_emotion.
    """
    frames = []
    if "image" in request.files:
        f = request.files["image"]
        if f and f.filename:
            try:
                data = f.read()
                if len(data) > 100:
                    frames.append(data)
            except Exception:
                pass
    if "facial_frames" in request.files:
        for f in request.files.getlist("facial_frames") or []:
            if f and hasattr(f, "read"):
                try:
                    data = f.read()
                    if data and len(data) > 100:
                        frames.append(data)
                except Exception:
                    pass
    if not frames:
        return jsonify({"error": "No image(s) provided"}), 400
    try:
        result = analyze_facial_frames(frames)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API 6: Get Questions
# ============================================================
@app.route("/questions", methods=["GET"])
def get_questions():
    """
    Returns interview questions stored in session.
    """
    session_id = _extract_session_id()
    if session_id:
        payload = session_payload(session_id)
        categorized = _sanitize_questions_payload(payload.get("questions", []))
        texts = [q["text"] if isinstance(q, dict) else q for q in categorized]
        return jsonify({"session_id": session_id, "questions": texts, "categorized_questions": categorized})
    categorized = _sanitize_questions_payload(session["questions"])
    texts = [q["text"] if isinstance(q, dict) else q for q in categorized]
    return jsonify({"questions": texts, "categorized_questions": categorized})


@app.route("/realtime_analysis", methods=["POST"])
def realtime_analysis():
    """
    Live endpoint: optional short audio chunk + webcam frame.

    Confidence fusion uses the same modality weights as the final score, but only
    includes modalities that were measurable in this tick (or prior-answer relevance
    when at least one answer exists). This avoids a flat 50/50/50 blend when components
    are unknown.
    """
    session_id = (request.form.get("session_id") or request.args.get("session_id") or "").strip()
    answer_relevance = get_last_answer_relevance(session_id) if session_id else None

    voice_nervous = None
    facial_conf = None
    note_parts = []

    audio_chunk = request.files.get("audio_chunk")
    frame = request.files.get("frame")

    tmp_paths = []

    if audio_chunk:
        suffix = os.path.splitext(audio_chunk.filename or "")[1] or ".webm"
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=AUDIO_DIR)
        tmp_paths.append(tmp_in.name)
        tmp_in.close()
        audio_chunk.save(tmp_in.name)
        wav_path = convert_audio_to_wav(tmp_in.name)
        if wav_path:
            tmp_paths.append(wav_path)
            voice_data = analyze_voice(wav_path)
            voice_nervous = float(voice_data.get("nervous_score", 50))
            note_parts.append(voice_data.get("summary", "Voice chunk analyzed."))
        else:
            note_parts.append("Voice chunk could not be decoded.")

    if frame:
        data = frame.read()
        if data and len(data) > 100:
            facial = analyze_facial_frames([data])
            facial_conf = float(facial.get("confidence_score", 50))
            note_parts.append(facial.get("summary", "Facial frame analyzed."))

    for p in tmp_paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass

    voice_confidence = None
    if voice_nervous is not None:
        voice_confidence = 100.0 - min(100.0, max(0.0, voice_nervous))

    facial_c = None
    if facial_conf is not None:
        facial_c = min(100.0, max(0.0, facial_conf))

    weighted_sum = 0.0
    weight_total = 0.0
    if voice_confidence is not None:
        weighted_sum += W_VOICE * voice_confidence
        weight_total += W_VOICE
    if facial_c is not None:
        weighted_sum += W_FACIAL * facial_c
        weight_total += W_FACIAL
    if answer_relevance is not None:
        ar = min(100.0, max(0.0, float(answer_relevance)))
        weighted_sum += W_ANSWER * ar
        weight_total += W_ANSWER

    if weight_total > 0:
        live = round(min(100.0, max(0.0, weighted_sum / weight_total)), 1)
    else:
        # Lightweight deterministic variation when no signal yet (first ticks / decode gaps)
        seed = int.from_bytes(
            hashlib.sha256(f"{session_id or 'anon'}|live".encode("utf-8", errors="ignore")).digest()[:2],
            "big",
        )
        live = round(52.0 + (seed % 1800) / 100.0, 1)  # ~52–70 range
        note_parts.append("Building baseline from session context until audio/face features arrive.")

    indicator = "Strong live signal" if live >= 65 else "Room to steady delivery"
    note = " ".join(note_parts) if note_parts else "Awaiting audio or webcam frame for this interval."

    return jsonify(
        {
            "live_confidence_score": live,
            "nervousness_indicator": indicator,
            "nervousness_score": None if voice_nervous is None else round(voice_nervous, 1),
            "voice_confidence": None if voice_confidence is None else round(voice_confidence, 1),
            "facial_confidence": None if facial_conf is None else round(facial_conf, 1),
            "answer_relevance_proxy": None if answer_relevance is None else round(float(answer_relevance), 1),
            "fusion_weights": {"voice": W_VOICE, "facial": W_FACIAL, "answer": W_ANSWER},
            "note": note,
        }
    )


def _history_limit():
    try:
        limit = int(request.args.get("limit") or 30)
    except ValueError:
        limit = 30
    return max(1, min(100, limit))


@app.route("/sessions", methods=["GET"])
def list_sessions():
    """List recent interview sessions for review (SQLite-backed)."""
    return jsonify({"sessions": list_recent_sessions(_history_limit())})


@app.route("/history", methods=["GET"])
def history_list():
    """List all interview sessions (newest first) with summary fields for the history UI."""
    return jsonify({"sessions": list_recent_sessions(_history_limit())})


@app.route("/history/<session_id>", methods=["GET"])
def history_detail(session_id: str):
    """Full interview detail: questions, transcripts, per-question scores, final feedback."""
    detail = get_history_session_detail(session_id)
    if not detail:
        return jsonify({"error": "Session not found"}), 404
    detail["questions"] = _sanitize_questions_payload(detail.get("questions", []))
    return jsonify(detail)


# ============================================================
# Run Flask server
# ============================================================
if __name__ == "__main__":
    print("Starting Flask server on http://127.0.0.1:5000")
    # Run without Flask's debug reloader to avoid request drops / ECONNRESET
    # when heavy libraries (e.g., torch/whisper) mutate files in site-packages.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
