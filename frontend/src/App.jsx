import { useState, useEffect, useCallback } from "react";
import Recorder from "./Recorder";
import {
  uploadResume,
  submitAnswer,
  endInterview,
  getFeedback,
  realtimeAnalysis,
  listSessions,
  getHistorySession,
  wakeBackend,
  formatApiError,
} from "./api";

const INTERVIEW_TYPES = [
  { id: "HR", label: "HR", hint: "Behavioral and soft-skills focus." },
  { id: "Technical", label: "Technical", hint: "Depth on systems, debugging, and craft." },
  { id: "Role-Based", label: "Role-Based", hint: "Anchored to the target role you enter." },
  { id: "Company-Based", label: "Company-Based", hint: "Culture, motivation, and company context." },
  { id: "JD-Based", label: "JD-Based", hint: "Maps to pasted job description keywords." },
];

const TARGET_ROLE_OPTIONS = [
  "Software Engineer",
  "Frontend Developer",
  "Backend Developer",
  "Full Stack Developer",
  "Data Analyst",
  "Data Scientist",
  "Machine Learning Engineer",
  "DevOps Engineer",
  "QA Engineer",
  "Product Manager",
];
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

function Section({ label, title, children, className = "" }) {
  return (
    <section
      className={`rounded-2xl border border-slate-700/80 bg-surface-800/60 backdrop-blur-sm p-4 sm:p-6 shadow-xl ${className}`}
    >
      {(label || title) && (
        <div className="mb-4">
          {label && (
            <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold">{label}</div>
          )}
          {title && <h2 className="text-lg font-semibold text-white mt-1">{title}</h2>}
        </div>
      )}
      <div className="text-slate-200">{children}</div>
    </section>
  );
}

function describeScore(score, type = "generic") {
  if (typeof score !== "number" || Number.isNaN(score)) return "No signal captured.";
  const s = Math.max(0, Math.min(100, score));

  if (type === "facial") {
    if (s >= 75) return "Strong on-camera confidence and presence.";
    if (s >= 55) return "Generally confident, with some visible tension.";
    if (s >= 40) return "Mixed presence; confidence is not consistent yet.";
    return "Low visible confidence; posture/expression needs improvement.";
  }

  if (type === "voice") {
    if (s >= 75) return "Calm tone and stable pacing.";
    if (s >= 55) return "Mostly steady voice, minor nervous markers.";
    if (s >= 40) return "Noticeable pauses/tone fluctuation.";
    return "High vocal nervousness; pacing and breath control need work.";
  }

  if (type === "answer") {
    if (s >= 75) return "Highly relevant and well-aligned response.";
    if (s >= 55) return "Reasonably relevant, can be more specific.";
    if (s >= 40) return "Partially relevant; missing key details.";
    return "Low relevance; answer did not address the question clearly.";
  }

  if (type === "pacing") {
    if (s >= 75) return "Strong answer timing for interview delivery.";
    if (s >= 55) return "Acceptable timing with minor pacing drift.";
    if (s >= 40) return "Timing is uneven; answer length needs tuning.";
    return "Timing is weak; too short/too long for interview impact.";
  }

  if (type === "overall") {
    if (s >= 75) return "Interview-ready overall performance.";
    if (s >= 55) return "Good foundation with clear improvement areas.";
    if (s >= 40) return "Moderate readiness; needs focused practice.";
    return "Early-stage readiness; coaching and repetition recommended.";
  }

  if (s >= 75) return "Strong performance.";
  if (s >= 55) return "Good performance with room to improve.";
  if (s >= 40) return "Moderate performance.";
  return "Needs improvement.";
}

function sanitizeQuestionText(text) {
  if (typeof text !== "string") return "";
  return text
    .replace(/\s*Ground your answer with a concrete story involving [^.!?]+[.!?]?\s*$/i, "")
    .trim();
}

function scoreChipClass(score) {
  if (typeof score !== "number" || Number.isNaN(score)) return "bg-slate-700/60 text-slate-200";
  if (score >= 75) return "bg-emerald-500/20 text-emerald-300";
  if (score >= 55) return "bg-sky-500/20 text-sky-300";
  if (score >= 40) return "bg-amber-500/20 text-amber-300";
  return "bg-rose-500/20 text-rose-300";
}

function metricTile(title, value, tone = "generic") {
  return (
    <div className="rounded-xl border border-slate-700 bg-surface-900/40 p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-lg font-semibold text-white">{value}</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full ${scoreChipClass(typeof value === "string" ? Number(value.split("/")[0]) : Number(value))}`}>
          {tone}
        </span>
      </div>
    </div>
  );
}

export default function App() {
  const QUESTION_TIME_LIMIT_SECONDS = 75;
  const [step, setStep] = useState("upload");
  const [resumeFile, setResumeFile] = useState(null);
  const [interviewType, setInterviewType] = useState(null);
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [extractedText, setExtractedText] = useState("");
  const [questions, setQuestions] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [perAnswerResults, setPerAnswerResults] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [liveScore, setLiveScore] = useState(null);
  const [liveAnalyzing, setLiveAnalyzing] = useState(false);
  const [liveIndicator, setLiveIndicator] = useState("");

  const [pastSessions, setPastSessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);

  const speakQuestion = useCallback((text) => {
    if (!text || typeof text !== "string") return;
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new window.SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 0.9;
    window.speechSynthesis.speak(u);
  }, []);

  useEffect(() => {
    if (step !== "interview" || !questions.length) return;
    const q = questions[currentIndex];
    const text = typeof q === "string" ? q : q?.text;
    if (text) speakQuestion(text);
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    };
  }, [step, currentIndex, questions, speakQuestion]);

  const loadHistory = async () => {
    setHistoryLoading(true);
    setError("");
    setHistoryDetail(null);
    try {
      const data = await listSessions(40);
      setPastSessions(data.sessions || []);
      setStep("history");
    } catch (e) {
      setError(formatApiError(e, "Could not load sessions."));
    } finally {
      setHistoryLoading(false);
    }
  };

  const openHistoryDetail = async (sessionId) => {
    setHistoryDetailLoading(true);
    setHistoryDetail(null);
    setStep("historyDetail");
    setError("");
    try {
      const d = await getHistorySession(sessionId);
      setHistoryDetail(d);
    } catch (e) {
      setError(formatApiError(e, "Could not load session detail."));
      setStep("history");
    } finally {
      setHistoryDetailLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!resumeFile) {
      setError("Please select a PDF file.");
      return;
    }
    if (!interviewType) {
      setError("Please select an interview type.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const data = await uploadResume(resumeFile, {
        role,
        company,
        jobDescription,
        interviewType,
      });
      setExtractedText(data.extracted_text || "");
      const rawQ = data.categorized_questions?.length ? data.categorized_questions : data.questions || [];
      setQuestions(
        rawQ
          .map((item) => {
            if (typeof item === "string") {
              return { text: sanitizeQuestionText(item), category: "" };
            }
            return {
              ...item,
              text: sanitizeQuestionText(item?.text || ""),
            };
          })
          .filter((item) => item?.text)
      );
      setStep("interview");
      setCurrentIndex(0);
      setPerAnswerResults([]);
      wakeBackend();
    } catch (e) {
      setError(formatApiError(e, "Upload failed."));
    } finally {
      setLoading(false);
    }
  };

  const handleAnswerComplete = async (blob, facialFrames = [], meta = {}) => {
    const q = questions[currentIndex];
    const qText = sanitizeQuestionText(typeof q === "string" ? q : q?.text);
    if (!q) return;
    setLoading(true);
    setError("");
    try {
      const data = await submitAnswer(blob, qText, facialFrames, {
        questionIndex: currentIndex,
        timeTaken: meta?.timeTaken ?? 0,
      });
      setPerAnswerResults((prev) => {
        const next = [...prev];
        next[currentIndex] = {
          question_index: currentIndex,
          question: qText,
          transcript: data.transcript || "",
          voice_analysis: data.voice_analysis || null,
          facial_analysis: data.facial_analysis || null,
          evaluation: data.evaluation || null,
          time_taken: data.time_taken ?? meta?.timeTaken ?? 0,
          time_confidence_score: data.time_confidence_score ?? 0,
        };
        return next;
      });
      if (currentIndex + 1 >= questions.length) {
        await endInterview();
        const fb = await getFeedback();
        setFeedback(fb);
        setStep("results");
      } else {
        setCurrentIndex((i) => i + 1);
      }
    } catch (e) {
      setError(formatApiError(e, "Submit failed."));
    } finally {
      setLoading(false);
    }
  };

  const handleRealtimeUpdate = async (audioChunk, frameBlob) => {
    setLiveAnalyzing(true);
    try {
      const data = await realtimeAnalysis(audioChunk, frameBlob);
      if (typeof data.live_confidence_score === "number") {
        setLiveScore(data.live_confidence_score);
      }
      setLiveIndicator(data.nervousness_indicator || "Live analysis");
    } catch {
      // Keep UI smooth during transient chunk failures.
    } finally {
      setLiveAnalyzing(false);
    }
  };

  const handleRecordingChange = useCallback((recording) => {
    setIsRecording(!!recording);
    if (recording) {
      setLiveScore(null);
      setLiveAnalyzing(false);
      setLiveIndicator("");
    } else {
      setLiveScore(null);
      setLiveAnalyzing(false);
      setLiveIndicator("");
    }
  }, []);

  const skipQuestion = async () => {
    const q = questions[currentIndex];
    if (!q) return;
    setError("");
    if (currentIndex + 1 >= questions.length) {
      setLoading(true);
      try {
        await endInterview();
        const fb = await getFeedback();
        setFeedback(fb);
        setStep("results");
      } catch (e) {
        setError(formatApiError(e, "Could not end interview."));
      } finally {
        setLoading(false);
      }
    } else {
      setCurrentIndex((i) => i + 1);
    }
  };

  if (step === "upload") {
    return (
      <div className="min-h-screen bg-gradient-to-b from-surface-900 via-surface-900 to-slate-950">
        <div className="max-w-4xl mx-auto px-4 py-8 sm:py-12 space-y-8 sm:space-y-10">
          <header className="text-center space-y-3">
            <p className="text-xs uppercase tracking-[0.2em] text-accent font-semibold">AI Mock Interview</p>
            <h1 className="text-4xl font-bold text-white">InterviewPrep AI</h1>
            <p className="text-slate-400 max-w-xl mx-auto">
              Upload your resume, choose an interview style, then practice with voice and webcam analysis.
              Live confidence updates while you record; STAR coaching appears in final feedback.
            </p>
          </header>

          <div className="grid sm:grid-cols-3 gap-4">
            {[
              ["Resume intelligence", "PDF text extraction and skill-aware topics."],
              ["Multimodal scoring", "Whisper, Librosa, MediaPipe, TF-IDF fusion."],
              ["Coaching", "Final feedback with improved STAR sample answers."],
            ].map(([t, d]) => (
              <div
                key={t}
                className="group rounded-xl border border-slate-700 bg-surface-800/50 p-4 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-sky-500/20 hover:border-sky-400/70 hover:bg-surface-800/95"
              >
                <h3 className="text-sm font-semibold text-white mb-1">{t}</h3>
                <p className="text-xs text-slate-400 leading-relaxed group-hover:text-slate-200 transition-colors duration-300">
                  {d}
                </p>
              </div>
            ))}
          </div>

          <Section label="Setup" title="Resume & interview context">
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-2">Interview type</label>
                <div className="flex flex-wrap gap-2">
                  {INTERVIEW_TYPES.map((t) => {
                    const selected = interviewType === t.id;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setInterviewType(t.id)}
                        className={`px-3 py-2 rounded-lg text-sm font-medium border transition ${
                          selected
                            ? "border-accent bg-accent/15 text-white ring-2 ring-accent/60 shadow-lg shadow-sky-500/10"
                            : "border-slate-600 text-slate-300 hover:border-slate-500 hover:bg-slate-800/60"
                        }`}
                        title={t.hint}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                </div>
                {interviewType && (
                  <p className="text-xs text-slate-500 mt-2">
                    {INTERVIEW_TYPES.find((x) => x.id === interviewType)?.hint}
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Resume (PDF)</label>
                <input
                  className="block w-full text-sm text-slate-200 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-slate-700 file:text-white file:cursor-pointer"
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setResumeFile(e.target.files?.[0] || null)}
                />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-slate-300 mb-1">Target role</label>
                  <select
                    className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                  >
                    <option value="">Select target role</option>
                    {TARGET_ROLE_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-300 mb-1">Company</label>
                  <input
                    className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
                    placeholder="e.g. Acme Corp"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Job description (optional)</label>
                <textarea
                  className="w-full min-h-[100px] rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
                  placeholder="Paste key responsibilities or requirements to tailor technical questions."
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-700 hover:!bg-slate-800 hover:!text-white text-white font-semibold text-sm disabled:opacity-50 transition-all duration-200 hover:-translate-y-0.5"
                  onClick={handleUpload}
                  disabled={loading || !interviewType || !resumeFile}
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m5 12 5 5L20 7" />
                  </svg>
                  {loading ? "Uploading…" : "Start interview (upload & generate)"}
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border border-slate-600 text-slate-200 text-sm hover:bg-slate-800 hover:!text-white transition-all duration-200 hover:-translate-y-0.5"
                  onClick={loadHistory}
                  disabled={historyLoading}
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 12a9 9 0 1 0 3-6.7" />
                    <path d="M3 3v6h6" />
                  </svg>
                  {historyLoading ? "Loading…" : "Past interviews"}
                </button>
              </div>
              {error && <p className="text-sm text-rose-400">{error}</p>}
            </div>
          </Section>

        </div>
      </div>
    );
  }

  if (step === "history") {
    return (
      <div className="min-h-screen bg-surface-900 px-4 py-10">
        <div className="max-w-3xl mx-auto space-y-6">
          <header className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">Past interviews</h1>
              <p className="text-slate-400 text-sm">Stored locally in SQLite via the Flask API.</p>
            </div>
            <button
              type="button"
              className="text-sm text-accent hover:underline"
              onClick={() => setStep("upload")}
            >
              ← Back to setup
            </button>
          </header>
          {error && <p className="text-sm text-rose-400">{error}</p>}
          {historyLoading ? (
            <div className="rounded-2xl border border-slate-700 p-10 text-center text-slate-400 text-sm">
              Loading past interviews…
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-700 divide-y divide-slate-700 overflow-hidden">
              {pastSessions.length === 0 && (
                <div className="p-6 text-slate-400 text-sm">No past interviews found.</div>
              )}
              {pastSessions.map((s) => (
                <button
                  key={s.session_id}
                  type="button"
                  onClick={() => openHistoryDetail(s.session_id)}
                  className="w-full text-left p-4 flex flex-wrap justify-between gap-3 bg-surface-800/40 hover:bg-slate-800/80 transition cursor-pointer"
                >
                  <div>
                    <div className="text-white font-medium text-sm">
                      {s.company || "—"} · {s.role || "General"}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {(s.interview_type && `${s.interview_type} · `) || ""}
                      {s.total_questions != null ? `${s.total_questions} questions` : ""}
                      {s.total_questions != null && s.answer_count != null ? " · " : ""}
                      {s.answer_count != null ? `${s.answer_count} answered` : ""}
                    </div>
                    <div className="text-xs text-slate-500 mt-1 font-mono">{s.session_id}</div>
                    <div className="text-xs text-slate-400 mt-1">{s.created_at}</div>
                  </div>
                  <div className="text-right text-sm">
                    {typeof s.final_score === "number" && (
                      <div className="text-accent font-semibold">Final score: {s.final_score}</div>
                    )}
                    <div className="text-xs text-slate-500 mt-1">View details →</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (step === "historyDetail" && historyDetailLoading) {
    return (
      <div className="min-h-screen bg-surface-900 flex items-center justify-center px-4">
        <p className="text-slate-400">Loading session…</p>
      </div>
    );
  }

  if (step === "historyDetail" && historyDetail) {
    const fb = historyDetail.feedback;
    const improved = fb && (fb.improved_sample_answers || fb.per_answer_coaching);
    return (
      <div className="min-h-screen bg-surface-900 px-4 py-10">
        <div className="max-w-4xl mx-auto space-y-6">
          <header className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white">Interview detail</h1>
              <p className="text-slate-400 text-sm">
                {historyDetail.interview_type || "—"} · {historyDetail.created_at}
              </p>
            </div>
            <div className="flex gap-4">
              <button
                type="button"
                className="text-sm text-accent hover:underline"
                onClick={() => {
                  setHistoryDetail(null);
                  setStep("history");
                }}
              >
                ← Back to list
              </button>
              <button
                type="button"
                className="text-sm text-slate-400 hover:underline"
                onClick={() => {
                  setHistoryDetail(null);
                  setStep("upload");
                }}
              >
                Setup
              </button>
            </div>
          </header>

          <Section label="Session" title={`${historyDetail.company || "—"} · ${historyDetail.role || "General"}`}>
            <div className="text-sm text-slate-300 space-y-1">
              <p>
                <span className="text-slate-500">Session:</span>{" "}
                <span className="font-mono text-xs">{historyDetail.session_id}</span>
              </p>
              <p>
                <span className="text-slate-500">Questions:</span> {historyDetail.total_questions ?? "—"}
              </p>
              {fb && typeof fb.interview_confidence_score === "number" && (
                <p>
                  <span className="text-slate-500">Final score:</span>{" "}
                  <span className="text-accent font-semibold">{fb.interview_confidence_score}</span>/100
                </p>
              )}
            </div>
          </Section>

          <Section label="Q&A" title="Questions and your answers">
            <div className="space-y-6">
              {(historyDetail.answers || []).map((a, idx) => (
                <div key={`${a.question_index}-${idx}`} className="rounded-xl border border-slate-700 bg-surface-900/40 p-4 space-y-3">
                  <p className="text-xs text-slate-500">Question {typeof a.question_index === "number" ? a.question_index + 1 : idx + 1}</p>
                  <p className="text-white text-sm font-medium">{a.question}</p>
                  <div>
                    <p className="text-xs uppercase text-slate-500 mb-1">Transcript</p>
                    <pre className="text-xs whitespace-pre-wrap text-slate-300 bg-surface-900 rounded-lg p-3 border border-slate-700 max-h-40 overflow-auto">
                      {a.transcript || "—"}
                    </pre>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                    <div>
                      <div className="text-slate-500 text-xs">Voice score</div>
                      <div className="text-white font-semibold">{a.voice_score ?? "—"}</div>
                    </div>
                    <div>
                      <div className="text-slate-500 text-xs">Facial score</div>
                      <div className="text-white font-semibold">{a.facial_score ?? "—"}</div>
                    </div>
                    <div>
                      <div className="text-slate-500 text-xs">Relevance</div>
                      <div className="text-white font-semibold">{a.answer_relevance_score ?? "—"}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {fb && (
            <>
              <div className="grid md:grid-cols-2 gap-4">
                <Section label="Strengths" title="What went well">
                  <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
                    {(fb.strengths || []).map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </Section>
                <Section label="Weaknesses" title="Growth areas">
                  <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
                    {(fb.weaknesses || []).map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </Section>
              </div>
              <Section label="Suggestions" title="Recommendations">
                <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
                  {(fb.suggestions || []).map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              </Section>
            </>
          )}

          {improved && improved.length > 0 && (
            <Section label="Expected Answers" title="Question-wise expected answers">
              <div className="space-y-4">
                {improved.map((c, i) => (
                  <div key={i} className="rounded-xl border border-slate-700 bg-surface-900/40 p-4">
                    <p className="text-xs text-slate-500 font-mono mb-1">Q{i + 1}</p>
                    <p className="text-sm text-white font-medium mb-2">{c.question}</p>
                    <p className="text-sm text-slate-300 mb-2">{c.feedback_text}</p>
                    <pre className="text-xs whitespace-pre-wrap text-slate-300 bg-surface-900 rounded-lg p-3 border border-slate-700">
                      {c.star_sample_answer}
                    </pre>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {!fb && (
            <p className="text-sm text-slate-500">
              No final feedback stored for this session (interview may not have been completed).
            </p>
          )}
        </div>
      </div>
    );
  }

  if (step === "interview") {
    const q = questions[currentIndex];
    const qText = sanitizeQuestionText(typeof q === "string" ? q : q?.text);
    const qCat = typeof q === "object" && q?.category ? q.category : "";
    const total = questions.length || 1;
    const current = Math.min(currentIndex + 1, total);
    const pct = Math.round((current / total) * 100);
    return (
      <div className="min-h-screen bg-surface-900 px-3 sm:px-4 py-6 sm:py-8">
        <div className="max-w-5xl mx-auto space-y-6">
          <header>
            <h1 className="text-2xl font-bold text-white">Mock interview</h1>
            <p className="text-slate-400 text-sm">
              Answer naturally. Detailed metrics and coaching appear after you finish all questions.
            </p>
          </header>

          <Section label="Progress" title={`Question ${current} of ${total}`}>
            <div className="flex items-center gap-3 mb-2">
              <span className="text-sm text-slate-400">{pct}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
              <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
          </Section>

          {q && (
            <>
              <Section label={qCat ? qCat.toUpperCase() : "Question"} title="Read and answer">
                <p className="text-white text-lg leading-relaxed mb-4">{qText}</p>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-sm text-accent hover:underline transition"
                  onClick={() => speakQuestion(qText)}
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 5 6 9H3v6h3l5 4V5Z" />
                    <path d="M15.5 8.5a5 5 0 0 1 0 7" />
                    <path d="M18.5 6a9 9 0 0 1 0 12" />
                  </svg>
                  Read aloud
                </button>
              </Section>

              <Section label="Recording" title="Webcam + microphone">
                <div className="grid lg:grid-cols-[1fr_240px] gap-6">
                  <Recorder
                    onComplete={handleAnswerComplete}
                    disabled={loading}
                    maxDurationSeconds={QUESTION_TIME_LIMIT_SECONDS}
                    onRealtimeUpdate={handleRealtimeUpdate}
                    onRecordingChange={handleRecordingChange}
                  />
                  <div className="space-y-3">
                    <div className="rounded-xl border border-slate-700 bg-surface-900/40 p-3">
                      <p className="text-xs text-slate-400">Live confidence</p>
                      <p className="text-2xl font-bold text-white mt-1">
                        {typeof liveScore === "number" ? `${liveScore}/100` : "—"}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        {liveAnalyzing ? "Analyzing..." : liveIndicator || "Waiting for signal"}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-slate-600 text-slate-200 text-sm hover:bg-slate-800 transition-all duration-200 hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-accent/60"
                      onClick={skipQuestion}
                      disabled={loading}
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 5v14" />
                        <path d="m19 12-8-6v12l8-6Z" />
                      </svg>
                      Skip question
                    </button>
                  </div>
                </div>
                {loading && (
                  <p className="text-sm text-slate-400 mt-3">
                    Processing audio… This can take up to a minute on the first answer while the server loads AI models.
                  </p>
                )}
                {error && <p className="text-sm text-rose-400 mt-3">{error}</p>}
                <p className="text-xs text-slate-500 mt-3">
                  Timer: {QUESTION_TIME_LIMIT_SECONDS}s max · Frames captured every 2s · Live score updates every 3s
                </p>
              </Section>

            </>
          )}
        </div>
      </div>
    );
  }

  if (step === "results" && feedback) {
    const perQuestion = feedback.per_question_breakdown || [];
    const coachingBlocks = feedback.improved_sample_answers || feedback.per_answer_coaching || [];
    const coachingByQuestion = new Map(
      coachingBlocks.map((c) => [String(c.question || "").trim(), c])
    );
    const safeFindCoaching = (qText) => coachingByQuestion.get(String(qText || "").trim()) || null;

    return (
      <div className="min-h-screen bg-surface-900 px-3 py-6 sm:px-4 sm:py-10">
        <div className="max-w-5xl mx-auto space-y-6">
          <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-white">Interview results</h1>
              <p className="text-slate-400 text-sm">
                Per-question scores and improved sample answers. Open the dashboard after review.
              </p>
            </div>
            <div className="flex flex-wrap gap-4">
              <button
                type="button"
                className="text-sm text-slate-400 hover:underline"
                onClick={() => {
                  setStep("upload");
                  setFeedback(null);
                  setQuestions([]);
                  setPerAnswerResults([]);
                }}
              >
                New interview
              </button>
              <button
                type="button"
                className="text-sm text-accent hover:underline"
                onClick={() => setStep("feedback")}
              >
                View final dashboard →
              </button>
            </div>
          </header>

          <Section label="Review" title="Scores & accurate answers (per question)">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              {metricTile("Overall", `${feedback.interview_confidence_score ?? 0}/100`, "overall")}
              {metricTile("Content", `${feedback.performance_matrix?.content_score ?? 0}/100`, "content")}
              {metricTile("Voice", `${feedback.performance_matrix?.voice_score ?? 0}/100`, "voice")}
              {metricTile("Pacing", `${feedback.performance_matrix?.pacing_score ?? 0}/100`, "pacing")}
            </div>
            <div className="space-y-5">
              {questions.map((q, idx) => {
                const qText = typeof q === "string" ? q : q?.text;
                const stored = perAnswerResults[idx] || {};
                const row = perQuestion.find((x) => Number(x.question_index) === idx + 1) || null;
                const coaching = coachingBlocks[idx] || safeFindCoaching(qText);
                return (
                  <div
                    key={`${idx}-${qText}`}
                    className="rounded-2xl border border-slate-700 bg-surface-800/40 p-5 space-y-4 hover:border-slate-500 transition"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs text-slate-500">Question {idx + 1}</p>
                        <p className="text-white font-medium leading-relaxed">{qText}</p>
                      </div>
                      {row && (
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-center text-sm w-full lg:w-auto">
                          <div>
                            <div className="text-slate-500 text-xs">Answer</div>
                            <div className="text-white font-semibold">{row.answer_score ?? "—"}</div>
                          <div className="text-[10px] text-slate-500 mt-1">
                            {describeScore(row.answer_score, "answer")}
                          </div>
                          </div>
                          <div>
                            <div className="text-slate-500 text-xs">Voice</div>
                            <div className="text-white font-semibold">{row.voice_score ?? "—"}</div>
                          <div className="text-[10px] text-slate-500 mt-1">
                            {describeScore(row.voice_score, "voice")}
                          </div>
                          </div>
                          <div>
                            <div className="text-slate-500 text-xs">Face</div>
                            <div className="text-white font-semibold">{row.facial_score ?? "—"}</div>
                          <div className="text-[10px] text-slate-500 mt-1">
                            {describeScore(row.facial_score, "facial")}
                          </div>
                          </div>
                          <div>
                            <div className="text-slate-500 text-xs">Pacing</div>
                            <div className="text-white font-semibold">{row.time_score ?? "—"}</div>
                          <div className="text-[10px] text-slate-500 mt-1">
                            {describeScore(row.time_score, "pacing")}
                          </div>
                          </div>
                        </div>
                      )}
                    </div>

                    <div>
                      <div className="text-xs uppercase tracking-wider text-slate-500 mb-2 font-semibold">
                        Your transcript
                      </div>
                      <pre className="text-xs whitespace-pre-wrap text-slate-300 bg-surface-900 rounded-lg p-3 border border-slate-700 max-h-48 overflow-auto leading-relaxed">
                        {stored.transcript || "—"}
                      </pre>
                    </div>

                    {coaching?.star_sample_answer && (
                      <div>
                        <div className="text-xs uppercase tracking-wider text-slate-500 mb-2 font-semibold">
                          Expected answer
                        </div>
                        <pre className="text-xs whitespace-pre-wrap text-slate-200 bg-surface-900 rounded-lg p-3 border border-slate-700 overflow-x-auto leading-relaxed">
                          {coaching.star_sample_answer}
                        </pre>
                        {coaching.feedback_text ? (
                          <p className="text-xs text-slate-400 mt-2">{coaching.feedback_text}</p>
                        ) : null}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Section>
        </div>
      </div>
    );
  }

  if (step === "feedback" && feedback) {
    const confScore = feedback.interview_confidence_score ?? 0;
    const fusion = feedback.fusion_breakdown || {};
    const voiceMetrics = feedback.voice_analysis?.metrics || {};
    const perQuestionData = feedback.per_question_breakdown || [];
    const coachingBlocks = feedback.improved_sample_answers || feedback.per_answer_coaching || [];

    return (
      <div className="min-h-screen bg-surface-900 px-3 py-6 sm:px-4 sm:py-10">
        <div className="max-w-4xl mx-auto space-y-6">
          <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-white">Final feedback</h1>
              <p className="text-slate-400 text-sm">Multimodal fusion and actionable next steps.</p>
            </div>
            <button
              type="button"
              className="text-sm text-accent hover:underline"
              onClick={() => {
                setStep("upload");
                setFeedback(null);
                setQuestions([]);
              }}
            >
              New interview
            </button>
          </header>

          <Section label="Score" title="Interview confidence">
            <div className="flex flex-wrap items-end gap-3 mb-2">
              <div className="text-4xl sm:text-5xl font-bold text-white">{confScore}/100</div>
              <span className={`text-xs px-2.5 py-1 rounded-full ${scoreChipClass(confScore)}`}>
                {describeScore(confScore, "overall")}
              </span>
            </div>
            <div className="h-3 rounded-full bg-slate-700 overflow-hidden mb-3">
              <div className="h-full bg-accent" style={{ width: `${confScore}%` }} />
            </div>
            <p className="text-sm text-slate-400">
              Fusion: voice {fusion.voice_confidence_contribution?.toFixed?.(1) ?? "—"} · facial{" "}
              {fusion.facial_confidence_contribution?.toFixed?.(1) ?? "—"} · answer{" "}
              {fusion.answer_relevance_contribution?.toFixed?.(1) ?? "—"}
            </p>
          </Section>

          <Section label="Performance matrix" title="Skill-wise score view">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[
                ["Content", feedback.performance_matrix?.content_score],
                ["Voice", feedback.performance_matrix?.voice_score],
                ["Facial", feedback.performance_matrix?.facial_score],
                ["Pacing", feedback.performance_matrix?.pacing_score],
                ["Clarity", feedback.performance_matrix?.clarity_rate],
                ["Resume fit", feedback.performance_matrix?.resume_alignment_score],
              ].map(([label, val]) => (
                <div key={label} className="rounded-xl border border-slate-700 bg-surface-900/40 p-3 hover:border-slate-500 transition">
                  <div className="text-xs text-slate-400">{label}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-lg font-semibold text-white">{typeof val === "number" ? `${val}/100` : "—"}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full ${scoreChipClass(val)}`}>
                      {typeof val === "number" ? describeScore(val).split(".")[0] : "N/A"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            {feedback.performance_matrix?.trend && (
              <p className="text-xs text-slate-400 mt-3">
                Trend across questions: <span className="text-slate-200 font-medium">{feedback.performance_matrix.trend}</span>
              </p>
            )}
          </Section>

          <div className="grid md:grid-cols-2 gap-4">
            <Section label="Strengths" title="What went well">
              <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
                {(feedback.strengths || []).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </Section>
            <Section label="Growth areas" title="What to improve">
              <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
                {(feedback.weaknesses || []).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Section>
          </div>

          <Section label="Delivery" title="Voice summary">
            <p className="text-sm text-slate-300">{feedback.voice_analysis?.overall}</p>
            {voiceMetrics.avg_nervous_score != null && (
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
                {metricTile("Nervousness", `${voiceMetrics.avg_nervous_score}/100`, "voice")}
                {metricTile("Silence ratio", `${voiceMetrics.avg_silence_ratio ?? "—"}`, "pauses")}
                {metricTile("Pitch mean", `${voiceMetrics.avg_pitch_mean_hz ?? "—"} Hz`, "pitch")}
                {metricTile("Trend", `${voiceMetrics.nervous_trend ?? "stable"}`, "trend")}
              </div>
            )}
          </Section>

          {feedback.facial_analysis?.overall && (
            <Section label="Presence" title="Facial summary">
              <p className="text-sm text-slate-300">{feedback.facial_analysis.overall}</p>
            </Section>
          )}

          <Section label="Content" title="Answer analysis">
            <p className="text-sm text-slate-300">{feedback.answer_analysis?.overall}</p>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
              {metricTile("Relevance", `${feedback.answer_analysis?.metrics?.avg_relevance_score ?? 0}/100`, "content")}
              {metricTile("Avg words", `${feedback.answer_analysis?.metrics?.avg_word_count ?? 0}`, "length")}
              {metricTile("Clarity", `${feedback.performance_matrix?.clarity_rate ?? 0}/100`, "clarity")}
              {metricTile("Pacing", `${feedback.answer_analysis?.metrics?.avg_time_score ?? 0}/100`, "timing")}
            </div>
          </Section>

          <Section label="Suggestions" title="Next actions">
            <ul className="list-disc list-inside text-sm text-slate-200 space-y-1">
              {(feedback.suggestions || []).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </Section>

          {coachingBlocks.length > 0 && (
            <Section label="Expected Answers" title="Question-wise expected answers">
              <div className="space-y-4">
                {coachingBlocks.map((c, i) => (
                  <div key={i} className="rounded-xl border border-slate-700 bg-surface-900/40 p-4">
                    <p className="text-xs text-slate-500 font-mono mb-1">Q{i + 1}</p>
                    <p className="text-sm text-white font-medium mb-2">{c.question}</p>
                    <p className="text-sm text-slate-300 mb-2">{c.feedback_text}</p>
                    <pre className="text-xs whitespace-pre-wrap text-slate-300 bg-surface-900 rounded-lg p-3 border border-slate-700 overflow-x-auto">
                      {c.star_sample_answer}
                    </pre>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {!!perQuestionData.length && (
            <Section label="Trend" title="Per-question scores">
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={perQuestionData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="question_index" stroke="#94a3b8" />
                    <YAxis domain={[0, 100]} stroke="#94a3b8" />
                    <Tooltip contentStyle={{ background: "#111827", border: "1px solid #334155" }} />
                    <Legend />
                    <Line type="monotone" dataKey="answer_score" stroke="#38bdf8" name="Answer" />
                    <Line type="monotone" dataKey="voice_score" stroke="#34d399" name="Voice" />
                    <Line type="monotone" dataKey="facial_score" stroke="#f59e0b" name="Face" />
                    <Line type="monotone" dataKey="time_score" stroke="#f472b6" name="Pacing" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Section>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-900 flex items-center justify-center px-4">
      <p className="text-slate-400">Loading…</p>
    </div>
  );
}
