import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { api, clearTokens, hasToken } from "./api/client";
import type { Me } from "./api/types";
import { Wordmark } from "./components/Wordmark";
import Login from "./pages/Login";
import Measure from "./pages/Measure";
import Report from "./pages/Report";
import Review from "./pages/Review";

function Nav({ me }: { me: Me }) {
  return (
    <header className="border-b border-brand-rule bg-brand-paper sticky top-0 z-10 backdrop-blur-[1px] bg-opacity-95">
      <div className="max-w-[1360px] mx-auto px-8 h-14 flex items-center gap-8">
        <Wordmark />
        <nav className="flex items-center gap-1 ml-2 h-full">
          <NavLink to="/measure" className={({ isActive }) => `nav-link h-full ${isActive ? "active" : ""}`}>
            Measure
          </NavLink>
          <NavLink to="/review" className={({ isActive }) => `nav-link h-full ${isActive ? "active" : ""}`}>
            Review
          </NavLink>
          <NavLink to="/report" className={({ isActive }) => `nav-link h-full ${isActive ? "active" : ""}`}>
            Report
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-4 text-[12.5px]">
          <div className="text-right leading-tight">
            <div className="font-medium text-brand-ink">{me.organization?.name ?? "—"}</div>
            <div className="text-[11px] text-brand-subtle">
              {me.username} · {me.role}
            </div>
          </div>
          <button
            onClick={() => {
              clearTokens();
              window.location.href = "/";
            }}
            className="text-[11.5px] text-brand-subtle hover:text-brand-ink underline underline-offset-3 decoration-brand-rule hover:decoration-brand-ink"
          >
            sign out
          </button>
        </div>
      </div>
    </header>
  );
}

export default function App() {
  const location = useLocation();
  const [tokenPresent, setTokenPresent] = useState(hasToken());

  useEffect(() => {
    setTokenPresent(hasToken());
  }, [location.pathname]);

  const meQuery = useQuery<Me>({
    queryKey: ["me"],
    queryFn: () => api<Me>("/me/"),
    enabled: tokenPresent,
    retry: false,
  });

  if (!tokenPresent) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={() => setTokenPresent(true)} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  if (meQuery.isLoading || !meQuery.data) {
    return (
      <div className="min-h-screen grid place-items-center text-brand-subtle text-sm">
        Loading…
      </div>
    );
  }

  if (meQuery.error) {
    clearTokens();
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Nav me={meQuery.data} />
      <main className="flex-1 max-w-[1360px] mx-auto w-full px-8 py-10">
        <Routes>
          <Route path="/" element={<Navigate to="/measure" replace />} />
          <Route path="/measure" element={<Measure />} />
          <Route path="/review" element={<Review />} />
          <Route path="/report" element={<Report />} />
          <Route path="*" element={<Navigate to="/measure" replace />} />
        </Routes>
      </main>
      <footer className="border-t border-brand-rule bg-brand-paper">
        <div className="max-w-[1360px] mx-auto px-8 py-3.5 text-[11.5px] text-brand-subtle flex items-center gap-4 flex-wrap">
          <span>Prototype submission · single-container Django + React on a 512 MB droplet</span>
          <span className="text-brand-rule">·</span>
          <span>Factors: DEFRA 2024 · EPA eGRID 2022 · IEA 2023</span>
          <span className="text-brand-rule">·</span>
          <span>GHG Protocol Scope 1 / 2 / 3 Cat 6</span>
        </div>
      </footer>
    </div>
  );
}
