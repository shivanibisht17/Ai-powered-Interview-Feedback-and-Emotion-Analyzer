"""Generate interview questions from resume + role + company + job description."""

import re
import random
import hashlib
from llm_helper import llm_generate_questions


def extract_skills_and_topics(resume_text: str) -> list:
    """Extract skills, experience, and education mentions from resume."""

    text = resume_text.lower()
    topics = []

    skill_patterns = [
        r"\b(python|java|javascript|react|node\.?js|sql|aws|docker|kubernetes|machine learning|ai|agile|scrum)\b",
        r"\b(communication|leadership|problem solving|teamwork|analytical)\b",
        r"\b(bachelor|master|phd|degree|b\.?s\.?|m\.?s\.?)\b",
        r"\b(\d+)\+?\s*years?\s*(of\s*)?(experience|exp)\b",
        r"\b(engineer|developer|analyst|manager|intern)\b",
        r"\b(project|product|software|data)\b",
    ]

    for pattern in skill_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            word = m[0] if isinstance(m, tuple) else m
            if word and word not in [t.lower() for t in topics]:
                topics.append(word.title())

    if not topics:
        topics = ["your background", "your experience", "your skills", "your goals"]

    return list(set(topics))[:15]


def _question_item(category: str, text: str) -> dict:
    return {"category": category, "text": text}


def _contains_any(text: str, keywords: list) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def _resume_driven_technical_questions(resume_text: str, role_clean: str) -> list:
    """
    Build explicit technical questions from resume keywords.
    Prioritizes classic interview topics user requested (projects, OOP, DSA).
    """
    text = (resume_text or "").lower()
    q = []

    # Always include project deep-dive style prompts.
    q.extend(
        [
            _question_item(
                "technical",
                "Explain one project from your resume end-to-end: problem statement, architecture, your exact contribution, and final outcome.",
            ),
            _question_item(
                "technical",
                "What technologies did you use in that project, and why did you choose each one over alternatives?",
            ),
            _question_item(
                "technical",
                "What was the hardest bug in your project, and how did you debug and fix it?",
            ),
        ]
    )

    if _contains_any(text, ["oops", "oop", "object oriented", "c++", "java"]):
        q.extend(
            [
                _question_item("technical", "Explain inheritance with a practical example from your code."),
                _question_item("technical", "Explain polymorphism (compile-time vs runtime) with examples."),
                _question_item("technical", "What is a copy constructor, and when do we need it?"),
                _question_item("technical", "What is encapsulation and abstraction? Give a class design example."),
                _question_item("technical", "Explain static binding vs dynamic binding with example."),
                _question_item("technical", "What is function overloading vs overriding?"),
            ]
        )

    if _contains_any(text, ["data structure", "data structures", "dsa", "algorithm"]):
        q.extend(
            [
                _question_item("technical", "What is a stack? Explain push, pop, and real-world use cases."),
                _question_item("technical", "How would you design/implement a Binary Search Tree (BST)?"),
                _question_item("technical", "What is the time complexity of search/insert/delete in BST, and how does balancing help?"),
                _question_item("technical", "Difference between stack and queue, and where would you use each?"),
                _question_item("technical", "Compare array vs linked list with practical trade-offs."),
                _question_item("technical", "What is recursion? Explain recursion vs iteration with one example."),
            ]
        )

    if _contains_any(text, ["sql", "mysql", "postgres", "database", "dbms"]):
        q.extend(
            [
                _question_item("technical", "Explain normalization and when you might intentionally denormalize."),
                _question_item("technical", "What is the difference between an index scan and a full table scan?"),
            ]
        )

    if _contains_any(text, ["os", "operating system", "threads", "process", "deadlock"]):
        q.extend(
            [
                _question_item("technical", "Explain process vs thread with a practical example."),
                _question_item("technical", "What is deadlock, and how can you prevent or avoid it?"),
            ]
        )

    if _contains_any(text, ["computer networks", "networking", "tcp", "udp", "http"]):
        q.extend(
            [
                _question_item("technical", "Explain TCP vs UDP and when you would choose each."),
                _question_item("technical", "Walk through what happens when you open a website URL in the browser."),
            ]
        )

    if _contains_any(text, ["python", "java", "javascript", "react", "node", "api", "backend"]):
        q.append(
            _question_item(
                "technical",
                f"For {role_clean}, explain one debugging issue you handled and how you fixed it step by step.",
            )
        )

    # Keep order, remove duplicates.
    unique = []
    seen = set()
    for item in q:
        key = (item.get("category"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _seeded_rng(*parts: str) -> random.Random:
    joined = "|".join([p for p in parts if p is not None])
    digest = hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _sanitize_question_text(text: str, category: str = "") -> str:
    """Remove forced story/life-history phrasing from HR-style prompts."""
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()

    # Remove explicit suffix previously appended in HR generation.
    cleaned = re.sub(
        r"\s*Ground your answer with a concrete story involving [^\.!?]+[\.!?]?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    is_hr_like = (category or "").strip().lower() in {"hr", "behavioral", "company", "role"}
    if is_hr_like:
        # Soften opening prompts that demand a specific story.
        replacements = [
            (r"^Describe a time\s+", "How do you typically "),
            (r"^Give an example where\s+", "How do you "),
            (r"^Tell me about a time when\s+", "How do you "),
        ]
        for pattern, repl in replacements:
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    return cleaned


def _sanitize_questions(items: list) -> list:
    sanitized = []
    for item in items or []:
        if isinstance(item, dict):
            cat = item.get("category", "")
            txt = _sanitize_question_text(item.get("text", ""), cat)
            if txt:
                sanitized.append({"category": cat, "text": txt})
        elif isinstance(item, str):
            txt = _sanitize_question_text(item, "")
            if txt:
                sanitized.append({"category": "general", "text": txt})
    return sanitized


def _jd_keywords(jd_text: str, max_terms: int = 8) -> list[str]:
    """Lightweight JD token extraction for question tailoring."""
    if not jd_text or not isinstance(jd_text, str):
        return []
    clean = re.sub(r"[^\w\s]", " ", jd_text.lower())
    tokens = [w for w in clean.split() if len(w) >= 4][:200]
    freq: dict[str, int] = {}
    stop = {
        "that", "with", "from", "this", "have", "will", "your", "their", "must", "should",
        "ability", "experience", "years", "work", "team", "role", "job", "description",
    }
    for t in tokens:
        if t in stop:
            continue
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:max_terms]]


INTERVIEW_TYPES = ("HR", "Technical", "Role-Based", "Company-Based", "JD-Based")


def _normalize_interview_type(raw: str) -> str:
    t = (raw or "").strip()
    if t in INTERVIEW_TYPES:
        return t
    return "Technical"


def generate_questions(
    resume_text: str,
    role: str = "",
    company: str = "",
    jd_text: str = "",
    interview_type: str = "",
    session_seed: str = "",
) -> list:
    """
    Build an interview plan driven by interview_type (distinct mixes and wording).

    Types:
    - HR: behavioral, culture-fit, communication, conflict, motivation (minimal coding).
    - Technical: depth on systems, debugging, testing, architecture tied to resume topics.
    - Role-Based: every prompt explicitly anchors responsibilities for the target role.
    - Company-Based: mission, values, stakeholder style, and "why this company" emphasis.
    - JD-Based: questions tightly mapped to pasted job description keywords.
    """
    topics = extract_skills_and_topics(resume_text or "")
    jd_terms = _jd_keywords(jd_text or "")
    role_clean = (role or "").strip() or "this role"
    company_clean = (company or "").strip() or "the organization"
    jd_phrase = " referencing the responsibilities you pasted" if jd_terms else ""
    itype = _normalize_interview_type(interview_type)

    technical_pool = [
        f"For the {role_clean} position at {company_clean}, walk through a system or feature you owned end-to-end.",
        "How would you debug a production issue when logs are incomplete and users are impacted?",
        "Describe a performance or reliability optimization you implemented and how you measured success.",
        "What is your approach to testing before a release (unit, integration, staging, feature flags)?",
        "Design a simple API or data model for a feature you shipped; what trade-offs did you consider?",
    ]
    situational_pool = [
        "You have two high-priority tasks with the same deadline. How do you prioritize and communicate?",
        "A release is failing minutes before deployment. What steps do you take?",
        "How would you explain a complex technical trade-off to a non-technical stakeholder?",
    ]
    hr_pool = [
        "Tell me about yourself and what you are looking for next in your career.",
        "What are your key strengths, and what skill are you actively improving?",
        "How do you typically resolve conflict or misalignment within a team?",
        "How do you approach ownership beyond your formal responsibilities?",
        "How do you handle feedback when you disagree with it?",
        "How do you respond to failure or setbacks, and what do you improve afterward?",
    ]
    role_pool = [
        f"As {role_clean}, how do you define success in the first 90 days?",
        f"What is the hardest problem you have solved that maps directly to {role_clean} expectations?",
        f"How do you keep stakeholders aligned while executing deep work expected of a {role_clean}?",
        f"Which tools or practices from your background will you lean on most in {role_clean}, and why?",
        f"Describe how you would ramp on an unfamiliar codebase or domain for {role_clean}.",
    ]
    company_pool = [
        f"Why {company_clean} specifically, and what research have you done about how they operate?",
        f"How would you adapt your communication style to {company_clean}'s stakeholders and pace?",
        f"What concerns or risks do you see joining {company_clean}, and how would you mitigate them?",
        f"Tell me about a time you thrived in an environment similar to what you expect at {company_clean}.",
        f"If {company_clean} prioritized speed over polish for a quarter, how would you respond professionally?",
    ]

    total = 7
    questions: list = []

    # Prefer LLM-generated dynamic questions when API is configured.
    llm_questions = llm_generate_questions(
        resume_text=resume_text or "",
        role=role_clean,
        company=company_clean,
        interview_type=itype,
        total_questions=total,
        session_seed=session_seed or "",
    )
    if llm_questions:
        return _sanitize_questions(llm_questions)[:total]

    if itype == "HR":
        for i in range(total):
            base = hr_pool[i % len(hr_pool)]
            hook = topics[i % len(topics)] if topics else "your experience"
            questions.append(
                _question_item(
                    "hr",
                    f"{base} Keep your answer professional and role-relevant, especially around {hook}.",
                )
            )
        return _sanitize_questions(questions)[:total]

    if itype == "Technical":
        rng = _seeded_rng(resume_text or "", role_clean, company_clean, jd_text or "", itype, session_seed or "")
        # Resume-aware technical-first plan.
        # Priority: explicit concept questions from resume (projects/OOP/DSA/etc),
        # then generic technical depth, then only 1 HR question at end.
        targeted = _resume_driven_technical_questions(resume_text or "", role_clean)
        rng.shuffle(targeted)
        for item in targeted:
            questions.append(item)
            if len(questions) >= total - 1:
                break

        technical_candidates = []
        i = 0
        while len(technical_candidates) < 24:
            topic = topics[i % len(topics)] if topics else "your core skillset"
            if i % 3 == 2:
                base = situational_pool[i % len(situational_pool)]
                technical_candidates.append(
                    _question_item(
                        "situational",
                        f"In the context of {role_clean} and your experience with {topic}, {base.lower()}",
                    )
                )
            else:
                base = technical_pool[i % len(technical_pool)]
                technical_candidates.append(
                    _question_item(
                        "technical",
                        f"{base} Relate your answer to {topic}.",
                    )
                )
            i += 1
        rng.shuffle(technical_candidates)

        for item in technical_candidates:
            if len(questions) >= total - 1:
                break
            if item not in questions:
                questions.append(item)

        questions.append(_question_item("hr", "Briefly introduce yourself and connect your profile to this role."))
        return _sanitize_questions(questions)[:total]

    if itype == "Role-Based":
        for i in range(total):
            topic = topics[i % len(topics)] if topics else "your background"
            base = role_pool[i % len(role_pool)]
            questions.append(
                _question_item(
                    "role",
                    f"{base} Tie the story to evidence from your work with {topic}.",
                )
            )
        return _sanitize_questions(questions)[:total]

    if itype == "Company-Based":
        for i in range(total):
            topic = topics[i % len(topics)] if topics else "your experience"
            base = company_pool[i % len(company_pool)]
            if i % 2 == 0:
                questions.append(_question_item("company", f"{base} Reference real examples involving {topic}."))
            else:
                questions.append(
                    _question_item(
                        "company",
                        f"{base} Connect your answer to measurable outcomes, not generic praise.",
                    )
                )
        return _sanitize_questions(questions)[:total]

    if itype == "JD-Based":
        if not jd_terms:
            jd_terms = ["core responsibilities", "must-have skills", "delivery expectations", "collaboration norms"]
        n = len(jd_terms)
        for i in range(total):
            picks = [jd_terms[(i + j) % n] for j in range(min(3, n))]
            focus = ", ".join(picks)
            questions.append(
                _question_item(
                    "jd",
                    f"Against the JD themes ({focus}), describe a project where you demonstrated those capabilities{jd_phrase}.",
                )
            )
        return _sanitize_questions(questions)[:total]

    return []
