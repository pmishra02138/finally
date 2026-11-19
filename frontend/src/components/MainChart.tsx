"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { PricePoint, PriceUpdate } from "@/lib/types";

interface MainChartProps {
  ticker: string;
  priceUpdate: PriceUpdate | null;
  points: PricePoint[];
}

export function MainChart({ ticker, priceUpdate, points }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }

    let chart: IChartApi | null = null;
    try {
      chart = createChart(el, {
        layout: {
          background: { type: ColorType.Solid, color: "#131922" },
          textColor: "#8b98a9",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1d2635" },
          horzLines: { color: "#1d2635" },
        },
        rightPriceScale: {
          borderColor: "#253041",
        },
        timeScale: {
          borderColor: "#253041",
          timeVisible: true,
          secondsVisible: true,
        },
        width: el.clientWidth || 500,
        height: el.clientHeight || 240,
      });

      const series = chart.addAreaSeries({
        lineColor: "#209dd7",
        topColor: "rgba(32, 157, 215, 0.32)",
        bottomColor: "rgba(32, 157, 215, 0.02)",
        lineWidth: 2,
      });

      chartRef.current = chart;
      seriesRef.current = series;
    } catch {
      // Canvas not available in headless jsdom test environment
      return;
    }

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry && chartRef.current) {
              chartRef.current.applyOptions({
                width: Math.max(200, Math.floor(entry.contentRect.width)),
                height: Math.max(180, Math.floor(entry.contentRect.height)),
              });
            }
          })
        : null;

    observer?.observe(el);

    return () => {
      observer?.disconnect();
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [ticker]);

  useEffect(() => {
    if (!seriesRef.current || points.length === 0) return;
    const formatted = points.map((p) => ({
      time: p.time as UTCTimestamp,
      value: p.value,
    }));
    seriesRef.current.setData(formatted);
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  const values = points.map((p) => p.value);
  const sessionHigh = values.length > 0 ? Math.max(...values) : null;
  const sessionLow = values.length > 0 ? Math.min(...values) : null;
  const direction = priceUpdate?.direction ?? "flat";
  const dirColor =
    direction === "up"
      ? "text-terminal-green"
      : direction === "down"
        ? "text-terminal-red"
        : "text-terminal-muted";

  return (
    <section
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="Main Price Chart"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-terminal-border px-3 py-2">
        <div className="flex items-baseline gap-3 font-mono">
          <h2
            className="text-sm font-bold text-terminal-yellow"
            data-testid="main-chart-ticker"
          >
            {ticker || "—"}
          </h2>
          {priceUpdate ? (
            <>
              <span className="text-lg font-bold tabular-nums text-terminal-text">
                {formatCurrency(priceUpdate.price)}
              </span>
              <span className={`text-xs font-medium tabular-nums ${dirColor}`}>
                {priceUpdate.change >= 0 ? "+" : ""}
                {priceUpdate.change.toFixed(2)} (
                {formatPercent(priceUpdate.change_percent)})
              </span>
            </>
          ) : (
            <span className="text-xs text-terminal-muted">Waiting for stream…</span>
          )}
        </div>

        <div className="flex items-center gap-4 font-mono text-[11px] text-terminal-muted">
          <span>
            HIGH:{" "}
            <strong className="text-terminal-text">
              {sessionHigh !== null ? formatCurrency(sessionHigh) : "—"}
            </strong>
          </span>
          <span>
            LOW:{" "}
            <strong className="text-terminal-text">
              {sessionLow !== null ? formatCurrency(sessionLow) : "—"}
            </strong>
          </span>
          <span>
            TICKS: <strong className="text-terminal-text">{points.length}</strong>
          </span>
        </div>
      </div>

      <div className="relative flex-1 min-h-[220px] p-1">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </section>
  );
}
