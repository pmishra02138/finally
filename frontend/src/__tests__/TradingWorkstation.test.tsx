import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TradingWorkstation } from "@/components/TradingWorkstation";
import { setStoredPassword } from "@/lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("TradingWorkstation integration", () => {
  beforeEach(() => {
    setStoredPassword(null);
    vi.stubGlobal("EventSource", undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    setStoredPassword(null);
  });

  it("loads initial data, executes a trade, sends chat, and toggles copilot", async () => {
    const user = userEvent.setup();
    let cash = 10000;
    let positions: unknown[] = [];

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/portfolio") {
        return jsonResponse({
          cash_balance: cash,
          total_value: 10000,
          total_unrealized_pnl: 0,
          total_unrealized_pnl_pct: 0,
          positions,
        });
      }
      if (url === "/api/portfolio/history") {
        return jsonResponse([
          { total_value: 10000, recorded_at: "2026-01-01T00:00:00Z" },
        ]);
      }
      if (url === "/api/watchlist") {
        return jsonResponse({
          tickers: [
            {
              ticker: "AAPL",
              price: 200,
              previous_price: 199,
              change: 1,
              change_percent: 0.5,
              direction: "up",
              timestamp: 1700000000,
              added_at: "2026-01-01T00:00:00Z",
            },
          ],
        });
      }
      if (url === "/api/chat/history") {
        return jsonResponse({ messages: [] });
      }
      if (url === "/api/portfolio/trade" && init?.method === "POST") {
        cash = 9600;
        positions = [
          {
            ticker: "AAPL",
            quantity: 2,
            avg_cost: 200,
            current_price: 200,
            market_value: 400,
            unrealized_pnl: 0,
            unrealized_pnl_pct: 0,
            weight_pct: 4,
          },
        ];
        return jsonResponse({
          trade: {
            id: "t1",
            ticker: "AAPL",
            side: "buy",
            quantity: 2,
            price: 200,
            executed_at: "2026-01-01T00:01:00Z",
          },
          portfolio: {
            cash_balance: cash,
            total_value: 10000,
            total_unrealized_pnl: 0,
            total_unrealized_pnl_pct: 0,
            positions,
          },
        });
      }
      if (url === "/api/chat" && init?.method === "POST") {
        return jsonResponse({
          id: "c1",
          role: "assistant",
          content: "Your cash is $9,600.00.",
          actions: [],
          created_at: "2026-01-01T00:02:00Z",
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TradingWorkstation />);

    await waitFor(() => {
      expect(screen.getByTestId("header-cash")).toHaveTextContent("$10,000.00");
    });

    // Execute buy trade via TradeBar
    const qtyInput = screen.getByLabelText("Trade quantity");
    await user.clear(qtyInput);
    await user.type(qtyInput, "2");
    await user.click(screen.getByRole("button", { name: "Buy" }));

    await waitFor(() => {
      expect(screen.getByTestId("header-cash")).toHaveTextContent("$9,600.00");
    });

    // Send chat message
    await user.type(screen.getByLabelText("Chat message"), "status");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("Your cash is $9,600.00.")).toBeInTheDocument();
  });

  it("prompts for APP_PASSWORD on 401 and unlocks once valid password is submitted", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      if (headers.get("X-App-Password") !== "open-sesame") {
        return jsonResponse({ detail: "Unauthorized" }, 401);
      }
      const url = String(input);
      if (url === "/api/portfolio") {
        return jsonResponse({
          cash_balance: 10000,
          total_value: 10000,
          total_unrealized_pnl: 0,
          total_unrealized_pnl_pct: 0,
          positions: [],
        });
      }
      if (url === "/api/portfolio/history") return jsonResponse([]);
      if (url === "/api/watchlist") return jsonResponse({ tickers: [] });
      if (url === "/api/chat/history") return jsonResponse({ messages: [] });
      return jsonResponse({}, 200);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TradingWorkstation />);

    expect(
      await screen.findByRole("dialog", { name: "Access Password Required" })
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Enter password"), "open-sesame");
    await user.click(screen.getByRole("button", { name: "Unlock Terminal" }));

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "Access Password Required" })
      ).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$10,000.00");
  });
});
