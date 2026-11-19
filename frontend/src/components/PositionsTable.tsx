"use client";

import {
  formatCurrency,
  formatPercent,
  formatQuantity,
  formatSignedCurrency,
} from "@/lib/format";
import type { PositionResponse } from "@/lib/types";

interface PositionsTableProps {
  positions: PositionResponse[];
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}

export function PositionsTable({
  positions,
  selectedTicker,
  onSelectTicker,
}: PositionsTableProps) {
  return (
    <section
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="Positions"
    >
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
          Positions ({positions.length})
        </h2>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-auto">
        <table className="w-full border-collapse text-left font-mono text-xs">
          <thead className="sticky top-0 bg-terminal-elevated text-[10px] uppercase tracking-wider text-terminal-muted">
            <tr>
              <th className="px-3 py-1.5">Ticker</th>
              <th className="px-2 py-1.5 text-right">Qty</th>
              <th className="px-2 py-1.5 text-right">Avg Cost</th>
              <th className="px-2 py-1.5 text-right">Price</th>
              <th className="px-2 py-1.5 text-right">Value</th>
              <th className="px-2 py-1.5 text-right">Unrealized P&amp;L</th>
              <th className="px-2 py-1.5 text-right">Return %</th>
              <th className="px-3 py-1.5 text-right">Weight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-terminal-border/60">
            {positions.map((pos) => {
              const pnlColor =
                pos.unrealized_pnl > 0
                  ? "text-terminal-green"
                  : pos.unrealized_pnl < 0
                    ? "text-terminal-red"
                    : "text-terminal-muted";
              const isSelected = selectedTicker === pos.ticker;
              return (
                <tr
                  key={pos.ticker}
                  onClick={() => onSelectTicker(pos.ticker)}
                  className={`cursor-pointer transition-colors hover:bg-terminal-elevated/80 ${
                    isSelected ? "bg-terminal-blue/15" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-semibold text-terminal-yellow">
                    {pos.ticker}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatQuantity(pos.quantity)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-terminal-muted">
                    {formatCurrency(pos.avg_cost)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatCurrency(pos.current_price)}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {formatCurrency(pos.market_value)}
                  </td>
                  <td className={`px-2 py-2 text-right tabular-nums ${pnlColor}`}>
                    {formatSignedCurrency(pos.unrealized_pnl)}
                  </td>
                  <td className={`px-2 py-2 text-right tabular-nums ${pnlColor}`}>
                    {formatPercent(pos.unrealized_pnl_pct)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-terminal-muted">
                    {pos.weight_pct.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
            {positions.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="px-3 py-6 text-center text-xs text-terminal-muted"
                >
                  No open positions yet. Use the trade bar or AI Copilot to buy shares.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
