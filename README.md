# AI Interviewer

Full-stack mock interview app with resume-aware question generation, webcam + microphone capture, live confidence updates, and final coaching feedback.

## What This Project Does

- Uploads a resume PDF and generates interview questions.
- Supports interview modes: `HR`, `Technical`, `Role-Based`, `Company-Based`, and `JD-Based`.
- Records spoken answers from browser mic and captures webcam frames during each answer.
- Runs multi-modal scoring:
  - Speech-to-text with Whisper
  - Voice analysis with Librosa
  - Facial confidence analysis with MediaPipe + OpenCV
  - Answer relevance with TF-IDF style NLP scoring
- Produces final interview feedback with strengths, weaknesses, suggestions, and question-wise expected answers.
- Stores all sessions in SQLite and exposes history in the UI.

## Tech Stack

- Frontend: React (Vite), Tailwind CSS, Axios, Recharts
- Backend: Flask + Flask-CORS
- AI/ML: Whisper, Librosa, MediaPipe, scikit-learn
- Database: SQLite (`backend/data/interview.db`)
- Media tooling: system `ffmpeg` (CLI)

## Repository Structure

```text
AI-interviewer/
  backend/
    app.py                  # Flask API server
    question_generator.py   # Resume/interview-type question generation
    speech_to_text.py       # Whisper loading + transcription
    voice_analyzer.py       # Voice metrics
    facial_analyzer.py      # Frame-based facial analysis
    feedback_generator.py   # Final fusion + coaching response
    db.py                   # SQLite persistence
    requirements.txt
  frontend/
    src/App.jsx             # Main UI flow (setup, interview, results, history)
    src/Recorder.jsx        # Media capture and live analysis loop
    src/api.js              # API calls
    package.json
```

## How Scoring Works

Final confidence score is a weighted fusion:

```text
Interview Confidence =
0.35 * Voice Confidence +
0.25 * Facial Confidence +
0.40 * Answer Relevance
```

Live confidence updates during recording use the same weights but only include modalities available in that update tick.

## Local Setup

Prerequisites:

- Python 3.10+
- Node.js 18+
- `ffmpeg` installed and available in PATH

### 1) Start backend

```bash
cd AI-interviewer/backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Backend runs at `http://127.0.0.1:5000`.

### 2) Start frontend

```bash
cd AI-interviewer/frontend
npm install
npm run dev
```

Frontend runs at `http://127.0.0.1:5173`.

Vite should proxy `/api` requests to the Flask backend.

## Usage Flow

1. Open the app and choose interview type.
2. Upload a resume PDF and optionally provide role/company/job description.
3. Start interview and answer each question by recording audio + webcam.
4. Get live confidence updates while recording.
5. After final question, review:
   - overall score
   - per-question breakdown
   - strengths/weaknesses/suggestions
   - expected answer coaching
6. Open `Past interviews` to review previous sessions.

## Backend API Overview

- `POST /upload_resume` - Upload resume and generate questions
- `POST /submit_answer` - Submit one answer (audio + optional facial frames)
- `POST /realtime_analysis` - Live confidence tick (audio chunk + frame)
- `POST /end_interview` - Generate final feedback
- `GET /feedback` - Fetch final feedback
- `GET /questions` - Fetch generated questions
- `GET /history` and `GET /history/<session_id>` - Session history
- Auth helpers:
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/logout`
  - `GET /auth/last-email`

## Environment Notes

- Question generation can use an OpenAI-compatible endpoint if configured in `backend/.env`:
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL` (default in code: `gpt-4o-mini`)
  - `OPENAI_BASE_URL`
- If these are not set, the project falls back to rule-based question generation.
- Whisper model can be overridden with `WHISPER_MODEL`; code defaults to `tiny.en` for lower CPU latency.

## Troubleshooting

- If transcription fails, verify `ffmpeg` is installed and accessible from terminal.
- First backend run may be slower while Whisper model files load.
- Webcam/microphone permission must be granted in browser.
- If frontend cannot reach backend, verify Vite proxy and Flask server are both running.
