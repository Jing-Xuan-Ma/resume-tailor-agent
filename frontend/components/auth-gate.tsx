"use client";

import { useEffect, useState } from "react";
import { getCurrentUser, loginUser, registerUser } from "@/lib/api";

export interface CurrentUser {
  id: string;
  email: string;
  full_name?: string;
}

interface StoredAuth {
  token: string;
  user: CurrentUser;
}

interface AuthGateProps {
  children: (props: { user: CurrentUser; token: string; onLogout: () => void }) => React.ReactNode;
}

const STORAGE_KEY = "resume-agent-auth";
const DEMO_EMAIL = "demo@resume-agent.local";
const DEMO_PASSWORD = "demo-pass-1234";
const DEMO_NAME = "Demo User";

function normalizeUser(value: Record<string, unknown>): CurrentUser {
  return {
    id: String(value.id || ""),
    email: String(value.email || ""),
    full_name: value.full_name ? String(value.full_name) : undefined,
  };
}

function readStoredAuth(): StoredAuth | undefined {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as StoredAuth;
    if (parsed.token && parsed.user?.id) return parsed;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  return undefined;
}

export default function AuthGate({ children }: AuthGateProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [auth, setAuth] = useState<StoredAuth | undefined>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | undefined>();

  useEffect(() => {
    const stored = readStoredAuth();
    if (!stored) {
      setLoading(false);
      return;
    }
    getCurrentUser(stored.token)
      .then((result) => {
        const user = normalizeUser(result.user);
        const next = { token: stored.token, user };
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        setAuth(next);
      })
      .catch(() => {
        window.localStorage.removeItem(STORAGE_KEY);
      })
      .finally(() => setLoading(false));
  }, []);

  const persist = (result: { access_token: string; user: Record<string, unknown> }) => {
    const next = {
      token: result.access_token,
      user: normalizeUser(result.user),
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setAuth(next);
    setPassword("");
  };

  const handleSubmit = async () => {
    if (!email.trim() || !password || submitting) return;
    if (mode === "register" && !fullName.trim()) return;
    setSubmitting(true);
    setMessage(undefined);
    try {
      const result =
        mode === "login"
          ? await loginUser(email.trim(), password)
          : await registerUser(email.trim(), fullName.trim(), password);
      persist(result);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDemo = async () => {
    if (submitting) return;
    setSubmitting(true);
    setMessage(undefined);
    try {
      try {
        persist(await loginUser(DEMO_EMAIL, DEMO_PASSWORD));
      } catch {
        persist(await registerUser(DEMO_EMAIL, DEMO_NAME, DEMO_PASSWORD));
      }
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Demo sign-in failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setAuth(undefined);
    setMessage(undefined);
  };

  if (loading) {
    return (
      <main className="flex h-screen items-center justify-center bg-[#eef2f7] text-slate-950">
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-5 text-sm font-semibold text-slate-600 shadow-sm">
          Loading workspace…
        </div>
      </main>
    );
  }

  if (auth?.user.id) return <>{children({ user: auth.user, token: auth.token, onLogout: handleLogout })}</>;

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top_left,#d1fae5,transparent_36%),#f4f6f4] px-4 text-slate-950"
      data-testid="auth-gate"
    >
      <section className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.12)] md:grid-cols-[1.1fr_0.9fr]">
        <div className="bg-slate-950 p-8 text-white md:p-10">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-emerald-300">Resume Agent</p>
          <h1 className="mt-6 max-w-md text-3xl font-black tracking-tight md:text-4xl">
            Ranked jobs → tailor → confirm → apply safely.
          </h1>
          <p className="mt-4 max-w-md text-sm leading-6 text-slate-300">
            JobRight-style flow: pick a ranked role, see keyword match, rewrite on a locked template, then apply with a pause before submit.
          </p>
          <ol className="mt-8 grid gap-3 text-sm text-slate-200">
            <li className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">1. Browse ranked jobs by match score</li>
            <li className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">2. Tailor resume content only (no format rebuild)</li>
            <li className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">3. Confirm, then manual or auto-apply (stops before Submit)</li>
          </ol>
          <a
            href="/jobs"
            className="mt-6 inline-flex text-sm font-semibold text-emerald-300 hover:text-emerald-200"
            data-testid="auth-skip-to-jobs"
          >
            Skip login — browse ranked jobs →
          </a>
        </div>

        <div className="p-8 md:p-10">
          <div className="mb-6 flex gap-1 rounded-full bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => setMode("login")}
              className={`flex-1 rounded-full px-4 py-2 text-sm font-bold ${mode === "login" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              className={`flex-1 rounded-full px-4 py-2 text-sm font-bold ${mode === "register" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Register
            </button>
          </div>

          <div className="space-y-3">
            {mode === "register" && (
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Full name"
                className="h-12 w-full rounded-2xl border border-slate-200 px-4 text-sm outline-none focus:ring-2 focus:ring-emerald-500"
              />
            )}
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Email"
              type="email"
              className="h-12 w-full rounded-2xl border border-slate-200 px-4 text-sm outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && handleSubmit()}
              placeholder="Password"
              type="password"
              className="h-12 w-full rounded-2xl border border-slate-200 px-4 text-sm outline-none focus:ring-2 focus:ring-emerald-500"
            />
            {message && <p className="rounded-2xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">{message}</p>}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting || !email.trim() || !password || (mode === "register" && !fullName.trim())}
              className="h-12 w-full rounded-2xl bg-emerald-600 text-sm font-bold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
            >
              {submitting ? "Working…" : mode === "login" ? "Login" : "Create account"}
            </button>
            <button
              type="button"
              data-testid="auth-demo"
              onClick={handleDemo}
              disabled={submitting}
              className="h-12 w-full rounded-2xl border border-emerald-200 bg-emerald-50 text-sm font-bold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
            >
              Continue as demo (fastest)
            </button>
            <p className="text-center text-[11px] text-slate-400">Demo keeps data local to this browser session.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
