import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MainChart } from "@/components/MainChart";
import { PnLChart } from "@/components/PnLChart";

describe("MainChart and PnLChart", () => {
  it("renders MainChart header stats and PnLChart return summary", () => {
    render(
      <>
        <MainChart
          ticker="NVDA"
          priceUpdate={{
            ticker: "NVDA",
            price: 145.5,
            previous_price: 144.0,
            timestamp: 1700000005,
            change: 1.5,
            change_percent: 1.04,
            direction: "up",
          }}
          points={[
            { time: 1700000001, value: 142.0 },
            { time: 1700000005, value: 145.5 },
          ]}
        />
        <PnLChart
          snapshots={[
            { total_value: 10000, recorded_at: "2026-01-01T00:00:00Z" },
            { total_value: 10250, recorded_at: "2026-01-01T00:05:00Z" },
          ]}
          liveTotalValue={10300}
        />
      </>
    );

    expect(screen.getByTestId("main-chart-ticker")).toHaveTextContent("NVDA");
    expect(screen.getAllByText("$145.50")).toHaveLength(2);
    expect(screen.getByText("$142.00")).toBeInTheDocument();
    expect(screen.getByText("$10,300.00")).toBeInTheDocument();
    expect(screen.getByText("+3.00%")).toBeInTheDocument();
    expect(screen.getByText("(2 pts)")).toBeInTheDocument();
  });
});
