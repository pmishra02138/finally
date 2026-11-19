import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "@/components/TradeBar";

describe("TradeBar", () => {
  it("submits market buy/sell orders and displays confirmation", async () => {
    const user = userEvent.setup();
    const onTrade = vi.fn().mockResolvedValue(undefined);

    render(
      <TradeBar
        selectedTicker="AAPL"
        prices={{
          AAPL: {
            ticker: "AAPL",
            price: 200,
            previous_price: 199,
            timestamp: 1700000000,
            change: 1,
            change_percent: 0.5,
            direction: "up",
          },
        }}
        onTrade={onTrade}
      />
    );

    const qtyInput = screen.getByLabelText("Trade quantity");
    await user.clear(qtyInput);
    await user.type(qtyInput, "5");
    expect(screen.getByText("$1,000.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Buy" }));
    expect(onTrade).toHaveBeenCalledWith("AAPL", "buy", 5);
    expect(await screen.findByText(/BUY 5 AAPL filled/i)).toBeInTheDocument();
  });
});
