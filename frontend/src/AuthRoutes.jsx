import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Link, Route, Routes, useNavigate } from "react-router-dom";
import App from "./App";
import { getLastLoginEmail, loginUser, logoutUser, registerUser } from "./api";

const AUTH_KEY = "ai_interviewer_auth_user";
const THEME_KEY = "ai_interviewer_theme";

function authCard(title, subtitle, children) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-surface-900 via-surface-900 to-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-surface-800/70 p-6 shadow-2xl">
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        <p className="text-sm text-slate-400 mt-1 mb-6">{subtitle}</p>
        {children}
      </div>
    </div>
  );
}

function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    getLastLoginEmail()
      .then((value) => {
        if (alive && value) setEmail(value);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await loginUser({ email: email.trim().toLowerCase(), password });
      localStorage.setItem(AUTH_KEY, data?.user?.email || email.trim().toLowerCase());
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.error || "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  return authCard(
    "Login",
    "Access your interview workspace.",
    <form onSubmit={handleLogin} className="space-y-4">
      <div>
        <label className="text-sm text-slate-300 block mb-1">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
          placeholder="you@example.com"
        />
      </div>
      <div>
        <label className="text-sm text-slate-300 block mb-1">Password</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
          placeholder="********"
        />
      </div>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="w-full py-2.5 rounded-lg bg-accent hover:bg-accent-dim text-surface-900 font-semibold text-sm"
      >
        {loading ? "Logging in..." : "Login"}
      </button>
      <p className="text-sm text-slate-400">
        New here?{" "}
        <Link className="text-accent hover:underline" to="/sign-in">
          Create account
        </Link>
      </p>
    </form>
  );
}

function SignInPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSignIn = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const trimmedEmail = email.trim().toLowerCase();
    try {
      const data = await registerUser({ name: name.trim(), email: trimmedEmail, password });
      localStorage.setItem(AUTH_KEY, data?.user?.email || trimmedEmail);
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.error || "Could not create account.");
    } finally {
      setLoading(false);
    }
  };

  return authCard(
    "Sign In",
    "Create an account to start mock interviews.",
    <form onSubmit={handleSignIn} className="space-y-4">
      <div>
        <label className="text-sm text-slate-300 block mb-1">Full name</label>
        <input
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
          placeholder="Your name"
        />
      </div>
      <div>
        <label className="text-sm text-slate-300 block mb-1">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
          placeholder="you@example.com"
        />
      </div>
      <div>
        <label className="text-sm text-slate-300 block mb-1">Password</label>
        <input
          type="password"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg bg-surface-900 border border-slate-600 px-3 py-2 text-sm text-white"
          placeholder="Minimum 6 characters"
        />
      </div>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="w-full py-2.5 rounded-lg bg-accent hover:bg-accent-dim text-surface-900 font-semibold text-sm"
      >
        {loading ? "Creating..." : "Create account"}
      </button>
      <p className="text-sm text-slate-400">
        Already registered?{" "}
        <Link className="text-accent hover:underline" to="/login">
          Go to login
        </Link>
      </p>
    </form>
  );
}

function ProtectedRoute({ children }) {
  const loggedIn = !!localStorage.getItem(AUTH_KEY);
  return loggedIn ? children : <Navigate to="/login" replace />;
}

function InterviewWorkspace({ theme, setTheme }) {
  const navigate = useNavigate();
  const userEmail = useMemo(() => localStorage.getItem(AUTH_KEY) || "User", []);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const onDocClick = (event) => {
      if (!menuRef.current) return;
      if (!menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div className="relative">
      <div ref={menuRef} className="absolute top-4 right-4 z-50">
        <button
          type="button"
          className="inline-flex items-center justify-center rounded-full border border-slate-600 bg-surface-800/95 p-2.5 text-slate-200 shadow-lg transition hover:bg-slate-800 hover:text-white"
          title="Menu"
          aria-label="Open menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 7h16" />
            <path d="M4 12h16" />
            <path d="M4 17h16" />
          </svg>
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-full mt-2 w-64 rounded-2xl border border-slate-600 bg-surface-800/95 p-2 shadow-2xl backdrop-blur-sm">
            <div className="rounded-xl border border-slate-600/70 bg-surface-900/40 px-3 py-2 mb-2">
              <p className="text-xs text-slate-400">Signed in as</p>
              <p className="text-sm text-slate-100 truncate">{userEmail}</p>
            </div>

            <button
              type="button"
              className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 transition"
              onClick={() => setTheme((prev) => (prev === "light" ? "dark" : "light"))}
            >
              {theme === "light" ? "Dark mode" : "Light mode"}
            </button>
            <button
              type="button"
              className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm text-rose-300 hover:bg-rose-500/10 transition"
              onClick={async () => {
                try {
                  await logoutUser();
                } catch {
                  // Keep logout UX robust even if API call fails.
                }
                localStorage.removeItem(AUTH_KEY);
                navigate("/login");
              }}
            >
              Logout
            </button>
          </div>
        )}
      </div>
      <App />
    </div>
  );
}

export default function AuthRoutes() {
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "dark");

  useEffect(() => {
    const nextTheme = theme === "light" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, nextTheme);
    if (typeof document !== "undefined") {
      document.body.classList.toggle("theme-light", nextTheme === "light");
    }
  }, [theme]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/sign-in" element={<SignInPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <InterviewWorkspace theme={theme} setTheme={setTheme} />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
