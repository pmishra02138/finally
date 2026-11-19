import type {
  ChatHistoryResponse,
  ChatMessageResponse,
  HealthResponse,
  PortfolioResponse,
  PortfolioSnapshotResponse,
  TradeRequest,
  TradeResponse,
  WatchlistItemResponse,
  WatchlistRemoveResponse,
  WatchlistResponse,
} from "./types";

const PASSWORD_STORAGE_KEY = "finally_app_password";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getStoredPassword(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(PASSWORD_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredPassword(password: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (password) {
      window.sessionStorage.setItem(PASSWORD_STORAGE_KEY, password);
    } else {
      window.sessionStorage.removeItem(PASSWORD_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors in restricted contexts
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const password = getStoredPassword();
  if (password) {
    headers.set("X-App-Password", password);
  }

  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data?.detail) && data.detail[0]?.msg) {
        detail = data.detail[0].msg;
      }
    } catch {
      // Non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  getHealth: () => apiFetch<HealthResponse>("/api/health"),
  getPortfolio: () => apiFetch<PortfolioResponse>("/api/portfolio"),
  getPortfolioHistory: () =>
    apiFetch<PortfolioSnapshotResponse[]>("/api/portfolio/history"),
  executeTrade: (payload: TradeRequest) =>
    apiFetch<TradeResponse>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getWatchlist: () => apiFetch<WatchlistResponse>("/api/watchlist"),
  addToWatchlist: (ticker: string) =>
    apiFetch<WatchlistItemResponse>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeFromWatchlist: (ticker: string) =>
    apiFetch<WatchlistRemoveResponse>(
      `/api/watchlist/${encodeURIComponent(ticker)}`,
      { method: "DELETE" }
    ),
  getChatHistory: () => apiFetch<ChatHistoryResponse>("/api/chat/history"),
  sendChat: (message: string) =>
    apiFetch<ChatMessageResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
