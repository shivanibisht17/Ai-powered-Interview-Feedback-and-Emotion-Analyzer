"""Answer evaluation using TF-IDF similarity and rule-based scoring.

Adds deterministic explanation fields:
- detected_keywords
- missing_keywords
- answer_length_category
"""

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except Exception:
    TfidfVectorizer = None
import re


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "with", "you", "your", "i", "we", "they", "them", "our", "ours",
    "my", "mine", "me", "he", "she", "his", "her", "their", "there", "here",
    "not", "but", "if", "then", "so", "do", "does", "did", "done", "can", "could",
    "would", "should", "will", "just", "about", "into", "over", "under", "more",
    "less", "very", "also", "than", "too",
}


def tokenize_for_similarity(text: str) -> str:
    """Normalize text for TF-IDF."""
    if not text or not isinstance(text, str):
        return ""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _extract_resume_keywords(resume_text: str, max_keywords: int = 12) -> list:
    """Extract simple, deterministic keywords from resume text (no external deps)."""
    clean = tokenize_for_similarity(resume_text)
    if not clean:
        return []
    tokens = [w for w in clean.split() if len(w) >= 3 and not w.isdigit() and w not in _STOPWORDS]
    if not tokens:
        return []
    freq = {}
    for w in tokens:
        freq[w] = freq.get(w, 0) + 1
    # sort by (freq desc, token asc) for determinism
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:max_keywords]]


def _detect_keywords(text_clean: str, keywords: list) -> list:
    """Detect which resume keywords appear in the answer (word-boundary match)."""
    detected = []
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text_clean):
            detected.append(kw)
    return detected


def _extract_question_keywords(question_text: str, max_keywords: int = 10) -> list:
    """Extract intent-bearing keywords from the interview question."""
    clean = tokenize_for_similarity(question_text)
    if not clean:
        return []
    tokens = [w for w in clean.split() if len(w) >= 4 and w not in _STOPWORDS]
    if not tokens:
        return []
    freq = {}
    for w in tokens:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:max_keywords]]


def _structure_quality_score(transcript: str) -> int:
    """
    Score answer structure quality (0-100) independent of exact wording.
    Rewards clear flow, action/result language, and concrete evidence signals.
    """
    t = transcript or ""
    text = tokenize_for_similarity(t)
    words = text.split()
    if not words:
        return 0

    sentence_count = max(1, len([s for s in re.split(r"[.!?]+", t) if s.strip()]))
    has_flow = sentence_count >= 2

    action_terms = len(re.findall(r"\b(i|we)\s+(built|implemented|created|designed|led|improved|optimized|fixed)\b", text))
    result_terms = len(re.findall(r"\b(result|impact|improved|reduced|increased|delivered|achieved|outcome)\b", text))
    context_terms = len(re.findall(r"\b(situation|task|problem|challenge|goal|deadline|team|project)\b", text))
    metric_terms = len(re.findall(r"\b\d+(\.\d+)?\b|%|hours?|days?|weeks?|users?|latency|uptime|accuracy\b", t.lower()))

    score = 25
    if has_flow:
        score += 15
    if len(words) >= 20:
        score += 15
    if len(words) >= 45:
        score += 10
    score += min(15, action_terms * 5)
    score += min(10, result_terms * 4)
    score += min(10, context_terms * 3)
    score += min(15, metric_terms * 3)
    return int(max(0, min(100, score)))


def evaluate_answer(question: str, transcript: str, resume_text: str) -> dict:
    """Score relevance from intent + structure (not exact wording match)."""
    q_clean = tokenize_for_similarity(question)
    t_clean = tokenize_for_similarity(transcript)
    r_clean = tokenize_for_similarity(resume_text)

    short_answer = len(t_clean.split()) < 10
    very_short = len(t_clean.split()) < 3
    word_count = len(t_clean.split())

    resume_keywords = _extract_resume_keywords(resume_text, max_keywords=12)
    detected_keywords = _detect_keywords(t_clean, resume_keywords) if resume_keywords else []
    missing_keywords = [k for k in resume_keywords if k not in set(detected_keywords)]

    if very_short or not t_clean:
        return {
            "relevance_score": 0,
            "clarity": "poor",
            "length_feedback": "Answer was too short or missing.",
            "is_short": True,
            "is_unclear": True,
            "word_count": word_count,
            "answer_length_category": "short",
            "detected_keywords": detected_keywords,
            "missing_keywords": missing_keywords[:8],
            "detail": "No substantial answer detected.",
        }

    q_keywords = _extract_question_keywords(question, max_keywords=10)
    q_detected = _detect_keywords(t_clean, q_keywords) if q_keywords else []
    q_keyword_coverage = (len(q_detected) / len(q_keywords)) if q_keywords else 0.0

    structure_score = _structure_quality_score(transcript)

    # Optional semantic-ish signal; lower weight than structure/intent.
    tfidf_signal = 0
    if TfidfVectorizer is not None:
        corpus = [q_clean, r_clean, t_clean]
        vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
        try:
            tfidf = vectorizer.fit_transform(corpus)
        except Exception:
            tfidf = vectorizer.fit_transform([t or " " for t in corpus])

        from sklearn.metrics.pairwise import cosine_similarity
        t_vec = tfidf[2:3]
        q_sim = cosine_similarity(t_vec, tfidf[0:1])[0][0]
        r_sim = cosine_similarity(t_vec, tfidf[1:2])[0][0]
        tfidf_signal = int(min(100, max(0, (0.65 * q_sim + 0.35 * r_sim) * 100)))

    # Main score emphasizes relevance to the question + structure quality.
    relevance_score = int(
        round(
            (q_keyword_coverage * 100) * 0.45
            + structure_score * 0.40
            + tfidf_signal * 0.15
        )
    )
    relevance_score = max(0, min(100, relevance_score))

    # Reasonable floor for substantive answers to avoid over-penalizing wording variations.
    if word_count >= 20:
        relevance_score = max(relevance_score, 45)
    elif word_count >= 10:
        relevance_score = max(relevance_score, 30)

    if word_count < 15:
        length_feedback = "Answer was quite brief; adding 1–2 concrete examples would strengthen it."
        clarity = "fair"
        answer_length_category = "short"
    elif word_count < 40:
        length_feedback = "Length is okay; consider one more specific example where relevant."
        clarity = "good"
        answer_length_category = "normal"
    else:
        length_feedback = "Good length; answer had enough detail."
        clarity = "good"
        answer_length_category = "detailed"

    filler = len(re.findall(r"\b(um|uh|like|you know|basically)\b", t_clean, re.I))
    if filler > 3:
        clarity = "fair" if clarity == "good" else "poor"

    is_unclear = clarity == "poor" or very_short

    return {
        "relevance_score": relevance_score,
        "structure_score": structure_score,
        "question_keyword_coverage": round(q_keyword_coverage * 100, 1),
        "clarity": clarity,
        "length_feedback": length_feedback,
        "is_short": short_answer,
        "is_unclear": is_unclear,
        "word_count": word_count,
        "answer_length_category": answer_length_category,
        "detected_keywords": detected_keywords,
        "missing_keywords": missing_keywords[:8],
        "detail": (
            f"Relevance: {relevance_score}/100. "
            f"Length: {answer_length_category} ({word_count} words). "
            f"Clarity: {clarity}."
        ),
    }
