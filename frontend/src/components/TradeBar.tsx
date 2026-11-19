"use client";

import { useEffect, useState } from "react";
import { formatCurrency } from "@/lib/format";
import type { PriceUpdate } from "@/lib/types";

interface TradeBarProps {
  selectedTicker: string;
  prices: Record<string, PriceUpdate>;
  onTrade: (ticker: string, side: "buy" | "sell", quantity: number) => Promise<void>;
}

export function TradeBar({ selectedTicker, prices, onTrade }: TradeBarProps) {
  const [ticker, setTicker] = useState(selectedTicker || "AAPL");
  const [quantity, setQuantity] = useState("1");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    if (selectedTicker) {
      setTicker(selectedTicker);
    }
  }, [selectedTicker]);

  const normalized = ticker.trim().toUpperCase();
  const parsedQty = Number(quantity);
  const livePrice = prices[normalized]?.price ?? null;
  const estTotal =
    livePrice !== null && Number.isFinite(parsedQty) && parsedQty > 0
      ? livePrice * parsedQty
      : null;

  const submit = async (side: "buy" | "sell") => {
    if (!normalized) {
      setFeedback({ type: "error", text: "Enter a valid ticker" });
      return;
    }
    if (!Number.isFinite(parsedQty) || parsedQty <= 0) {
      setFeedback({ type: "error", text: "Quantity must be greater than 0" });
      return;
    }

    setBusy(true);
    setFeedback(null);
    try {
      await onTrade(normalized, side, parsedQty);
      setFeedback({
        type: "success",
        text: `${side.toUpperCase()} ${parsedQty} ${normalized} filled`,
      });
    } catch (err) {
      setFeedback({
        type: "error",
        text: err instanceof Error ? err.message : "Trade failed",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="flex flex-wrap items-center justify-between gap-3 rounded border border-terminal-border bg-terminal-panel px-3 py-2"
      aria-label="Trade Bar"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
          Market Order
        </span>

        <label className="flex items-center gap-1.5 text-xs text-terminal-muted">
          <span>Ticker</span>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            maxLength={5}
            aria-label="Trade ticker"
            className="w-20 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-xs font-semibold text-terminal-text focus:border-terminal-blue focus:outline-none"
          />
        </label>

        <label className="flex items-center gap-1.5 text-xs text-terminal-muted">
          <span>Qty</span>
          <input
            type="number"
            min="0.0001"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            aria-label="Trade quantity"
            className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-xs text-terminal-text focus:border-terminal-blue focus:outline-none"
          />
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit("buy")}
            className="rounded bg-terminal-green px-3.5 py-1 text-xs font-semibold text-terminal-bg hover:bg-terminal-green/90 disabled:opacity-40"
          >
            Buy
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit("sell")}
            className="rounded bg-terminal-red px-3.5 py-1 text-xs font-semibold text-white hover:bg-terminal-red/90 disabled:opacity-40"
          >
            Sell
          </button>
        </div>

        {estTotal !== null && (
          <span className="font-mono text-xs text-terminal-muted">
            Est: <strong className="text-terminal-text">{formatCurrency(estTotal)}</strong>
          </span>
        )}
      </div>

      {feedback && (
        <div
          role={feedback.type === "error" ? "alert" : "status"}
          className={`font-mono text-xs ${
            feedback.type === "error" ? "text-terminal-red" : "text-terminal-green"
          }`}
        >
          {feedback.text}
        </div>
      )}
    </section>
  );
}
