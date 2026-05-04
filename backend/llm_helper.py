"""Lightweight OpenAI-compatible helper for dynamic interview generation."""

import json
import os
import urllib.request
from typing import Optional

_DOTENV_CACHE = None


def _load_dotenv_local() -> dict:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE
    data = {}
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    _DOTENV_CACHE = data
    return data


def _env(name: str, default: str = "") -> str:
    val = (os.environ.get(name) or "").strip()
    if val:
        return val
    return (_load_dotenv_local().get(name) or default).strip()


def _post_chat(messages: list, temperature: float = 0.7, max_tokens: int = 900) -> Optional[str]:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        return None

    model = _env("OPENAI_MODEL", "gpt-4o-mini")
    base_url = _env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(raw)
        choices = obj.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except Exception:
        return None
    return None


def llm_generate_questions(
    resume_text: str,
    role: str,
    company: str,
    interview_type: str,
    total_questions: int = 7,
    session_seed: str = "",
) -> Optional[list]:
    """
    Ask LLM for dynamic, resume-grounded question set.
    Returns list[{"category": str, "text": str}] or None.
    """
    sys_msg = (
        "You generate interview questions in JSON only. "
        "Return exactly a JSON array of objects with keys: category, text. "
        "No markdown, no explanation."
    )
    user_msg = (
        f"Generate {total_questions} interview questions for this candidate.\n"
        f"Interview type: {interview_type or 'Technical'}\n"
        f"Role: {role or 'Software Engineer'}\n"
        f"Company: {company or 'Target company'}\n"
        f"Session seed for variety: {session_seed or 'none'}\n\n"
        "Requirements:\n"
        "- Mostly technical if interview type is Technical.\n"
        "- If interview type is HR, avoid asking for personal life stories or 'tell me about a time' style prompts.\n"
        "- For HR, prefer direct professional questions about approach, communication, and role fit.\n"
        "- Strongly align to resume topics and projects.\n"
        "- Include concept depth (e.g., OOP/DSA/DBMS/OS/CN) if present in resume.\n"
        "- Keep each question specific and non-repetitive.\n\n"
        f"Resume:\n{(resume_text or '')[:7000]}"
    )
    content = _post_chat(
        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
        temperature=0.85,
        max_tokens=1200,
    )
    if not content:
        return None

    try:
        arr = json.loads(content)
        if not isinstance(arr, list):
            return None
        cleaned = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            cat = (item.get("category") or "technical").strip().lower()
            if text:
                cleaned.append({"category": cat, "text": text})
        return cleaned[:total_questions] if cleaned else None
    except Exception:
        return None


def llm_generate_expected_answer(question: str, resume_text: str, transcript: str = "") -> Optional[str]:
    """Generate question-specific expected answer in simple first-person style."""
    sys_msg = (
        "You are an interview coach. Provide a concise expected answer sample. "
        "Use simple first-person language and keep it question-specific."
    )
    user_msg = (
        f"Question: {question}\n\n"
        "Write one expected answer sample that directly answers this exact question.\n"
        "Constraints:\n"
        "- 4 to 7 sentences\n"
        "- First-person style (I, my)\n"
        "- If concept/theory question, give clear definition + short example\n"
        "- If personal question, start naturally (e.g., My name is..., My strengths are...)\n"
        "- Avoid generic template wording\n\n"
        f"Candidate resume context:\n{(resume_text or '')[:3500]}\n\n"
        f"Candidate transcript (optional context):\n{(transcript or '')[:1200]}"
    )
    return _post_chat(
        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
        temperature=0.7,
        max_tokens=420,
    )
