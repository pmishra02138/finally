"use client";

import { FormEvent, useState } from "react";
import { Plus, X } from "lucide-react";
import { Sparkline } from "./Sparkline";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { PricePoint, PriceUpdate, WatchlistItemResponse } from "@/lib/types";

interface WatchlistPanelProps {
  items: WatchlistItemResponse[];
  prices: Record<string, PriceUpdate>;
  history: Record<string, PricePoint[]>;
  flashes: Record<string, "up" | "down">;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
  onAddTicker: (ticker: string) => Promise<void>;
  onRemoveTicker: (ticker: string) => Promise<void>;
}

export function WatchlistPanel({
  items,
  prices,
  history,
  flashes,
  selectedTicker,
  onSelectTicker,
  onAddTicker,
  onRemoveTicker,
}: WatchlistPanelProps) {
  const [newTicker, setNewTicker] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    const cleaned = newTicker.trim().toUpperCase();
    if (!cleaned) return;
    setBusy(true);
    setError(null);
    try {
      await onAddTicker(cleaned);
      setNewTicker("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add ticker");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="Watchlist"
    >
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
          Watchlist ({items.length})
        </h2>
        <form onSubmit={handleAdd} className="flex items-center gap-1.5">
          <input
            type="text"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
            placeholder="Add ticker"
            maxLength={5}
            aria-label="Add ticker to watchlist"
            className="w-24 rounded border border-terminal-border bg-terminal-bg px-2 py-1 font-mono text-xs text-terminal-text placeholder:text-terminal-muted focus:border-terminal-blue focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !newTicker.trim()}
            aria-label="Add ticker"
            className="flex items-center justify-center rounded bg-terminal-blue px-2 py-1 text-xs font-medium text-white hover:bg-terminal-blue/90 disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </form>
      </div>

      {error && (
        <div
          role="alert"
          className="border-b border-terminal-red/30 bg-terminal-red/10 px-3 py-1.5 text-xs text-terminal-red"
        >
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <table className="w-full border-collapse text-left font-mono text-xs">
          <thead className="sticky top-0 bg-terminal-elevated text-[10px] uppercase tracking-wider text-terminal-muted">
            <tr>
              <th className="px-3 py-1.5">Ticker</th>
              <th className="px-2 py-1.5 text-right">Price</th>
              <th className="px-2 py-1.5 text-right">Chg %</th>
              <th className="px-2 py-1.5 text-right">Trend</th>
              <th className="w-7 px-1 py-1.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border/60">
            {items.map((item) => {
              const live = prices[item.ticker];
              const price = live?.price ?? item.price ?? null;
              const changePct = live?.change_percent ?? item.change_percent ?? 0;
              const direction = live?.direction ?? item.direction ?? "flat";
              const flash = flashes[item.ticker];
              const isSelected = selectedTicker === item.ticker;

              const flashClass =
                flash === "up"
                  ? "flash-up"
                  : flash === "down"
                    ? "flash-down"
                    : "";

              const chgColor =
                direction === "up"
                  ? "text-terminal-green"
                  : direction === "down"
                    ? "text-terminal-red"
                    : "text-terminal-muted";

              return (
                <tr
                  key={item.ticker}
                  onClick={() => onSelectTicker(item.ticker)}
                  data-testid={`watchlist-row-${item.ticker}`}
                  className={`cursor-pointer transition-colors hover:bg-terminal-elevated/80 ${flashClass} ${
                    isSelected ? "bg-terminal-blue/15" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-semibold text-terminal-text">
                    <span
                      className={
                        isSelected ? "text-terminal-yellow" : "text-terminal-text"
                      }
                    >
                      {item.ticker}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-terminal-text">
                    {price !== null ? formatCurrency(price) : "—"}
                  </td>
                  <td className={`px-2 py-2 text-right tabular-nums ${chgColor}`}>
                    {price !== null ? formatPercent(changePct) : "—"}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <div className="inline-flex justify-end">
                      <Sparkline points={history[item.ticker] ?? []} />
                    </div>
                  </td>
                  <td className="px-1 py-2 text-right">
                    <button
                      type="button"
                      aria-label={`Remove ${item.ticker}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        void onRemoveTicker(item.ticker);
                      }}
                      className="rounded p-0.5 text-terminal-muted hover:bg-terminal-red/20 hover:text-terminal-red"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-6 text-center text-xs text-terminal-muted"
                >
                  Watchlist is empty. Add a ticker above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
