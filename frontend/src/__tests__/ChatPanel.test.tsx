import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import type { ChatMessageResponse } from "@/lib/types";

const MESSAGES: ChatMessageResponse[] = [
  {
    id: "m1",
    role: "user",
    content: "Buy 2 AAPL and 9999 NVDA",
    actions: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "m2",
    role: "assistant",
    content: "Executed your AAPL buy order.",
    actions: [
      {
        type: "trade",
        ticker: "AAPL",
        side: "buy",
        quantity: 2,
        price: 190,
        action: null,
        status: "executed",
        error: null,
      },
      {
        type: "trade",
        ticker: "NVDA",
        side: "buy",
        quantity: 9999,
        price: null,
        action: null,
        status: "failed",
        error: "Insufficient cash",
      },
    ],
    created_at: "2026-01-01T00:00:01Z",
  },
];

describe("ChatPanel", () => {
  it("renders history, executed/failed action badges, loading indicator, and sends messages", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <ChatPanel messages={MESSAGES} sending={false} onSend={onSend} />
    );

    expect(screen.getByText("Executed your AAPL buy order.")).toBeInTheDocument();
    expect(screen.getByText(/BUY 2 AAPL @ \$190\.00/)).toBeInTheDocument();
    expect(screen.getByText("Insufficient cash")).toBeInTheDocument();

    const input = screen.getByLabelText("Chat message");
    await user.type(input, "Analyze my risk");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledWith("Analyze my risk");

    rerender(<ChatPanel messages={MESSAGES} sending={true} onSend={onSend} />);
    expect(screen.getByText(/FinAlly is thinking/i)).toBeInTheDocument();
  });
});
