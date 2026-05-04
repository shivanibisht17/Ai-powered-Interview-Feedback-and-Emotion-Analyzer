"""
SQLite persistence for interview sessions and analytics.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone


BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "data")
DB_PATH = os.path.join(DB_DIR, "interview.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after first deploy (SQLite has limited ALTER)."""
    def cols(table: str) -> set:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1] for r in rows}

    try:
        cu = cols("users")
        if "password_hash" not in cu:
            conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
        if "last_login_at" not in cu:
            conn.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
    except Exception:
        pass
    try:
        c = cols("interview_sessions")
        if "role" not in c:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN role TEXT DEFAULT ''")
        if "company" not in c:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN company TEXT DEFAULT ''")
        if "job_description" not in c:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN job_description TEXT DEFAULT ''")
        if "interview_type" not in c:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN interview_type TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        ca = cols("answers")
        if "coaching_json" not in ca:
            conn.execute("ALTER TABLE answers ADD COLUMN coaching_json TEXT")
    except Exception:
        pass


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                name TEXT,
                password_hash TEXT DEFAULT '',
                last_login_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interview_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER,
                resume_text TEXT,
                questions_json TEXT,
                role TEXT DEFAULT '',
                company TEXT DEFAULT '',
                job_description TEXT DEFAULT '',
                interview_type TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                question_type TEXT,
                question_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES interview_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_index INTEGER,
                question_text TEXT,
                transcript TEXT,
                evaluation_json TEXT,
                time_taken REAL DEFAULT 0,
                time_confidence_score REAL DEFAULT 0,
                coaching_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES interview_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS voice_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                answer_id INTEGER,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES interview_sessions(session_id),
                FOREIGN KEY(answer_id) REFERENCES answers(id)
            );

            CREATE TABLE IF NOT EXISTS facial_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                answer_id INTEGER,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES interview_sessions(session_id),
                FOREIGN KEY(answer_id) REFERENCES answers(id)
            );

            CREATE TABLE IF NOT EXISTS final_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                feedback_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES interview_sessions(session_id)
            );
            """
        )
        _migrate_schema(conn)
        conn.commit()
    finally:
        conn.close()


def create_session(
    session_id: str,
    resume_text: str,
    questions: list[str],
    role: str = "",
    company: str = "",
    job_description: str = "",
    interview_type: str = "",
) -> None:
    now = utc_now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO interview_sessions(
                session_id, resume_text, questions_json, role, company, job_description, interview_type, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                resume_text,
                json.dumps(questions),
                role or "",
                company or "",
                job_description or "",
                interview_type or "",
                now,
                now,
            ),
        )
        for idx, question in enumerate(questions):
            q_type = "technical"
            if isinstance(question, dict):
                q_text = question.get("text", "")
                q_type = question.get("category", "technical")
            else:
                q_text = question
            conn.execute(
                """
                INSERT INTO questions(session_id, question_index, question_type, question_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, idx, q_type, q_text, now),
            )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM interview_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["questions"] = json.loads(data.get("questions_json") or "[]")
        return data
    finally:
        conn.close()


def list_recent_sessions(limit: int = 30) -> list[dict]:
    """Return recent sessions for history UI (newest first)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT s.session_id, s.created_at, s.role, s.company,
                   COALESCE(s.interview_type, '') AS interview_type,
                   (SELECT COUNT(*) FROM questions q WHERE q.session_id = s.session_id) AS total_questions,
                   (SELECT COUNT(*) FROM answers a WHERE a.session_id = s.session_id) AS answer_count,
                   (SELECT feedback_json FROM final_feedback f WHERE f.session_id = s.session_id LIMIT 1) AS feedback_json
            FROM interview_sessions s
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        out = []
        for r in rows:
            fb = None
            if r["feedback_json"]:
                try:
                    fb = json.loads(r["feedback_json"])
                except Exception:
                    fb = None
            score = None
            if fb and isinstance(fb, dict):
                score = fb.get("interview_confidence_score")
            out.append(
                {
                    "session_id": r["session_id"],
                    "created_at": r["created_at"],
                    "role": r["role"] or "",
                    "company": r["company"] or "",
                    "interview_type": r["interview_type"] or "",
                    "total_questions": int(r["total_questions"] or 0),
                    "answer_count": r["answer_count"] or 0,
                    "final_score": score,
                    "interview_confidence_score": score,
                }
            )
        return out
    finally:
        conn.close()


def get_history_session_detail(session_id: str) -> dict | None:
    """
    Full session for history detail: questions, per-answer metrics, final feedback.
    """
    conn = _connect()
    try:
        sess = conn.execute(
            """
            SELECT session_id, created_at, updated_at, role, company, job_description,
                   COALESCE(interview_type, '') AS interview_type,
                   resume_text, questions_json
            FROM interview_sessions WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if not sess:
            return None

        questions_rows = conn.execute(
            """
            SELECT question_index, question_type, question_text
            FROM questions WHERE session_id = ? ORDER BY question_index, id
            """,
            (session_id,),
        ).fetchall()
        questions_list = [{"index": r["question_index"], "type": r["question_type"], "text": r["question_text"]} for r in questions_rows]

        ans_rows = conn.execute(
            """
            SELECT a.id, a.question_index, a.question_text, a.transcript, a.evaluation_json,
                   a.time_taken, a.time_confidence_score, a.created_at,
                   v.analysis_json AS voice_json, f.analysis_json AS facial_json
            FROM answers a
            LEFT JOIN voice_analyses v ON v.answer_id = a.id
            LEFT JOIN facial_analyses f ON f.answer_id = a.id
            WHERE a.session_id = ?
            ORDER BY a.question_index, a.id
            """,
            (session_id,),
        ).fetchall()

        per_answers = []
        for r in ans_rows:
            ev = {}
            try:
                ev = json.loads(r["evaluation_json"] or "{}")
            except Exception:
                ev = {}
            voice = {}
            facial = {}
            try:
                voice = json.loads(r["voice_json"] or "{}")
            except Exception:
                voice = {}
            try:
                facial = json.loads(r["facial_json"] or "{}")
            except Exception:
                facial = {}
            nervous = float(voice.get("nervous_score", 50) or 50)
            voice_score = round(100.0 - min(100.0, max(0.0, nervous)), 1)
            fc = facial.get("confidence_score")
            facial_score = (
                round(min(100.0, max(0.0, float(fc))), 1) if isinstance(fc, (int, float)) else None
            )
            per_answers.append(
                {
                    "question_index": r["question_index"],
                    "question": r["question_text"],
                    "transcript": r["transcript"] or "",
                    "answer_relevance_score": ev.get("relevance_score"),
                    "voice_score": voice_score,
                    "facial_score": facial_score,
                    "time_taken": r["time_taken"] or 0,
                    "time_confidence_score": r["time_confidence_score"] or 0,
                    "voice_analysis": voice,
                    "facial_analysis": facial,
                    "evaluation": ev,
                    "answered_at": r["created_at"],
                }
            )

        fb_row = conn.execute(
            "SELECT feedback_json FROM final_feedback WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        feedback = None
        if fb_row and fb_row["feedback_json"]:
            try:
                feedback = json.loads(fb_row["feedback_json"])
            except Exception:
                feedback = None

        q_json = []
        try:
            q_json = json.loads(sess["questions_json"] or "[]")
        except Exception:
            q_json = []

        return {
            "session_id": sess["session_id"],
            "created_at": sess["created_at"],
            "updated_at": sess["updated_at"],
            "role": sess["role"] or "",
            "company": sess["company"] or "",
            "job_description": sess["job_description"] or "",
            "interview_type": sess["interview_type"] or "",
            "total_questions": len(questions_list) or len(q_json),
            "questions": questions_list,
            "answers": per_answers,
            "feedback": feedback,
        }
    finally:
        conn.close()


def store_answer(
    session_id: str,
    question_index: int,
    question_text: str,
    transcript: str,
    evaluation: dict,
    voice_data: dict,
    facial_data: dict,
    time_taken: float,
    time_confidence_score: float,
    coaching: dict | None = None,
) -> int:
    now = utc_now()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO answers(
                session_id, question_index, question_text, transcript, evaluation_json,
                time_taken, time_confidence_score, coaching_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                question_index,
                question_text,
                transcript,
                json.dumps(evaluation),
                float(time_taken or 0),
                float(time_confidence_score or 0),
                json.dumps(coaching) if coaching else None,
                now,
            ),
        )
        answer_id = cur.lastrowid
        conn.execute(
            "INSERT INTO voice_analyses(session_id, answer_id, analysis_json, created_at) VALUES (?, ?, ?, ?)",
            (session_id, answer_id, json.dumps(voice_data), now),
        )
        conn.execute(
            "INSERT INTO facial_analyses(session_id, answer_id, analysis_json, created_at) VALUES (?, ?, ?, ?)",
            (session_id, answer_id, json.dumps(facial_data), now),
        )
        conn.execute(
            "UPDATE interview_sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
        return int(answer_id)
    finally:
        conn.close()


def session_payload(session_id: str) -> dict:
    conn = _connect()
    try:
        base = conn.execute(
            "SELECT resume_text, questions_json FROM interview_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not base:
            return {
                "resume_text": "",
                "questions": [],
                "answers": [],
                "voice_analyses": [],
                "facial_analyses": [],
            }
        answers_rows = conn.execute(
            "SELECT * FROM answers WHERE session_id = ? ORDER BY question_index, id",
            (session_id,),
        ).fetchall()
        answers = []
        for row in answers_rows:
            coaching = None
            if "coaching_json" in row.keys() and row["coaching_json"]:
                try:
                    coaching = json.loads(row["coaching_json"])
                except Exception:
                    coaching = None
            answers.append(
                {
                    "id": row["id"],
                    "question": row["question_text"],
                    "transcript": row["transcript"],
                    "evaluation": json.loads(row["evaluation_json"] or "{}"),
                    "time_taken": row["time_taken"] or 0,
                    "time_confidence_score": row["time_confidence_score"] or 0,
                    "coaching": coaching,
                }
            )
        voice_rows = conn.execute(
            "SELECT analysis_json FROM voice_analyses WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        facial_rows = conn.execute(
            "SELECT analysis_json FROM facial_analyses WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return {
            "resume_text": base["resume_text"] or "",
            "questions": json.loads(base["questions_json"] or "[]"),
            "answers": answers,
            "voice_analyses": [json.loads(r["analysis_json"] or "{}") for r in voice_rows],
            "facial_analyses": [json.loads(r["analysis_json"] or "{}") for r in facial_rows],
        }
    finally:
        conn.close()


def save_feedback(session_id: str, feedback: dict) -> None:
    now = utc_now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO final_feedback(session_id, feedback_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                feedback_json = excluded.feedback_json,
                updated_at = excluded.updated_at
            """,
            (session_id, json.dumps(feedback), now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_feedback(session_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT feedback_json FROM final_feedback WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return json.loads(row["feedback_json"]) if row else None
    finally:
        conn.close()


def get_last_answer_relevance(session_id: str) -> float | None:
    """
    Most recent answer relevance (0-100) for live confidence blending.
    Returns None when no submitted answers yet (caller should omit answer weight).
    """
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT evaluation_json FROM answers
            WHERE session_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if not row or not row["evaluation_json"]:
            return None
        ev = json.loads(row["evaluation_json"] or "{}")
        r = ev.get("relevance_score")
        if isinstance(r, (int, float)):
            return float(min(100.0, max(0.0, r)))
        return None
    except Exception:
        return None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, email, name, password_hash, created_at, last_login_at FROM users WHERE email = ?",
            (normalized,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(name: str, email: str, password_hash: str) -> dict | None:
    normalized = (email or "").strip().lower()
    display_name = (name or "").strip()
    if not normalized or not password_hash:
        return None
    now = utc_now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO users(email, name, password_hash, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalized, display_name, password_hash, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()
    return get_user_by_email(normalized)


def update_user_last_login(email: str) -> None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE email = ?",
            (utc_now(), normalized),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_login_email() -> str:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT email FROM users
            WHERE email IS NOT NULL AND email <> ''
            ORDER BY COALESCE(last_login_at, created_at) DESC
            LIMIT 1
            """
        ).fetchone()
        return (row["email"] if row else "") or ""
    finally:
        conn.close()
