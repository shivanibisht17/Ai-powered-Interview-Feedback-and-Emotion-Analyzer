"""
Deterministic, data-based final feedback.

This module generates the final interview feedback using:
- Voice analysis metrics (nervousness, pitch, pauses)
- Facial emotion metrics (confidence, nervousness, stress)
- NLP evaluation metrics (relevance, clarity)
- Resume keyword alignment
- Multi-modal emotion fusion → Interview Confidence Score

Deterministic means:
Same interview input -> same feedback output (no randomness)
"""

# Libraries used
import hashlib   # used to generate stable hash-based seeds
import math      # used for numeric calculations (pitch std, etc.)
import random    # used for controlled sentence variation
import re
from llm_helper import llm_generate_expected_answer


# -------------------------------------------------------------------
# Helper function: generate a stable integer seed from strings
# Used so feedback remains consistent for same interview inputs
# -------------------------------------------------------------------
def _stable_int_seed(*parts: str) -> int:
    joined = "|".join([p for p in parts if p is not None])
    digest = hashlib.sha256(joined.encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


# -------------------------------------------------------------------
# Helper function: pick a sentence from pool deterministically
# Same input -> same selected sentence
# -------------------------------------------------------------------
def _pick(pool: list, seed_key: str) -> str:
    if not pool:
        return ""
    rng = random.Random(_stable_int_seed(seed_key))
    return rng.choice(pool)


# -------------------------------------------------------------------
# Helper function: compute mean of numeric values
# -------------------------------------------------------------------
def _mean(vals: list) -> float:
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


# -------------------------------------------------------------------
# Helper function: safely format numbers
# -------------------------------------------------------------------
def _fmt(x, digits=1):
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "0"


# -------------------------------------------------------------------
# Helper function: detect trend (increase/decrease/flat)
# Used for nervousness and pauses
# -------------------------------------------------------------------
def _trend_label(first: float, last: float, threshold: float) -> str:
    delta = last - first
    if delta > threshold:
        return "up"
    if delta < -threshold:
        return "down"
    return "flat"


# -------------------------------------------------------------------
# MULTI-MODAL EMOTION FUSION
# Combines voice, facial, and answer relevance into Interview Confidence Score
#
# Formula:
#   voice_confidence   = 100 - nervous_score  (higher nervous = lower confidence)
#   facial_confidence  = facial confidence_score (from face mesh)
#   answer_confidence  = relevance_score (0-100)
#
#   Interview_Confidence = w1*voice_confidence + w2*facial_confidence + w3*answer_confidence
#
# Weights (tuned for academic demo):
#   w1 = 0.35  (voice - tone and delivery)
#   w2 = 0.25  (facial - visual cues)
#   w3 = 0.40  (answer - content relevance)
# -------------------------------------------------------------------
W_VOICE = 0.35
W_FACIAL = 0.25
W_ANSWER = 0.40


def generate_answer_coaching(
    question: str,
    transcript: str,
    evaluation: dict,
    resume_text: str = "",
) -> dict:
    """
    Per-answer AI coaching: concise feedback plus an improved STAR-style sample answer.

    Deterministic (no external LLM): uses question text, transcript quality, and resume keywords
    to produce structured guidance suitable for mock-interview practice.
    """
    q = (question or "").strip()
    t = (transcript or "").strip()
    rel = int((evaluation or {}).get("relevance_score") or 0)
    clarity = (evaluation or {}).get("clarity") or "fair"
    wc = (evaluation or {}).get("word_count")
    if not isinstance(wc, int):
        wc = len(t.split()) if t else 0
    detected = (evaluation or {}).get("detected_keywords") or []
    missing = (evaluation or {}).get("missing_keywords") or []

    # Prefer LLM-generated expected answer when configured.
    llm_answer = llm_generate_expected_answer(q, resume_text or "", t)
    if llm_answer:
        return {
            "feedback_text": "Answer is generated automatically from your question and profile context.",
            "star_sample_answer": llm_answer.strip(),
            "star_structured": {
                "situation": "",
                "task": "",
                "action": "",
                "result": "",
            },
            "answer_format": "llm",
            "relevance_score": rel,
        }

    feedback_parts = []
    if rel >= 70:
        feedback_parts.append("Your answer stayed relevant to the question and showed good alignment with your background.")
    elif rel >= 40:
        feedback_parts.append("The answer is on-topic but could tie more explicitly to concrete outcomes and role-specific details.")
    else:
        feedback_parts.append("Try to anchor your response with specific examples and connect them directly to what the interviewer asked.")

    if clarity == "good":
        feedback_parts.append("Structure and clarity are solid; keep using signposting (first, then, finally).")
    elif clarity == "fair":
        feedback_parts.append("Add one clear example and quantify the impact (time saved, error rate, users affected).")
    else:
        feedback_parts.append("Reduce filler words and aim for a short setup, one example, and a crisp takeaway.")

    if wc < 15 and t:
        feedback_parts.append("The response is brief; expand with Situation → Task → Action → Result in 3–5 sentences.")

    if missing:
        feedback_parts.append(
            f"Consider weaving in resume-relevant terms you did not mention yet, such as: {', '.join(missing[:4])}."
        )

    def _is_behavioral_or_situational(question_text: str) -> bool:
        qt = (question_text or "").lower()
        markers = [
            "tell me about a time",
            "describe a time",
            "give an example",
            "how did you handle",
            "resolved conflict",
            "setback",
            "failure",
            "situation",
            "stakeholder",
            "misalignment",
            "ownership",
            "feedback",
            "prioritize",
            "deadline",
            "why should we hire",
            "leadership",
            "teamwork",
            "challenge",
        ]
        return any(m in qt for m in markers)

    is_behavioral = _is_behavioral_or_situational(q)
    q_lower = q.lower()

    # Personal identity/profile prompts should always be direct and simple.
    is_name_question = (
        "your name" in q_lower
        or "what is your name" in q_lower
        or "what's your name" in q_lower
        or q_lower.strip() == "name"
    )
    is_intro_question = "tell me about yourself" in q_lower or "introduce yourself" in q_lower
    is_strength_question = (
        "strength" in q_lower
        or "key strengths" in q_lower
        or "what are your strengths" in q_lower
        or "what is your strength" in q_lower
    )
    is_weakness_or_improvement_question = (
        "weakness" in q_lower
        or "improving" in q_lower
        or "working on" in q_lower
        or "skill are you actively improving" in q_lower
    )

    # Baseline components used for improved sample answer generation.
    sit = "In my recent role, I was responsible for delivering outcomes under tight constraints while collaborating with stakeholders."
    if detected:
        sit = f"In my background, I have worked with {', '.join(detected[:3])}, which maps well to this question."
    task = "The challenge was to deliver a clear result while managing risk and communicating progress."
    action = (
        "I broke the work into milestones, validated assumptions with data, and coordinated with teammates to execute. "
        "I documented decisions and adjusted the plan when new information appeared."
    )
    result = (
        "The outcome was a measurable improvement in quality or delivery, with stakeholders aligned on the final approach. "
        "I captured lessons learned for the next iteration."
    )

    def _question_focus(question_text: str) -> str:
        qt = (question_text or "").lower()
        if "yourself" in qt:
            return "your background, core strengths, and role-fit motivation"
        if "strength" in qt:
            return "specific strengths with one concrete proof point"
        if "conflict" in qt or "misalignment" in qt:
            return "how you resolved disagreement and aligned stakeholders"
        if "feedback" in qt:
            return "how you processed feedback and improved execution"
        if "failure" in qt or "setback" in qt:
            return "what failed, what you learned, and what changed"
        if "ownership" in qt:
            return "where you took initiative beyond assigned scope"
        if "debug" in qt or "issue" in qt:
            return "your debugging flow from detection to prevention"
        if "design" in qt or "architecture" in qt or "api" in qt or "system" in qt:
            return "your design decisions, trade-offs, and reliability plan"
        if "test" in qt or "quality" in qt:
            return "your testing strategy and release confidence checks"
        if "performance" in qt or "optimi" in qt or "latency" in qt:
            return "how you measured bottlenecks and improved performance"
        return "a direct answer tied to one relevant project example"

    def _extract_key_terms(question_text: str, max_terms: int = 5) -> list:
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-\+\.]{2,}", (question_text or "").lower())
        stop = {
            "what", "which", "when", "where", "your", "with", "from", "that", "this",
            "about", "explain", "describe", "would", "could", "should", "have", "into",
            "how", "does", "used", "using", "role", "project", "question", "answer",
            "tell", "give", "time", "example", "between", "difference",
        }
        out = []
        for w in words:
            if w in stop:
                continue
            if w not in out:
                out.append(w)
            if len(out) >= max_terms:
                break
        return out

    focus_area = _question_focus(q)

    if is_name_question or is_intro_question or is_strength_question or is_weakness_or_improvement_question:
        if is_name_question:
            sample = (
                "My name is [Your Name]. I am currently focused on software development practice and interview preparation. "
                "I am interested in this role because it aligns with my strengths in problem-solving, coding, and structured communication."
            )
            focus = [
                "say your name clearly in first sentence",
                "add your current education/role",
                "mention one relevant interest area",
                "keep it concise and confident",
            ]
        elif is_intro_question:
            sample = (
                "I am a software-focused candidate with hands-on experience building full-stack and AI-assisted projects. "
                "I enjoy solving practical product problems and improving reliability, performance, and user experience. "
                "In a recent project, I implemented end-to-end features and improved the quality of outputs through iterative testing. "
                "I am excited for this role because it matches my technical interests and my goal to contribute to real production systems."
            )
            focus = [
                "start with role and background",
                "mention 1-2 key skills",
                "include one concrete project/result",
                "close with role-fit motivation",
            ]
        elif is_strength_question:
            sample = (
                "My key strengths are ownership, consistency, and adaptability. "
                "For example, in one of my projects I took responsibility for a core feature, handled debugging and integration issues, "
                "and delivered a stable result on schedule while keeping communication clear with teammates."
            )
            focus = [
                "state 2-3 strengths directly",
                "support with one real example",
                "show ownership and consistency",
                "end with measurable/clear outcome",
            ]
        else:
            sample = (
                "One skill I am actively improving is communicating complex technical ideas more concisely. "
                "I identified this while explaining project trade-offs in reviews. "
                "To improve, I practice short structured explanations, ask for feedback after discussions, and track improvement "
                "through clearer updates and fewer follow-up clarifications."
            )
            focus = [
                "name one genuine improvement area",
                "show what action you are taking",
                "mention feedback/learning loop",
                "add current progress evidence",
            ]

        improved_answer = sample
        answer_format = "direct"
    elif is_behavioral:
        ql = q_lower
        if "conflict" in ql or "misalignment" in ql:
            sit = "Two teammates disagreed on implementation direction while we were close to a delivery deadline."
            task = "I needed to align the team quickly without compromising code quality or timeline."
            action = (
                "I facilitated a short technical review, compared options against project constraints, and proposed a hybrid plan. "
                "I assigned clear owners and added check-ins to reduce further ambiguity."
            )
            result = (
                "The team aligned within a day, we delivered on time, and post-release defects stayed low due to clearer ownership."
            )
        elif "feedback" in ql and "disagree" in ql:
            sit = "I received feedback on an approach I believed was technically stronger than the suggested alternative."
            task = "My goal was to respond professionally, validate assumptions, and still protect delivery quality."
            action = (
                "I acknowledged the feedback, prepared a quick comparison with risks/trade-offs, and discussed it with my lead. "
                "We agreed on a revised approach with measurable checkpoints."
            )
            result = (
                "The final solution balanced both viewpoints, and we improved maintainability without delaying release."
            )
        elif "failure" in ql or "setback" in ql:
            sit = "A feature I owned missed expected adoption after release due to poor onboarding flow."
            task = "I had to identify root causes and recover user trust quickly."
            action = (
                "I analyzed drop-off metrics, interviewed users, simplified the onboarding steps, and added in-product guidance. "
                "I also set weekly review metrics to track recovery."
            )
            result = (
                "Adoption improved over subsequent sprints, and I documented lessons so future launches included earlier usability checks."
            )
        elif "strength" in ql or "actively improving" in ql:
            sit = "I regularly handle cross-functional tasks where communication and ownership directly impact outcomes."
            task = "I wanted to use my strengths while intentionally improving one weaker area."
            action = (
                "I leveraged planning discipline and collaboration for execution, while practicing concise status updates to improve clarity. "
                "I requested feedback after each milestone and adjusted communication style."
            )
            result = (
                "Delivery became more predictable, stakeholder alignment improved, and my communication quality measurably improved."
            )
        elif "tell me about yourself" in ql:
            sit = "In recent projects, I have focused on building reliable features with strong ownership from design to delivery."
            task = "I aimed to grow into a role where I can contribute both technically and through team collaboration."
            action = (
                "I took end-to-end responsibility for features, improved testing/quality practices, and kept communication crisp with stakeholders."
            )
            result = (
                "This helped me deliver consistent outcomes and prepared me for a software role with broader impact."
            )
        elif "ownership" in ql:
            sit = "A critical module had unclear ownership, causing delays and repeated handoffs."
            task = "I stepped in to establish accountability and keep delivery on track."
            action = (
                "I defined scope, created a milestone plan, coordinated dependencies, and proactively shared status/risk updates."
            )
            result = (
                "The module shipped within timeline and became easier to maintain due to clear ownership and documentation."
            )

        improved_answer = (
            f"{sit} {task} {action} {result} "
            f"Keep the answer focused on {focus_area} and mention one clear measurable outcome."
        )
        answer_format = "direct"
    else:
        # Technical/general answers should be direct and question-specific, not STAR.
        q_lower = q.lower()
        focus = []
        sample = ""
        if "inheritance" in q_lower:
            focus = [
                "definition in one line",
                "why it is useful (reuse/extensibility)",
                "small class example",
                "real project context",
            ]
            sample = (
                "Inheritance means creating a new class from an existing class so the child class can reuse and extend parent behavior. "
                "For example, if `Vehicle` has `start()` and `stop()`, then `Car` can inherit `Vehicle` and add `airbagStatus()`. "
                "It helps reduce duplicate code and keeps designs easier to maintain."
            )
        elif "polymorphism" in q_lower:
            focus = [
                "clear definition",
                "compile-time and runtime distinction",
                "example in code",
                "benefit in scalable design",
            ]
            sample = (
                "Polymorphism means one interface with multiple implementations. "
                "Compile-time polymorphism is method overloading, and runtime polymorphism is method overriding through inheritance. "
                "For example, a `Shape` reference can call `draw()` and execute `Circle.draw()` or `Rectangle.draw()` at runtime."
            )
        elif "copy constructor" in q_lower:
            focus = [
                "what it is",
                "when it gets called",
                "deep copy vs shallow copy",
                "practical example",
            ]
            sample = (
                "A copy constructor creates a new object as a copy of an existing object. "
                "It is used when passing/returning objects by value or explicitly cloning an object. "
                "If the class manages dynamic memory, we implement deep copy to avoid shared pointers and unintended side effects."
            )
        elif "static binding" in q_lower or "dynamic binding" in q_lower:
            focus = [
                "difference between both bindings",
                "when each occurs",
                "method overloading/overriding relation",
                "small OOP example",
            ]
            sample = (
                "Static binding is resolved at compile time, typically in function overloading or non-virtual methods. "
                "Dynamic binding is resolved at runtime, typically in function overriding with virtual methods. "
                "Dynamic binding enables runtime polymorphism and flexible designs."
            )
        elif "stack" in q_lower and "what is" in q_lower:
            focus = [
                "LIFO definition",
                "core operations",
                "time complexity",
                "real use cases",
            ]
            sample = (
                "A stack is a linear data structure that follows LIFO (Last In, First Out). "
                "Main operations are push, pop, and top/peek, each usually O(1). "
                "Common uses are function call stack, undo operation, expression evaluation, and backtracking."
            )
        elif "binary search tree" in q_lower or "bst" in q_lower:
            focus = [
                "BST property",
                "basic node structure",
                "insert/search/delete approach",
                "complexity and balancing note",
            ]
            sample = (
                "A BST is a binary tree where left subtree values are smaller and right subtree values are larger than the node value. "
                "I would define a node with value, left, and right pointers, then implement insert/search recursively or iteratively. "
                "Average operations are O(log n), but can degrade to O(n) if unbalanced, so balanced BSTs are preferred."
            )
        elif "debug" in q_lower or "issue" in q_lower or "production" in q_lower:
            focus = [
                "how you reproduced the issue",
                "logs/metrics you checked first",
                "root-cause isolation steps",
                "fix + prevention guardrails",
            ]
            sample = (
                "In production, I first reproduce the issue with the same request path and correlate logs with metrics "
                "for error spikes, latency, and recent deploys. I isolate the failure to one service by checking trace IDs "
                "across dependencies, then validate the root cause with a minimal test case. After fixing the defect, I add "
                "a regression test, alert threshold, and runbook note so the same incident is detected and resolved faster next time."
            )
        elif "design" in q_lower or "architecture" in q_lower or "system" in q_lower or "api" in q_lower:
            focus = [
                "core components and boundaries",
                "data model and trade-offs",
                "scalability/reliability decisions",
                "failure handling and observability",
            ]
            sample = (
                "I would design this with a clear API layer, service layer, and persistence layer. The API enforces schema "
                "validation and idempotency, the service layer handles business rules, and the database uses indexed keys for read-heavy paths. "
                "For reliability, I would add retries with backoff, timeouts, and structured logs with request IDs. This gives predictable latency "
                "while keeping the system easy to scale horizontally."
            )
        elif "test" in q_lower or "quality" in q_lower:
            focus = [
                "test pyramid choices",
                "critical edge cases",
                "automation in CI/CD",
                "release confidence checks",
            ]
            sample = (
                "I follow a test pyramid: unit tests for core logic, integration tests for service contracts, and a small set of end-to-end tests "
                "for critical flows. I prioritize edge cases like invalid input, timeouts, and concurrency collisions. In CI/CD, I gate merges on "
                "test pass rate and coverage for modified modules, then run smoke tests in staging before release."
            )
        elif "performance" in q_lower or "optimi" in q_lower or "latency" in q_lower:
            focus = [
                "baseline and bottleneck identification",
                "optimization technique used",
                "before/after metrics",
                "trade-offs accepted",
            ]
            sample = (
                "I start by capturing a baseline using profiling and endpoint latency metrics, then identify the top bottleneck "
                "(query time, serialization, or network wait). I optimize the highest-impact path first, such as adding indexes, caching hot reads, "
                "or batching requests. I report before/after numbers and monitor error rate to ensure performance gains do not reduce correctness."
            )
        else:
            key_terms = _extract_key_terms(q, max_terms=4)
            key_phrase = ", ".join(key_terms) if key_terms else "the exact requirement asked in the question"
            is_definition = q_lower.startswith("what is") or q_lower.startswith("define") or "explain" in q_lower
            is_comparison = "difference between" in q_lower or " vs " in q_lower
            is_process = q_lower.startswith("how would you") or q_lower.startswith("how do you")

            focus = [
                "directly address the exact ask in first sentence",
                "use one correct technical explanation",
                "add one practical example",
                "close with trade-off or impact",
            ]
            if is_comparison:
                sample = (
                    f"The key difference in this question is around {key_phrase}. "
                    "I would compare both options across purpose, complexity/performance, and real-world usage. "
                    "Then I would give one short example where option A is preferred and one where option B is better."
                )
            elif is_process:
                sample = (
                    f"My approach would be step-by-step around {key_phrase}: clarify constraints, design/implement the core flow, "
                    "validate with tests/metrics, and then optimize bottlenecks. "
                    "I would also mention edge cases and how I would monitor production behavior."
                )
            elif is_definition:
                sample = (
                    f"This question is about {key_phrase}. I would start with a precise one-line definition, "
                    "then explain the core mechanism in simple technical terms. "
                    "After that, I would include one practical example and a short note on limitations or trade-offs."
                )
            else:
                sample = (
                    f"My answer would focus on {key_phrase}. I would first give a direct response, "
                    "then support it with one concrete implementation example, "
                    "and finish with the outcome and one trade-off considered."
                )

        improved_answer = sample
        answer_format = "direct"

    return {
        "feedback_text": " ".join(feedback_parts),
        "star_sample_answer": improved_answer,
        "star_structured": {
            "situation": sit,
            "task": task,
            "action": action,
            "result": result,
        },
        "answer_format": answer_format,
        "relevance_score": rel,
    }


def _compute_fusion_score(voice_nervous: float, facial_conf: float, relevance: float) -> float:
    """Compute weighted Interview Confidence Score (0-100)."""
    voice_conf = 100.0 - min(100, max(0, voice_nervous))
    fc = min(100, max(0, facial_conf))
    rc = min(100, max(0, relevance))
    return W_VOICE * voice_conf + W_FACIAL * fc + W_ANSWER * rc


# -------------------------------------------------------------------
# MAIN FUNCTION
# Generates final interview feedback
# -------------------------------------------------------------------
def generate_feedback(
    answers_data: list,
    voice_analyses: list,
    facial_analyses=None,
    resume_text: str = "",
) -> dict:
    """
    Parameters:
    answers_data     -> contains NLP evaluation for each answer
    voice_analyses   -> contains pitch, pauses, nervousness per answer
    facial_analyses  -> optional; contains facial confidence per answer
    resume_text      -> used for keyword alignment

    Returns:
    strengths, weaknesses, voice summary, answer summary, suggestions,
    interview_confidence_score, fusion_breakdown
    """

    strengths = []
    weaknesses = []
    suggestions = []

    def _band(score: float) -> str:
        s = float(min(100.0, max(0.0, score)))
        if s >= 80:
            return "excellent"
        if s >= 65:
            return "good"
        if s >= 50:
            return "fair"
        return "needs improvement"

    # Ensure facial_analyses is a list (may be empty)
    if facial_analyses is None:
        facial_analyses = []

    # If no answers recorded
    if not answers_data:
        return {
            "strengths": ["Completed the interview flow."],
            "weaknesses": ["No answer data was recorded."],
            "voice_analysis": {"overall": "No voice data."},
            "answer_analysis": {"overall": "No answers to analyze."},
            "facial_analysis": {"overall": "No facial data."},
            "interview_confidence_score": 0,
            "fusion_breakdown": {},
            "per_answer_coaching": [],
            "suggestions": ["Try recording answers for at least a few questions next time."],
        }

    # ---------------------------------------------------------------
    # Generate deterministic seed based on resume + transcripts
    # Ensures same interview -> same feedback
    # ---------------------------------------------------------------
    transcripts = [(a.get("transcript") or "") for a in answers_data]
    seed_base = hashlib.sha256(
        (resume_text + "|" + "|".join(transcripts)).encode("utf-8", errors="ignore")
    ).hexdigest()

    # ---------------------------------------------------------------
    # Extract evaluation metrics
    # ---------------------------------------------------------------
    evals = [(a.get("evaluation") or {}) for a in answers_data]
    relevance_scores = [e.get("relevance_score", 0) for e in evals]
    word_counts = [e.get("word_count") for e in evals]
    clarities = [e.get("clarity", "poor") for e in evals]
    length_cats = [e.get("answer_length_category") for e in evals]

    # If word count missing -> compute from transcript
    for i, wc in enumerate(list(word_counts)):
        if not isinstance(wc, int):
            word_counts[i] = len((transcripts[i] or "").strip().split())

    time_scores = [a.get("time_confidence_score", 0) for a in answers_data]

    # Average metrics
    avg_relevance = _mean(relevance_scores)
    avg_words = _mean(word_counts)
    avg_time_score = _mean(time_scores)
    good_clarity_count = sum(1 for c in clarities if c == "good")
    unclear_count = sum(1 for c in clarities if c == "poor")
    short_count = sum(1 for wc in word_counts if wc < 15)

    # ---------------------------------------------------------------
    # Resume keyword alignment
    # ---------------------------------------------------------------
    detected_all = []
    missing_all = []

    for e in evals:
        detected_all.extend(e.get("detected_keywords") or [])
        missing_all.extend(e.get("missing_keywords") or [])

    # Function to extract top frequent keywords
    def _top_terms(terms: list, n: int = 6) -> list:
        freq = {}
        for t in terms:
            if not t:
                continue
            freq[t] = freq.get(t, 0) + 1
        ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [t for t, _ in ranked[:n]]

    top_detected = _top_terms(detected_all)
    top_missing = _top_terms(missing_all)

    # ---------------------------------------------------------------
    # Voice Metrics Extraction
    # ---------------------------------------------------------------
    nervous_scores = [v.get("nervous_score", 50) for v in voice_analyses if isinstance(v, dict)]
    silence_ratios = [v.get("silence_ratio", 0) for v in voice_analyses if isinstance(v, dict)]
    pitch_means = [v.get("pitch_mean_hz", 0) for v in voice_analyses if isinstance(v, dict)]
    pitch_vars = [v.get("pitch_variance", 0) for v in voice_analyses if isinstance(v, dict)]

    pitch_stds = [math.sqrt(max(0.0, pv)) for pv in pitch_vars]

    avg_nervous = _mean(nervous_scores)
    avg_silence_ratio = _mean(silence_ratios)
    avg_pitch = _mean([p for p in pitch_means if p > 0])
    avg_pitch_std = _mean(pitch_stds)

    # ---------------------------------------------------------------
    # Cross-answer comparison
    # Detect hesitation trend
    # ---------------------------------------------------------------
    mid = max(1, len(nervous_scores) // 2)

    nervous_first = _mean(nervous_scores[:mid])
    nervous_last = _mean(nervous_scores[mid:])
    silence_first = _mean(silence_ratios[:mid])
    silence_last = _mean(silence_ratios[mid:])

    nervous_trend = _trend_label(nervous_first, nervous_last, threshold=6.0)
    silence_trend = _trend_label(silence_first, silence_last, threshold=0.05)

    # ---------------------------------------------------------------
    # Facial metrics (if available)
    # ---------------------------------------------------------------
    facial_confs = [
        f.get("confidence_score", 50)
        for f in facial_analyses
        if isinstance(f, dict)
    ]
    facial_nervous = [
        f.get("nervousness_score", 50)
        for f in facial_analyses
        if isinstance(f, dict)
    ]
    avg_facial_conf = _mean(facial_confs) if facial_confs else 50.0
    avg_facial_nervous = _mean(facial_nervous) if facial_nervous else 50.0

    # ---------------------------------------------------------------
    # Multi-modal fusion: Interview Confidence Score
    # ---------------------------------------------------------------
    interview_confidence = _compute_fusion_score(
        voice_nervous=avg_nervous,
        facial_conf=avg_facial_conf,
        relevance=avg_relevance,
    )
    interview_confidence = round(min(100, max(0, interview_confidence)), 1)

    # Breakdown for transparency (viva explanation)
    voice_conf_component = 100 - min(100, avg_nervous)
    voice_conf_component = max(0.0, voice_conf_component)
    fusion_breakdown = {
        "voice_confidence_contribution": round(W_VOICE * voice_conf_component, 2),
        "facial_confidence_contribution": round(W_FACIAL * avg_facial_conf, 2),
        "answer_relevance_contribution": round(W_ANSWER * avg_relevance, 2),
        "voice_confidence_score": round(voice_conf_component, 1),
        "facial_confidence_score": round(avg_facial_conf, 1),
        "answer_relevance_score": round(avg_relevance, 1),
        "overall_band": _band(interview_confidence),
        "weights": {"voice": W_VOICE, "facial": W_FACIAL, "answer": W_ANSWER},
    }

    # ---------------------------------------------------------------
    # Build voice summary
    # ---------------------------------------------------------------
    voice_overall = (
        f"Voice confidence is {_band(voice_conf_component)} ({voice_conf_component:.1f}/100). "
        f"Average nervousness is {avg_nervous:.1f}/100, with silence ratio {_fmt(avg_silence_ratio,2)} and "
        f"pitch mean {avg_pitch:.1f} Hz. Trend: nervousness {nervous_trend}, pauses {silence_trend}."
    )

    # ---------------------------------------------------------------
    # Build answer summary
    # ---------------------------------------------------------------
    answer_overall = (
        f"Answer quality is {_band(avg_relevance)} (relevance {avg_relevance:.1f}/100). "
        f"Average length is {avg_words:.1f} words and pacing score is {avg_time_score:.1f}/100. "
        f"Clear answers: {good_clarity_count}/{len(answers_data)}; unclear: {unclear_count}; short: {short_count}."
    )

    # ---------------------------------------------------------------
    # Strengths logic
    # ---------------------------------------------------------------
    if avg_relevance >= 70:
        strengths.append("Strong content relevance: answers consistently stayed aligned to interview intent and role context.")
    elif avg_relevance >= 55:
        strengths.append("Answer relevance is generally good with a solid base to build stronger depth.")

    if good_clarity_count >= len(answers_data) / 2:
        strengths.append("Most responses were clearly structured and easy to follow.")

    if avg_nervous < 55:
        strengths.append("Voice delivery remained relatively steady with manageable nervousness.")

    if avg_facial_conf >= 60 and facial_confs:
        strengths.append("Facial presence showed positive confidence cues and engagement.")
    elif not facial_confs:
        strengths.append("Interview flow was completed even without webcam signals.")

    # ---------------------------------------------------------------
    # Weakness logic
    # ---------------------------------------------------------------
    if avg_relevance < 50:
        weaknesses.append("Content relevance is low; several answers need clearer linkage to the exact question and role.")
    elif avg_relevance < 65:
        weaknesses.append("Answers are partially relevant but still miss technical or outcome-level depth in places.")

    if unclear_count > 0:
        weaknesses.append("Some responses lacked crisp structure, which reduced clarity and impact.")

    if avg_nervous >= 60:
        weaknesses.append("Voice profile shows elevated nervousness and inconsistent pacing in parts.")

    if avg_facial_nervous >= 60 and facial_nervous:
        weaknesses.append("Facial cues suggest visible stress during some answers.")

    if top_missing:
        weaknesses.append("Important resume keywords were underused in answers, weakening profile alignment.")

    # ---------------------------------------------------------------
    # Suggestions generation
    # ---------------------------------------------------------------
    if unclear_count > 0 or avg_relevance < 65:
        suggestions.append("Use a repeatable 3-part response pattern: context, action, measurable result.")
    if top_missing:
        suggestions.append(f"Intentionally include resume anchors such as: {', '.join(top_missing[:4])}.")
    if avg_nervous >= 55 or avg_silence_ratio >= 0.18:
        suggestions.append("Improve delivery control with pause-breath-pause pacing and slower first 10 seconds.")
    if avg_time_score < 65 or short_count > 0:
        suggestions.append("Target 60-90 second answers with one concrete example and one quantified outcome.")
    if facial_confs and avg_facial_conf < 60:
        suggestions.append("Maintain camera-facing posture and steady eye line to improve visible confidence.")
    if not suggestions:
        suggestions.append("Maintain current performance; focus on role-specific depth and sharper metrics in examples.")

    # ---------------------------------------------------------------
    # Build facial summary
    # ---------------------------------------------------------------
    facial_overall = (
        f"Facial confidence is {_band(avg_facial_conf)} ({avg_facial_conf:.1f}/100), "
        f"with nervousness at {avg_facial_nervous:.1f}/100."
        if facial_confs
        else "No facial data captured (enable webcam for full analysis)."
    )

    # ---------------------------------------------------------------
    # Final output
    # ---------------------------------------------------------------
    per_question_breakdown = []
    for i, answer in enumerate(answers_data):
        eval_item = (answer.get("evaluation") or {}) if isinstance(answer, dict) else {}
        voice_item = voice_analyses[i] if i < len(voice_analyses) else {}
        facial_item = facial_analyses[i] if i < len(facial_analyses) else {}
        time_score_val = round(float(answer.get("time_confidence_score", 0) or 0), 1)

        # Per-answer voice score: blend multiple signals so values are not flat.
        nervous_raw = voice_item.get("nervous_score", None) if isinstance(voice_item, dict) else None
        silence_raw = voice_item.get("silence_ratio", None) if isinstance(voice_item, dict) else None
        rate_raw = voice_item.get("speaking_rate", None) if isinstance(voice_item, dict) else None
        energy_raw = voice_item.get("energy_mean", voice_item.get("energy", None)) if isinstance(voice_item, dict) else None

        nervous = float(nervous_raw) if isinstance(nervous_raw, (int, float)) else None
        silence_ratio = float(silence_raw) if isinstance(silence_raw, (int, float)) else None
        speaking_rate = float(rate_raw) if isinstance(rate_raw, (int, float)) else None
        energy_mean = float(energy_raw) if isinstance(energy_raw, (int, float)) else None

        if nervous is not None:
            base_voice = 100.0 - min(100.0, max(0.0, nervous))
            silence_component = 100.0 - min(100.0, max(0.0, (silence_ratio or 0.0) * 100.0))
            # Tempo centered around ~120 BPM equivalent speaking rhythm.
            pace_component = 100.0 - min(40.0, abs((speaking_rate or 120.0) - 120.0) * 0.5)
            # Keep energy contribution small but non-zero to avoid repeated identical values.
            energy_component = 60.0 + min(30.0, max(-20.0, (energy_mean or 0.02) * 600.0))
            voice_score_val = (
                0.65 * base_voice
                + 0.2 * silence_component
                + 0.1 * pace_component
                + 0.05 * energy_component
            )
        else:
            # Fallback: use pacing + transcript length proxy instead of a fixed 50.
            transcript_wc = len((answer.get("transcript") or "").strip().split())
            length_component = min(100.0, max(35.0, 35.0 + transcript_wc * 1.3))
            voice_score_val = 0.7 * time_score_val + 0.3 * length_component

        voice_score_val = round(min(100.0, max(0.0, voice_score_val)), 1)
        per_question_breakdown.append(
            {
                "question_index": i + 1,
                "question": answer.get("question", ""),
                "answer_score": round(float(eval_item.get("relevance_score", 0) or 0), 1),
                "voice_score": voice_score_val,
                "facial_score": round(float(facial_item.get("confidence_score", 50) or 50), 1),
                "time_score": time_score_val,
            }
        )

    trend = "stable"
    if len(per_question_breakdown) >= 2:
        first = per_question_breakdown[0]["answer_score"]
        last = per_question_breakdown[-1]["answer_score"]
        if last - first >= 10:
            trend = "improving"
        elif first - last >= 10:
            trend = "declining"

    per_answer_coaching = []
    for a in answers_data:
        if not isinstance(a, dict):
            continue
        q = (a.get("question") or "").strip()
        transcript = (a.get("transcript") or "").strip()
        evaluation = a.get("evaluation") or {}
        ch = generate_answer_coaching(q, transcript, evaluation, resume_text)
        per_answer_coaching.append(
            {
                "question": q,
                "feedback_text": ch.get("feedback_text", ""),
                "star_sample_answer": ch.get("star_sample_answer", ""),
                "star_structured": ch.get("star_structured"),
            }
        )

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "interview_confidence_score": interview_confidence,
        "fusion_breakdown": fusion_breakdown,
        "performance_matrix": {
            "overall_band": _band(interview_confidence),
            "content_score": round(avg_relevance, 1),
            "voice_score": round(voice_conf_component, 1),
            "facial_score": round(avg_facial_conf, 1) if facial_confs else None,
            "pacing_score": round(avg_time_score, 1),
            "clarity_rate": round((good_clarity_count / max(1, len(answers_data))) * 100.0, 1),
            "resume_alignment_score": round(min(100.0, max(0.0, avg_relevance + (8 if top_detected else 0) - (6 if top_missing else 0))), 1),
            "trend": trend,
        },
        "per_answer_coaching": per_answer_coaching,
        "improved_sample_answers": per_answer_coaching,
        "voice_analysis": {
            "overall": voice_overall,
            "metrics": {
                "avg_pitch_mean_hz": round(avg_pitch, 2),
                "avg_pitch_std": round(avg_pitch_std, 2),
                "avg_silence_ratio": round(avg_silence_ratio, 2),
                "avg_nervous_score": round(avg_nervous, 1),
                "nervous_trend": nervous_trend,
                "silence_trend": silence_trend,
            },
            "per_answer": voice_analyses,
        },
        "facial_analysis": {
            "overall": facial_overall,
            "metrics": {
                "avg_confidence_score": round(avg_facial_conf, 1),
                "avg_nervousness_score": round(avg_facial_nervous, 1),
            },
            "per_answer": facial_analyses,
        },
        "answer_analysis": {
            "overall": answer_overall,
            "metrics": {
                "avg_relevance_score": round(avg_relevance, 1),
                "avg_word_count": round(avg_words, 1),
                "avg_time_score": round(avg_time_score, 1),
                "overall_band": _band(avg_relevance),
                "good_clarity_count": good_clarity_count,
                "unclear_count": unclear_count,
                "short_count": short_count,
                "resume_keywords_detected_top": top_detected,
                "resume_keywords_missing_top": top_missing,
            },
            "per_answer": answers_data,
        },
        "time_analysis": {
            "overall": f"Average response pacing score: {round(avg_time_score, 1)}/100.",
            "avg_time_confidence_score": round(avg_time_score, 1),
        },
        "per_question_breakdown": per_question_breakdown,
        "performance_trend": trend,
        "suggestions": suggestions,
    }
