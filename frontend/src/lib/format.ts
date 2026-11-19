import type { PortfolioResponse, PositionResponse, PriceUpdate } from "./types";

export function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return value < 0 ? `-$${formatted}` : `$${formatted}`;
}

export function formatSignedCurrency(value: number): string {
  const abs = Math.abs(value);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return `$${formatted}`;
}

export function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatQuantity(value: number): string {
  if (Number.isInteger(value)) {
    return value.toLocaleString("en-US");
  }
  return Number(value.toFixed(4)).toString();
}

export interface LivePortfolioSummary {
  cash_balance: number;
  total_value: number;
  total_unrealized_pnl: number;
  total_unrealized_pnl_pct: number;
  positions: PositionResponse[];
}

/**
 * Recompute live portfolio valuation & position P&L reactively from SSE prices.
 */
export function computeLivePortfolio(
  portfolio: PortfolioResponse | null,
  prices: Record<string, PriceUpdate>
): LivePortfolioSummary {
  if (!portfolio) {
    return {
      cash_balance: 0,
      total_value: 0,
      total_unrealized_pnl: 0,
      total_unrealized_pnl_pct: 0,
      positions: [],
    };
  }

  let totalPositionsValue = 0;
  let totalCostBasis = 0;
  let totalUnrealizedPnl = 0;

  const preliminary = portfolio.positions.map((pos) => {
    const live = prices[pos.ticker]?.price;
    const currentPrice = live !== undefined ? live : pos.current_price;
    const marketValue = pos.quantity * currentPrice;
    const costBasis = pos.quantity * pos.avg_cost;
    const unrealizedPnl = marketValue - costBasis;
    const unrealizedPnlPct = costBasis > 0 ? (unrealizedPnl / costBasis) * 100 : 0;

    totalPositionsValue += marketValue;
    totalCostBasis += costBasis;
    totalUnrealizedPnl += unrealizedPnl;

    return {
      ...pos,
      current_price: currentPrice,
      market_value: marketValue,
      unrealized_pnl: unrealizedPnl,
      unrealized_pnl_pct: unrealizedPnlPct,
    };
  });

  const totalValue = portfolio.cash_balance + totalPositionsValue;
  const totalUnrealizedPnlPct =
    totalCostBasis > 0 ? (totalUnrealizedPnl / totalCostBasis) * 100 : 0;

  const positions: PositionResponse[] = preliminary.map((p) => ({
    ...p,
    weight_pct: totalValue > 0 ? (p.market_value / totalValue) * 100 : 0,
  }));

  return {
    cash_balance: portfolio.cash_balance,
    total_value: totalValue,
    total_unrealized_pnl: totalUnrealizedPnl,
    total_unrealized_pnl_pct: totalUnrealizedPnlPct,
    positions,
  };
}
