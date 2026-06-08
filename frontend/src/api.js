import axios from "axios";

const base = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL.replace(/\/$/, "")}/api`
  : "/api";
const SESSION_KEY = "interview_session_id";

export function getSessionId() {
  return localStorage.getItem(SESSION_KEY) || "";
}

export function setSessionId(sessionId) {
  if (sessionId) localStorage.setItem(SESSION_KEY, sessionId);
}

export async function registerUser({ name, email, password }) {
  const { data } = await axios.post(`${base}/auth/register`, { name, email, password });
  return data;
}

export async function loginUser({ email, password }) {
  const { data } = await axios.post(`${base}/auth/login`, { email, password });
  return data;
}

export async function logoutUser() {
  const { data } = await axios.post(`${base}/auth/logout`, {});
  return data;
}

export async function getLastLoginEmail() {
  const { data } = await axios.get(`${base}/auth/last-email`);
  return data?.email || "";
}

/**
 * Upload resume PDF and optional role / company / job description for tailored questions.
 */
export async function uploadResume(file, meta = {}) {
  const form = new FormData();
  form.append("resume", file);
  form.append("file", file);
  if (meta.role) form.append("role", meta.role);
  if (meta.company) form.append("company", meta.company);
  if (meta.jobDescription) form.append("job_description", meta.jobDescription);
  if (meta.interviewType) form.append("interview_type", meta.interviewType);
  const { data } = await axios.post(`${base}/upload_resume`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  if (data?.session_id) setSessionId(data.session_id);
  return data;
}

export async function submitAnswer(audioBlob, questionText, facialFrames = [], meta = {}) {
  const form = new FormData();
  const audioName = audioBlob instanceof File ? audioBlob.name : "answer.webm";
  const sessionId = getSessionId();
  form.append("audio", audioBlob, audioName);
  form.append("file", audioBlob, audioName);
  form.append("question", questionText);
  form.append("question_text", questionText);
  if (sessionId) form.append("session_id", sessionId);
  if (typeof meta.questionIndex === "number") form.append("question_index", String(meta.questionIndex));
  if (typeof meta.timeTaken === "number") form.append("time_taken", String(meta.timeTaken));
  for (let i = 0; i < facialFrames.length; i++) {
    if (facialFrames[i] instanceof Blob) {
      form.append("facial_frames", facialFrames[i], `frame_${i}.jpg`);
    }
  }
  const { data } = await axios.post(`${base}/submit_answer`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function endInterview() {
  const sessionId = getSessionId();
  const payload = sessionId ? { session_id: sessionId } : {};
  const { data } = await axios.post(`${base}/end_interview`, payload);
  return data;
}

export async function getFeedback() {
  const sessionId = getSessionId();
  const { data } = await axios.get(`${base}/feedback`, {
    params: sessionId ? { session_id: sessionId } : {},
  });
  return data;
}

export async function getQuestions() {
  const sessionId = getSessionId();
  const { data } = await axios.get(`${base}/questions`, {
    params: sessionId ? { session_id: sessionId } : {},
  });
  return data;
}

/** Recent sessions stored in SQLite (past interviews). */
export async function listSessions(limit = 30) {
  const { data } = await axios.get(`${base}/history`, { params: { limit } });
  return data;
}

/** Full session detail for history drill-down. */
export async function getHistorySession(sessionId) {
  const { data } = await axios.get(`${base}/history/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function analyzeFacial(imageBlob) {
  const form = new FormData();
  form.append("image", imageBlob, "frame.jpg");
  const { data } = await axios.post(`${base}/analyze_facial`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/**
 * Live multimodal confidence: sends optional audio chunk + frame; includes session_id
 * so the server can blend in the last answer relevance (40% weight).
 */
export async function realtimeAnalysis(audioChunk, frame) {
  const form = new FormData();
  const sessionId = getSessionId();
  if (sessionId) form.append("session_id", sessionId);
  if (audioChunk) form.append("audio_chunk", audioChunk, "chunk.webm");
  if (frame) form.append("frame", frame, "frame.jpg");
  const { data } = await axios.post(`${base}/realtime_analysis`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
