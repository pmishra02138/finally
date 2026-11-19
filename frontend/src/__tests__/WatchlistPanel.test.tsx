import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WatchlistPanel } from "@/components/WatchlistPanel";
import type { PriceUpdate, WatchlistItemResponse } from "@/lib/types";

const ITEMS: WatchlistItemResponse[] = [
  {
    ticker: "AAPL",
    price: 190.5,
    previous_price: 190.0,
    change: 0.5,
    change_percent: 0.26,
    direction: "up",
    timestamp: 1700000000,
    added_at: "2026-01-01T00:00:00Z",
  },
  {
    ticker: "TSLA",
    price: 250.0,
    previous_price: 252.0,
    change: -2.0,
    change_percent: -0.79,
    direction: "down",
    timestamp: 1700000000,
    added_at: "2026-01-01T00:00:00Z",
  },
];

const PRICES: Record<string, PriceUpdate> = {
  AAPL: {
    ticker: "AAPL",
    price: 191.2,
    previous_price: 190.5,
    timestamp: 1700000005,
    change: 0.7,
    change_percent: 0.37,
    direction: "up",
  },
  TSLA: {
    ticker: "TSLA",
    price: 248.5,
    previous_price: 250.0,
    timestamp: 1700000005,
    change: -1.5,
    change_percent: -0.6,
    direction: "down",
  },
};

describe("WatchlistPanel", () => {
  it("renders tickers, triggers price flash classes, and supports add/remove/select", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onAdd = vi.fn().mockResolvedValue(undefined);
    const onRemove = vi.fn().mockResolvedValue(undefined);

    render(
      <WatchlistPanel
        items={ITEMS}
        prices={PRICES}
        history={{
          AAPL: [
            { time: 1, value: 190 },
            { time: 2, value: 191.2 },
          ],
        }}
        flashes={{ AAPL: "up", TSLA: "down" }}
        selectedTicker="AAPL"
        onSelectTicker={onSelect}
        onAddTicker={onAdd}
        onRemoveTicker={onRemove}
      />
    );

    const aaplRow = screen.getByTestId("watchlist-row-AAPL");
    const tslaRow = screen.getByTestId("watchlist-row-TSLA");
    expect(aaplRow).toHaveClass("flash-up");
    expect(tslaRow).toHaveClass("flash-down");
    expect(screen.getByText("$191.20")).toBeInTheDocument();

    // Select TSLA
    await user.click(tslaRow);
    expect(onSelect).toHaveBeenCalledWith("TSLA");

    // Add PYPL
    const input = screen.getByLabelText("Add ticker to watchlist");
    await user.type(input, "pypl");
    await user.click(screen.getByRole("button", { name: "Add ticker" }));
    expect(onAdd).toHaveBeenCalledWith("PYPL");

    // Remove TSLA
    await user.click(screen.getByRole("button", { name: "Remove TSLA" }));
    expect(onRemove).toHaveBeenCalledWith("TSLA");
  });
});
