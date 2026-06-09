import axios from "axios";

const base = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL.replace(/\/$/, "")
  : import.meta.env.DEV
  ? "/api"
  : null;

const MAX_FACIAL_FRAMES_PER_ANSWER = 10;
const SUBMIT_TIMEOUT_MS = 180000;

function getApiBaseUrl() {
  if (!base) {
    throw new Error(
      "Missing VITE_API_BASE_URL in production. Set VITE_API_BASE_URL to your backend URL or deploy the backend with the frontend."
    );
  }
  return base;
}

const api = axios.create({
  timeout: 60000,
});

function formatApiError(error, fallback = "Request failed.") {
  if (error?.response?.data?.error) return error.response.data.error;
  if (error?.code === "ECONNABORTED" || error?.message?.toLowerCase().includes("timeout")) {
    return "Request timed out. The server may still be waking up on Render — wait a moment and try again.";
  }
  if (error?.message === "Network Error") {
    return "Network error — the backend may be waking up or still processing. Wait ~30s and try again.";
  }
  return error?.message || fallback;
}

async function postWithRetry(url, data, config = {}, retries = 1) {
  try {
    const { data: responseData } = await api.post(url, data, config);
    return responseData;
  } catch (error) {
    const isRetryable =
      retries > 0 &&
      (!error.response || error.message === "Network Error" || error.code === "ECONNABORTED");
    if (isRetryable) {
      await wakeBackend();
      return postWithRetry(url, data, config, retries - 1);
    }
    throw error;
  }
}

const SESSION_KEY = "interview_session_id";

export function getSessionId() {
  return localStorage.getItem(SESSION_KEY) || "";
}

export function setSessionId(sessionId) {
  if (sessionId) localStorage.setItem(SESSION_KEY, sessionId);
}

/** Ping Render so the service is awake before heavy audio uploads. */
export async function wakeBackend() {
  const baseUrl = getApiBaseUrl();
  const wakePaths = ["/health", "/questions"];
  for (const path of wakePaths) {
    try {
      await api.get(`${baseUrl}${path}`, { timeout: 90000 });
      return;
    } catch (error) {
      if (error?.response?.status !== 404) return;
    }
  }
}

export { formatApiError };

export async function registerUser({ name, email, password }) {
  const { data } = await api.post(`${getApiBaseUrl()}/auth/register`, { name, email, password });
  return data;
}

export async function loginUser({ email, password }) {
  const { data } = await api.post(`${getApiBaseUrl()}/auth/login`, { email, password });
  return data;
}

export async function logoutUser() {
  const { data } = await api.post(`${getApiBaseUrl()}/auth/logout`, {});
  return data;
}

export async function getLastLoginEmail() {
  const { data } = await api.get(`${getApiBaseUrl()}/auth/last-email`);
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
  await wakeBackend();
  const { data } = await api.post(`${getApiBaseUrl()}/upload_resume`, form, { timeout: 120000 });
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
  const framesToSend = facialFrames.slice(-MAX_FACIAL_FRAMES_PER_ANSWER);
  for (let i = 0; i < framesToSend.length; i++) {
    if (framesToSend[i] instanceof Blob) {
      form.append("facial_frames", framesToSend[i], `frame_${i}.jpg`);
    }
  }
  await wakeBackend();
  return postWithRetry(`${getApiBaseUrl()}/submit_answer`, form, { timeout: SUBMIT_TIMEOUT_MS });
}

export async function endInterview() {
  const sessionId = getSessionId();
  const payload = sessionId ? { session_id: sessionId } : {};
  const { data } = await api.post(`${getApiBaseUrl()}/end_interview`, payload, { timeout: 120000 });
  return data;
}

export async function getFeedback() {
  const sessionId = getSessionId();
  const { data } = await api.get(`${getApiBaseUrl()}/feedback`, {
    params: sessionId ? { session_id: sessionId } : {},
  });
  return data;
}

export async function getQuestions() {
  const sessionId = getSessionId();
  const { data } = await api.get(`${getApiBaseUrl()}/questions`, {
    params: sessionId ? { session_id: sessionId } : {},
  });
  return data;
}

/** Recent sessions stored in SQLite (past interviews). */
export async function listSessions(limit = 30) {
  const { data } = await api.get(`${getApiBaseUrl()}/history`, { params: { limit } });
  return data;
}

/** Full session detail for history drill-down. */
export async function getHistorySession(sessionId) {
  const { data } = await api.get(`${getApiBaseUrl()}/history/${encodeURIComponent(sessionId)}`);
  return data;
}

export async function analyzeFacial(imageBlob) {
  const form = new FormData();
  form.append("image", imageBlob, "frame.jpg");
  const { data } = await api.post(`${getApiBaseUrl()}/analyze_facial`, form);
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
  if (frame) form.append("frame", frame, "frame.jpg");
  const { data } = await api.post(`${getApiBaseUrl()}/realtime_analysis`, form, { timeout: 15000 });
  return data;
}
