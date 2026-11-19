"use client";

import { MessageSquare, TrendingUp } from "lucide-react";
import {
  formatCurrency,
  formatPercent,
  formatSignedCurrency,
  type LivePortfolioSummary,
} from "@/lib/format";
import type { ConnectionStatus } from "@/lib/types";

interface HeaderProps {
  portfolio: LivePortfolioSummary;
  connectionStatus: ConnectionStatus;
  chatOpen: boolean;
  onToggleChat: () => void;
}

const STATUS_META: Record<
  ConnectionStatus,
  { dotClass: string; label: string }
> = {
  connected: { dotClass: "bg-terminal-green", label: "LIVE" },
  reconnecting: { dotClass: "bg-terminal-yellow animate-pulse", label: "RECONNECTING" },
  disconnected: { dotClass: "bg-terminal-red", label: "DISCONNECTED" },
};

export function Header({
  portfolio,
  connectionStatus,
  chatOpen,
  onToggleChat,
}: HeaderProps) {
  const status = STATUS_META[connectionStatus];
  const pnlColor =
    portfolio.total_unrealized_pnl > 0
      ? "text-terminal-green"
      : portfolio.total_unrealized_pnl < 0
        ? "text-terminal-red"
        : "text-terminal-muted";

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-terminal-border bg-terminal-panel px-4 py-2.5">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-terminal-yellow/15 text-terminal-yellow">
            <TrendingUp className="h-4 w-4" />
          </span>
          <div>
            <span className="text-base font-bold tracking-tight text-terminal-yellow">
              FinAlly
            </span>
            <span className="ml-2 hidden text-xs uppercase tracking-widest text-terminal-muted sm:inline">
              AI Trading Workstation
            </span>
          </div>
        </div>

        <div
          className="ml-2 flex items-center gap-1.5 rounded border border-terminal-border bg-terminal-bg px-2 py-0.5 text-[11px] font-mono tracking-wider text-terminal-muted"
          data-testid="connection-status"
          title={`Stream status: ${connectionStatus}`}
        >
          <span className={`h-2 w-2 rounded-full ${status.dotClass}`} />
          <span>{status.label}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-5 font-mono text-sm">
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-wider text-terminal-muted">
            Portfolio Value
          </span>
          <span
            className="font-semibold text-terminal-text tabular-nums"
            data-testid="header-total-value"
          >
            {formatCurrency(portfolio.total_value)}
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-wider text-terminal-muted">
            Unrealized P&amp;L
          </span>
          <span
            className={`font-semibold tabular-nums ${pnlColor}`}
            data-testid="header-pnl"
          >
            {formatSignedCurrency(portfolio.total_unrealized_pnl)} (
            {formatPercent(portfolio.total_unrealized_pnl_pct)})
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-wider text-terminal-muted">
            Cash Available
          </span>
          <span
            className="font-semibold text-terminal-blue tabular-nums"
            data-testid="header-cash"
          >
            {formatCurrency(portfolio.cash_balance)}
          </span>
        </div>

        <button
          type="button"
          onClick={onToggleChat}
          className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
            chatOpen
              ? "border-terminal-purple bg-terminal-purple text-white"
              : "border-terminal-border bg-terminal-elevated text-terminal-text hover:border-terminal-purple"
          }`}
          aria-pressed={chatOpen}
        >
          <MessageSquare className="h-3.5 w-3.5" />
          <span>AI Copilot</span>
        </button>
      </div>
    </header>
  );
}
