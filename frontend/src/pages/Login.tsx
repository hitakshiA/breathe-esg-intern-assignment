import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { login } from "../api/client";
import { Wordmark } from "../components/Wordmark";

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState("analyst");
  const [password, setPassword] = useState("breathe2024");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await login(username, password);
      onLoggedIn();
      navigate("/measure");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-brand-paper">
      <header className="px-8 py-5">
        <Wordmark size="md" />
      </header>
      <main className="flex-1 grid place-items-center px-6 py-10">
        <div className="w-full max-w-[560px]">
          <div className="mb-10">
            <div className="eyebrow mb-3">Analyst review · prototype</div>
            <h1 className="lede font-display">
              Sign in to <span className="text-brand-green-700">approve emissions data</span>{" "}
              before it goes to auditors.
            </h1>
            <p className="mt-4 max-w-[40ch] text-brand-mid text-[15px] leading-relaxed">
              This is a hiring-assignment prototype. The demo tenant is pre-seeded with three
              ingested batches across SAP fuel, US utility electricity, and Concur travel.
            </p>
          </div>

          <form onSubmit={submit} className="surface p-7 space-y-5">
            <div className="flex items-baseline justify-between">
              <h2 className="font-display text-[18px] font-semibold">Sign in</h2>
              <span className="meta">demo credentials are pre-filled</span>
            </div>
            <label className="block">
              <span className="eyebrow">Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input mt-1.5"
                autoComplete="username"
              />
            </label>
            <label className="block">
              <span className="eyebrow">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input mt-1.5"
                autoComplete="current-password"
              />
            </label>
            {err && (
              <div className="text-[13px] text-red-800 bg-red-50 border border-red-100 rounded px-3 py-2">
                {err}
              </div>
            )}
            <button className="btn-primary w-full" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in to the workspace"}
            </button>
          </form>

          <div className="mt-8 grid grid-cols-3 gap-4 text-[12px] text-brand-mid">
            <div>
              <div className="eyebrow text-brand-subtle mb-1">Backend</div>
              Django REST · SQLite · gunicorn
            </div>
            <div>
              <div className="eyebrow text-brand-subtle mb-1">Frontend</div>
              React + TypeScript · Tailwind
            </div>
            <div>
              <div className="eyebrow text-brand-subtle mb-1">Deploy</div>
              One container · 512 MB droplet
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
