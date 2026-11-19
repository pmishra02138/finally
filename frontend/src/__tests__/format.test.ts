import { describe, expect, it } from "vitest";
import {
  computeLivePortfolio,
  formatCurrency,
  formatPercent,
  formatSignedCurrency,
} from "@/lib/format";
import type { PortfolioResponse, PriceUpdate } from "@/lib/types";

describe("format utilities", () => {
  it("formats currency, signed currency, and percents", () => {
    expect(formatCurrency(10000)).toBe("$10,000.00");
    expect(formatCurrency(-42.5)).toBe("-$42.50");
    expect(formatSignedCurrency(125.1)).toBe("+$125.10");
    expect(formatSignedCurrency(-10)).toBe("-$10.00");
    expect(formatPercent(2.634)).toBe("+2.63%");
    expect(formatPercent(-1.2)).toBe("-1.20%");
  });

  it("recomputes portfolio value, P&L, and weights reactively from live SSE prices", () => {
    const portfolio: PortfolioResponse = {
      cash_balance: 8000,
      total_value: 10000,
      total_unrealized_pnl: 0,
      total_unrealized_pnl_pct: 0,
      positions: [
        {
          ticker: "AAPL",
          quantity: 10,
          avg_cost: 200,
          current_price: 200,
          market_value: 2000,
          unrealized_pnl: 0,
          unrealized_pnl_pct: 0,
          weight_pct: 20,
        },
      ],
    };

    const livePrices: Record<string, PriceUpdate> = {
      AAPL: {
        ticker: "AAPL",
        price: 220,
        previous_price: 215,
        timestamp: 1700000000,
        change: 5,
        change_percent: 2.33,
        direction: "up",
      },
    };

    const live = computeLivePortfolio(portfolio, livePrices);
    expect(live.total_value).toBeCloseTo(10200, 2);
    expect(live.total_unrealized_pnl).toBeCloseTo(200, 2);
    expect(live.total_unrealized_pnl_pct).toBeCloseTo(10, 2);
    expect(live.positions[0].current_price).toBe(220);
    expect(live.positions[0].market_value).toBe(2200);
    expect(live.positions[0].weight_pct).toBeCloseTo((2200 / 10200) * 100, 2);
  });
});
