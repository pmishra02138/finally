"use client";

import { formatCurrency, formatPercent } from "@/lib/format";
import type { PositionResponse } from "@/lib/types";

interface PortfolioHeatmapProps {
  positions: PositionResponse[];
  onSelectTicker: (ticker: string) => void;
}

function getTileColors(pnlPct: number): { bg: string; border: string } {
  if (pnlPct >= 5) return { bg: "rgba(34, 197, 94, 0.45)", border: "#22c55e" };
  if (pnlPct > 0.2) return { bg: "rgba(34, 197, 94, 0.26)", border: "#16a34a" };
  if (pnlPct <= -5) return { bg: "rgba(239, 68, 68, 0.45)", border: "#ef4444" };
  if (pnlPct < -0.2) return { bg: "rgba(239, 68, 68, 0.26)", border: "#dc2626" };
  return { bg: "rgba(139, 152, 169, 0.16)", border: "#3b475a" };
}

export function PortfolioHeatmap({
  positions,
  onSelectTicker,
}: PortfolioHeatmapProps) {
  const sorted = [...positions].sort((a, b) => b.market_value - a.market_value);
  const totalPosValue = sorted.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <section
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="Portfolio Heatmap"
    >
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
          Portfolio Heatmap
        </h2>
        <span className="font-mono text-[10px] text-terminal-muted">
          Sized by weight • Colored by P&amp;L
        </span>
      </div>

      <div className="flex-1 p-2.5">
        {sorted.length === 0 ? (
          <div className="flex h-full min-h-[150px] items-center justify-center rounded border border-dashed border-terminal-border text-xs text-terminal-muted">
            Buy shares to populate the portfolio heatmap
          </div>
        ) : (
          <div
            className="flex h-full min-h-[150px] flex-wrap gap-1.5"
            data-testid="heatmap-grid"
          >
            {sorted.map((pos) => {
              const share =
                totalPosValue > 0
                  ? Math.max(18, (pos.market_value / totalPosValue) * 100)
                  : 100 / sorted.length;
              const { bg, border } = getTileColors(pos.unrealized_pnl_pct);
              return (
                <button
                  key={pos.ticker}
                  type="button"
                  onClick={() => onSelectTicker(pos.ticker)}
                  style={{
                    flexGrow: Math.max(1, Math.round(share)),
                    flexBasis: `${Math.min(100, Math.max(22, share * 0.85))}%`,
                    backgroundColor: bg,
                    borderColor: border,
                  }}
                  className="flex min-h-[68px] flex-col items-start justify-between rounded border p-2 text-left font-mono transition-transform hover:scale-[1.01]"
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="text-xs font-bold text-terminal-text">
                      {pos.ticker}
                    </span>
                    <span className="text-[10px] text-terminal-text/80">
                      {pos.weight_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="mt-1">
                    <div className="text-xs font-semibold tabular-nums text-terminal-text">
                      {formatPercent(pos.unrealized_pnl_pct)}
                    </div>
                    <div className="text-[10px] tabular-nums text-terminal-text/80">
                      {formatCurrency(pos.market_value)}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
