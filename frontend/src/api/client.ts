const API_BASE = "/api";

let accessToken: string | null = localStorage.getItem("accessToken");
let refreshToken: string | null = localStorage.getItem("refreshToken");

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  localStorage.setItem("accessToken", access);
  localStorage.setItem("refreshToken", refresh);
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem("accessToken");
  localStorage.removeItem("refreshToken");
}

export function hasToken() {
  return Boolean(accessToken);
}

async function refresh(): Promise<boolean> {
  if (!refreshToken) return false;
  const r = await fetch(`${API_BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: refreshToken }),
  });
  if (!r.ok) return false;
  const j = await r.json();
  accessToken = j.access;
  localStorage.setItem("accessToken", j.access);
  return true;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (resp.status === 401 && refreshToken) {
    const ok = await refresh();
    if (ok) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
    }
  }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as unknown as T;
  const ct = resp.headers.get("Content-Type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp.text() as unknown as T;
}

export async function login(username: string, password: string) {
  const r = await fetch(`${API_BASE}/auth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error("Invalid credentials");
  const j = await r.json();
  setTokens(j.access, j.refresh);
  return j;
}
