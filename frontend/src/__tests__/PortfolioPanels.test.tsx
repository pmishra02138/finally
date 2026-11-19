import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Header } from "@/components/Header";
import { PortfolioHeatmap } from "@/components/PortfolioHeatmap";
import { PositionsTable } from "@/components/PositionsTable";
import type { LivePortfolioSummary } from "@/lib/format";

const MOCK_PORTFOLIO: LivePortfolioSummary = {
  cash_balance: 8100,
  total_value: 10050,
  total_unrealized_pnl: 50,
  total_unrealized_pnl_pct: 2.63,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 190,
      current_price: 195,
      market_value: 1950,
      unrealized_pnl: 50,
      unrealized_pnl_pct: 2.63,
      weight_pct: 19.4,
    },
  ],
};

describe("Header, PositionsTable, and PortfolioHeatmap", () => {
  it("renders portfolio totals, connection status, positions, and heatmap tiles", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <>
        <Header
          portfolio={MOCK_PORTFOLIO}
          connectionStatus="connected"
          chatOpen={true}
          onToggleChat={vi.fn()}
        />
        <PortfolioHeatmap
          positions={MOCK_PORTFOLIO.positions}
          onSelectTicker={onSelect}
        />
        <PositionsTable
          positions={MOCK_PORTFOLIO.positions}
          selectedTicker="AAPL"
          onSelectTicker={onSelect}
        />
      </>
    );

    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,050.00");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,100.00");
    expect(screen.getByTestId("connection-status")).toHaveTextContent("LIVE");
    expect(screen.getByTestId("heatmap-grid")).toBeInTheDocument();

    const tile = screen.getByRole("button", { name: /AAPL/i });
    await user.click(tile);
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });
});
