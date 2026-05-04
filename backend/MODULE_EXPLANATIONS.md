# Full project module explanations (Backend + Frontend) (copy/paste for ChatGPT)

This document explains the whole project: both the backend (Flask + ML modules + SQLite) and the frontend (React UI + recording + API calls).

It also includes a suggested 4-member split so each member can explain their assigned files to ChatGPT (or for viva/project-report writeups).

---

## Whole project overview (end-to-end)

1. **Auth & workspace entry** (`frontend/src/AuthRoutes.jsx`)
   - Handles login/register and protects the interview workspace route.
   - Saves auth + theme in `localStorage`.

2. **Resume upload + question generation** (`frontend/src/App.jsx`, backend `POST /upload_resume`)
   - User uploads a PDF resume, selects an interview type, and optionally provides role/company/JD fields.
   - Backend extracts resume text (`resume_parser.py`) and generates questions (`question_generator.py` / optional LLM).
   - Backend creates a SQLite session (`db.py`) and returns `session_id` + questions.

3. **Answer recording + multimodal capture** (`frontend/src/Recorder.jsx`)
   - Browser records audio and captures webcam frames every ~2 seconds.
   - During recording, it sends periodic audio chunks + the latest frame to enable live confidence updates.

4. **Backend multimodal processing** (backend `POST /submit_answer` and `POST /realtime_analysis`)
   - Converts recorded audio to WAV using system `ffmpeg` (helper in `app.py`).
   - Runs:
     - Whisper STT (`speech_to_text.py`)
     - Voice heuristics (`voice_analyzer.py`)
     - Facial heuristics (`facial_analyzer.py`)
     - Transcript relevance/clarity scoring (`answer_evaluator.py`)

5. **Final feedback + scoring fusion** (backend `POST /end_interview`)
   - `feedback_generator.py` fuses:
     - voice: `W_VOICE = 0.35`
     - facial: `W_FACIAL = 0.25`
     - answer relevance: `W_ANSWER = 0.40`
   - Returns strengths, weaknesses, suggestions, and question-wise expected/star answers.
   - Persists everything in SQLite so “Past interviews” can show history.

## Suggested 4-member split

Backend modules in this repo = **10 files** (not divisible by 4), so the backend cannot be perfectly equal.
Frontend has **4 main files** in `frontend/src` used by the app.

Frontend is perfectly equal (1 file per member).
Backend is balanced as **3 / 3 / 2 / 2**.

### Member 1
- Frontend: `frontend/src/App.jsx`
- Backend (3): `backend/app.py`, `backend/db.py`, `backend/resume_parser.py`

### Member 2
- Frontend: `frontend/src/Recorder.jsx`
- Backend (3): `backend/speech_to_text.py`, `backend/voice_analyzer.py`, `backend/facial_analyzer.py`

### Member 3
- Frontend: `frontend/src/api.js`
- Backend (2): `backend/answer_evaluator.py`, `backend/question_generator.py`

### Member 4
- Frontend: `frontend/src/AuthRoutes.jsx`
- Backend (2): `backend/feedback_generator.py`, `backend/llm_helper.py`

---

## `app.py`

### Role
Main Flask server that exposes the REST API used by the React frontend. It:
- Accepts resume uploads and generates interview questions
- Accepts recorded answers (audio + optional webcam frames)
- Runs the multi-modal pipeline:
  - `speech_to_text.transcribe` (Whisper)
  - `voice_analyzer.analyze_voice` (Librosa heuristics)
  - `facial_analyzer.analyze_facial_frames` (MediaPipe FaceMesh + OpenCV heuristics)
  - `answer_evaluator.evaluate_answer` (rule-based + optional TF-IDF signal)
- Computes live confidence updates (chunk-by-chunk fusion)
- Generates and returns final feedback using `feedback_generator.generate_feedback`
- Persists sessions/answers/feedback using `db.py` (SQLite)

### Key helpers
- `reset_session()`: resets the in-memory session dict used for the single-user demo flow.
- `_extract_session_id()`: retrieves `session_id` from `form`, JSON body, or query params; falls back to `active_session_id`.
- `_time_confidence_score(time_taken, target_seconds=75)`: turns answer duration into a "pacing/confidence-like" score (closer to ideal length => higher score).
- `_sanitize_question_text(...)` and `_sanitize_questions_payload(...)`: strips trailing phrases that force story formatting.
- `convert_audio_to_wav(input_path)`: uses system `ffmpeg` (CLI via `subprocess`) to convert browser recordings to a WAV file that Whisper + Librosa can read.
  - It preserves the idea of “ffmpeg must exist on PATH”; it locates `ffmpeg` on Windows using the Winget install fallback.

### Routes (API endpoints)
- `POST /upload_resume`
  - Validates uploaded PDF
  - Extracts text via `resume_parser.extract_text_from_pdf`
  - Generates questions via `question_generator.generate_questions`
  - Creates a DB session via `db.create_session`
  - Returns:
    - `session_id`
    - extracted resume text (truncated)
    - `questions` + `categorized_questions`

- `POST /submit_answer`
  - Validates audio + required question text
  - Saves incoming audio file to `backend/data/audio/`
  - Converts to WAV using system ffmpeg
  - Runs:
    - `speech_to_text.transcribe(wav_path)`
    - `voice_analyzer.analyze_voice(wav_path)`
    - `answer_evaluator.evaluate_answer(question, transcript, resume_text)`
    - `facial_analyzer.analyze_facial_frames(facial_frames)` if provided
  - Stores per-answer results:
    - updates in-memory `session["answers"]` and analysis lists
    - persists with `db.store_answer(...)`
  - Returns:
    - `session_id`
    - transcript + voice/facial/evaluation
    - time taken + `time_confidence_score`
    - `next_index` (how many answers are now recorded)

- `POST /end_interview`
  - Fetches in-memory or DB-based session payload
  - Calls `feedback_generator.generate_feedback(...)`
  - Persists final feedback with `db.save_feedback(session_id, feedback)`
  - Returns `{ status: "ok", message: "Feedback generated" }`

- `GET /feedback`
  - Returns final feedback from DB (`db.get_feedback`) or from in-memory `session["feedback"]`

- `POST /analyze_facial`
  - Standalone facial analysis endpoint
  - Accepts multipart files: `image` and/or multiple `facial_frames`
  - Returns the facial metrics payload produced by `facial_analyzer.analyze_facial_frames`

- `GET /questions`
  - Returns generated questions from in-memory or DB based on `session_id`

- `POST /realtime_analysis`
  - Live endpoint called during recording (audio chunk + optional webcam frame)
  - Computes live confidence via weighted fusion:
    - voice confidence from nervousness
    - facial confidence from facial confidence score
    - answer relevance from the latest stored answer (DB helper `db.get_last_answer_relevance`)
  - If no modalities are available yet, it returns a deterministic baseline live score (using a hash seed)

- `GET /sessions`
  - Returns a list of recent sessions (summary fields) using `db.list_recent_sessions`

- `GET /history`
  - Same as `/sessions` (history list view)

- `GET /history/<session_id>`
  - Returns full session detail:
    - questions
    - per-answer transcripts and scores
    - final feedback
  - Uses `db.get_history_session_detail(...)`

- Auth endpoints (SQLite-backed):
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/logout`
  - `GET /auth/last-email`

### Output/DB behavior notes
- Backend stores files under `backend/data/`:
  - `resumes/`, `audio/`, `transcripts/`
- The DB is SQLite and is initialized at startup with `db.init_db()`.

---

## `speech_to_text.py`

### Role
Encapsulates OpenAI-Whisper transcription (speech-to-text) with CPU-friendly defaults and caching of the loaded Whisper model.

### Key functions
- `_ensure_ffmpeg_on_path()`
  - Whisper relies on the `ffmpeg` binary under the hood.
  - Checks `shutil.which("ffmpeg")`; if missing on Windows, adds a Winget install directory to PATH (using `LOCALAPPDATA`).

- `get_model()`
  - Lazily loads and caches the Whisper model in memory.
  - Model name selection:
    - `WHISPER_MODEL` env var if set
    - otherwise defaults to `"tiny.en"` (lower latency on CPU)
  - Uses `whisper.load_model(name, device="cpu")`

- `transcribe(audio_path) -> str`
  - Ensures ffmpeg is on PATH
  - Loads model with `get_model()`
  - Calls `model.transcribe(...)` with low-latency settings:
    - `fp16=False`
    - `language="en"`
    - `temperature=0.0`
    - `beam_size=1`, `best_of=1`
    - `condition_on_previous_text=False`
  - Returns:
    - recognized text, or
    - placeholders like `"[No speech detected]"` or `"[Transcription failed: ...]"`

---

## `voice_analyzer.py`

### Role
Extracts voice delivery metrics from the WAV audio using Librosa + NumPy heuristics. The output is a deterministic dict that includes:
- pitch (mean/variance)
- pauses/silence ratio
- energy
- speaking-rate proxy
- a nervousness heuristic score in range ~0-100

### Key functions
- `_fallback()`
  - Deterministic fallback payload used if:
    - librosa or numpy is not installed
    - audio cannot be loaded

- `analyze_voice(audio_path) -> dict`
  - Loads audio: `librosa.load(audio_path, sr=None)`
  - Computes pitch using `librosa.piptrack`
  - Computes pauses:
    - uses `librosa.effects.split(y, top_db=25)` to estimate speech segments
    - derives silence duration and silence ratio
  - Computes energy:
    - `librosa.feature.rms`
  - Computes speaking rate proxy:
    - `librosa.onset.onset_strength` + `librosa.beat.beat_track`
  - Nervousness heuristic:
    - uses `silence_ratio` and a jitter proxy from pitch variance
    - maps to a bounded score in [0, 100]

---

## `facial_analyzer.py`

### Role
Computes facial “emotion-like” metrics from webcam frames using:
- OpenCV (frame decoding and color conversion)
- MediaPipe Face Mesh (468 landmarks)

This module is intentionally rule-based (no training), designed to be explainable and deterministic for academic demonstration.

### Key functions and workflow
- `_get_mediapipe_face_mesh()`
  - Creates a cached `mp.solutions.face_mesh.FaceMesh(...)` instance once per process.
  - Returns `None` (and sets an error string) if MediaPipe/OpenCV compatibility is missing.

- `_analyze_single_frame(frame_rgb, face_mesh) -> dict | None`
  - Processes one frame and returns:
    - `confidence_score` (smile-based + inverse stress)
    - `nervousness_score` (mouth openness + symmetry/asymmetry)
    - `stress_score` (eye aspect ratio + symmetry)
    - `dominant_emotion` = `confident | nervous | stressed | neutral`
  - Landmark usage is hard-coded using MediaPipe landmark indices (mouth corners/lips, eyes, cheeks, nose tip).

- `analyze_facial_frames(frames: list) -> dict`
  - Decodes each frame (supports both raw bytes and image matrices).
  - Runs `_analyze_single_frame` for each decoded frame.
  - Aggregates results across frames:
    - uses median confidence/nervousness/stress for stability
    - picks dominant emotion from “signal frames” (non-neutral with enough score)
  - Provides a fallback payload (defaults around 50/50/50 + neutral) if:
    - MediaPipe cannot initialize
    - no face landmarks are detected

---

## `answer_evaluator.py`

### Role
Evaluates a user’s spoken answer for:
- relevance/intent alignment (question keywords + resume keyword anchors)
- clarity estimate (structure + presence of filler words)
- length category (short/normal/detailed)

It primarily uses deterministic rules. Optionally, if scikit-learn is available, it also computes a light TF-IDF cosine similarity signal.

### Key functions
- `tokenize_for_similarity(text) -> str`
  - Normalizes text by lowercasing, removing punctuation, collapsing whitespace.

- `_extract_resume_keywords(resume_text, max_keywords=12)`
  - Builds a deterministic list of keywords from the resume (token frequency excluding stopwords).

- `_extract_question_keywords(question_text, max_keywords=10)`
  - Extracts intent-bearing keywords from the question (token frequency excluding stopwords).

- `_detect_keywords(text_clean, keywords)`
  - Uses word-boundary regex matches to detect which keywords appear in the transcript.

- `_structure_quality_score(transcript) -> int (0-100)`
  - Heuristic scoring:
    - sentence count (flow)
    - action verbs (“implemented/built/led…”) and result words
    - context markers (situation/task/problem/team/project)
    - metric-like tokens (numbers, percent, latency, uptime, accuracy…)

- `evaluate_answer(question, transcript, resume_text) -> dict`
  - Computes:
    - `question_keyword_coverage` (how many question keywords were detected)
    - `structure_score`
    - optional `tfidf_signal` if TF-IDF is available
  - Produces `relevance_score` (0-100) as a weighted combination:
    - 45%: keyword coverage
    - 40%: structure quality
    - 15%: tf-idf-ish similarity signal (if available)
  - Adds “clarity” and length feedback:
    - short answers get lower clarity and extra feedback text
    - filler word count can downgrade clarity
  - Also returns:
    - `detected_keywords`, `missing_keywords` (resume anchors)

---

## `question_generator.py`

### Role
Generates interview questions based on:
- resume content
- selected interview type (`HR`, `Technical`, `Role-Based`, `Company-Based`, `JD-Based`)
- optional job description text

The module uses a hybrid strategy:
- If OpenAI is configured (`llm_helper.llm_generate_questions` returns data), it uses LLM-generated questions in JSON format.
- If not configured or LLM fails, it falls back to deterministic pools with resume-aware heuristics.

### Key functions
- `extract_skills_and_topics(resume_text) -> list`
  - Extracts a small set of topic strings via regex patterns (skills/experience/education/projects).

- `_resume_driven_technical_questions(resume_text, role_clean) -> list`
  - Builds explicit technical questions (OOP/DSA/DBMS/OS/Networking/etc.) based on resume keywords.

- `_jd_keywords(jd_text, max_terms=8) -> list[str]`
  - Lightweight token extraction from the job description to drive JD-Based question wording.

- `_sanitize_question_text(text, category)`
  - Removes forced “story/life-history” phrasing patterns (especially for HR-like prompts) and softens them.

- `generate_questions(resume_text, role, company, jd_text, interview_type, session_seed) -> list`
  - Normalizes interview type and creates question pools.
  - Tries LLM generation first; if missing, uses deterministic generation per type:
    - HR: behavioral + professional fit questions
    - Technical: concept/depth + one HR intro at the end
    - Role-Based: role-anchored responsibilities framing
    - Company-Based: values/stakeholder emphasis and “why company”
    - JD-Based: maps to job-description themes

---

## `llm_helper.py`

### Role
OpenAI-compatible client used by `question_generator.py` and `feedback_generator.py`.

### Key functions
- `_load_dotenv_local()`
  - Reads a local `.env` file next to `llm_helper.py` (if it exists).

- `_env(name, default)`
  - Returns environment variables or `.env` values.

- `_post_chat(messages, temperature, max_tokens)`
  - Calls `{OPENAI_BASE_URL}/chat/completions` with bearer token from `OPENAI_API_KEY`.
  - Returns the assistant’s `content` string, or `None` on errors/missing configuration.

- `llm_generate_questions(...)`
  - Requests the model to return JSON only: an array of `{category, text}` objects.
  - Parses and sanitizes the returned JSON; limits output to `total_questions`.

- `llm_generate_expected_answer(question, resume_text, transcript="")`
  - Requests one concise expected sample answer (simple first-person style).
  - Used as optional content for coaching output.

---

## `feedback_generator.py`

### Role
Generates deterministic final interview feedback from collected metrics:
- voice metrics (nervousness, pauses, pitch proxies)
- facial metrics (confidence + nervousness/stress proxies)
- NLP evaluation metrics (relevance, clarity, length)
- resume keyword alignment signals
- multi-modal fusion => final “Interview Confidence Score”

The module is deterministic: the same inputs produce the same outputs.

### Key configuration constants
- `W_VOICE = 0.35`
- `W_FACIAL = 0.25`
- `W_ANSWER = 0.40`

These match the frontend fusion concept and the scoring formula in README.

### Key functions
- `generate_answer_coaching(question, transcript, evaluation, resume_text) -> dict`
  - Produces per-question coaching:
    - `feedback_text`
    - `star_sample_answer`
    - `star_structured` (S/T/A/R fields)
  - If `llm_generate_expected_answer` returns content, it prefers that; otherwise uses deterministic templates based on question type and clarity/relevance.

- `_compute_fusion_score(voice_nervous, facial_conf, relevance) -> float`
  - Converts voice nervousness to voice confidence:
    - `voice_conf = 100 - nervous`
  - Weighted sum:
    - `W_VOICE * voice_conf + W_FACIAL * facial_conf + W_ANSWER * relevance`

- `generate_feedback(answers_data, voice_analyses, facial_analyses=None, resume_text="") -> dict`
  - Main function used by `app.py` at interview end.
  - Computes:
    - overall `interview_confidence_score`
    - `fusion_breakdown` (contribution pieces for viva explanation)
    - strengths, weaknesses, suggestions
    - `performance_matrix` (content/voice/facial/pacing + clarity_rate + trend)
    - `per_question_breakdown` with:
      - `answer_score` (from relevance_score)
      - `voice_score`, `facial_score`, and `time_score`
    - `per_answer_coaching` + `improved_sample_answers`
      - both are based on the output of `generate_answer_coaching`

### Returned JSON shape (main keys)
- `strengths`, `weaknesses`, `suggestions`
- `interview_confidence_score`
- `fusion_breakdown`
- `performance_matrix`
- `voice_analysis` (overall + metrics + per_answer)
- `facial_analysis` (overall + metrics + per_answer)
- `answer_analysis` (overall + metrics + per_answer)
- `per_question_breakdown`
- `per_answer_coaching`, `improved_sample_answers`

---

## `db.py`

### Role
SQLite persistence layer for:
- user accounts
- interview sessions
- questions and answers
- voice/facial analysis blobs (JSON)
- final feedback blob (JSON)

### Key constants
- `DB_PATH = backend/data/interview.db`

### Key functions
- `init_db()`
  - Creates tables (if not existing) for:
    - `users`, `interview_sessions`, `questions`, `answers`, `voice_analyses`, `facial_analyses`, `final_feedback`
  - Also performs lightweight schema migrations with `ALTER TABLE` (adds new columns if missing).

- `create_session(session_id, resume_text, questions, role, company, job_description, interview_type)`
  - Inserts one row into `interview_sessions`
  - Inserts question rows into `questions`

- `store_answer(session_id, question_index, question_text, transcript, evaluation, voice_data, facial_data, time_taken, time_confidence_score, coaching=None) -> int`
  - Inserts into:
    - `answers`
    - `voice_analyses`
    - `facial_analyses`
  - Updates `interview_sessions.updated_at`
  - Returns `answer_id` (primary key for the inserted answer row)

- `session_payload(session_id) -> dict`
  - Fetches the minimal payload used by the feedback generation step:
    - resume_text, questions, and ordered arrays of:
      - answer objects with evaluation + transcript + time scores
      - voice analyses JSON list
      - facial analyses JSON list

- `save_feedback(session_id, feedback)`
  - Stores the final feedback JSON in `final_feedback`
  - Upserts using `ON CONFLICT(session_id) DO UPDATE`

- `get_feedback(session_id) -> dict | None`
  - Reads from `final_feedback`

- `get_last_answer_relevance(session_id) -> float | None`
  - Used for live confidence fusion (`/realtime_analysis`).
  - Reads the most recently inserted `answers.evaluation_json` and returns its `relevance_score` if available.

- History helpers for UI:
  - `list_recent_sessions(limit)`
  - `get_history_session_detail(session_id)`

### Auth-related functions
- `get_user_by_email(email)`
- `create_user(name, email, password_hash)`
- `update_user_last_login(email)`
- `get_last_login_email()`

---

## `resume_parser.py`

### Role
Extracts plain text from uploaded PDF resumes.

### Key function
- `extract_text_from_pdf(file_path) -> str`
  - Uses `PyPDF2.PdfReader`
  - Iterates pages and calls `page.extract_text()`
  - Joins extracted text using blank lines
  - Returns empty string if no extractable text is found

---

## `frontend/src/App.jsx`

### Role
Main React component that controls the whole UI workflow and collects results for the final feedback screen.

### Key responsibilities
- Steps/state machine: `upload` -> `interview` -> `history` / `historyDetail` -> `results` / `feedback`.
- Calls backend APIs through `frontend/src/api.js`:
  - `uploadResume(...)` to get `session_id` and generated questions
  - `submitAnswer(...)` when recording is complete (audio blob + facial frames)
  - `realtimeAnalysis(...)` while recording to update the live confidence score
  - `endInterview()` + `getFeedback()` after the last question
  - `listSessions(...)` and `getHistorySession(...)` for past interviews
- Speaks questions out loud using the browser `speechSynthesis`.
- Maintains:
  - `questions` and `currentIndex`
  - `perAnswerResults` (transcript + evaluation + voice/facial + pacing/time confidence)
  - `liveScore` and `liveIndicator` during recording

## `frontend/src/Recorder.jsx`

### Role
Captures the user’s answer with:
- Microphone audio (for final submission + live chunks)
- Webcam frames (JPEG) every ~2 seconds

### Key flow
- `getUserMedia({ audio: true, video: true })` starts one media stream.
- Uses `MediaRecorder` to record **audio-only** (video tracks are only for preview/frame capture).
- Every `FRAME_INTERVAL_MS` (~2000ms) it:
  - draws the current video frame to a hidden canvas
  - converts canvas -> JPEG `Blob`
  - pushes the blob into `facialFramesRef.current`
- Every `REALTIME_INTERVAL_MS` (~3000ms) it:
  - takes the latest audio chunk (`lastAudioChunkRef.current`)
  - captures a fresh frame
  - calls `onRealtimeUpdate(audioChunk, frameBlob)`
- When recording stops/timeout:
  - builds the final audio `Blob` from collected chunks
  - calls `onComplete(audioBlob, facialFramesRef.current, { timeTaken })`

## `frontend/src/api.js`

### Role
Axios-based client for the Flask REST API.

### Key responsibilities
- Maintains a stored `session_id` in `localStorage` (`interview_session_id`).
- Wraps backend routes:
  - `registerUser`, `loginUser`, `logoutUser`, `getLastLoginEmail`
  - `uploadResume(...)` -> `/upload_resume` (stores returned `session_id`)
  - `submitAnswer(...)` -> `/submit_answer` (multipart FormData: `audio`, `question`, `session_id`, `question_index`, `time_taken`, `facial_frames`)
  - `endInterview()` -> `/end_interview`
  - `getFeedback()` -> `/feedback`
  - `getQuestions()` -> `/questions`
  - `listSessions()` -> `/history`
  - `getHistorySession(sessionId)` -> `/history/<session_id>`
  - `realtimeAnalysis(...)` -> `/realtime_analysis` (optional `audio_chunk` + `frame`, plus `session_id`)

## `frontend/src/AuthRoutes.jsx`

### Role
Authentication UI + route protection using React Router.

### Key responsibilities
- Provides:
  - `/login` (login)
  - `/sign-in` (register)
  - `/` protected interview workspace
- `ProtectedRoute` checks if user is “logged in” via a `localStorage` marker.
- `InterviewWorkspace` handles theme toggle (stored in `localStorage`) and logout.
- Renders the main workspace content via the `App` component.

---

## Optional next step (for you)
If you want, tell me whether you want these explanations to be:
- shorter (1 paragraph per file), or
- more “viva style” (add flow diagrams + what to say for each module).

