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
import type { PortfolioSnapshotResponse } from "@/lib/types";

interface PnLChartProps {
  snapshots: PortfolioSnapshotResponse[];
  liveTotalValue: number;
}

export function PnLChart({ snapshots, liveTotalValue }: PnLChartProps) {
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
          fontSize: 10,
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
          secondsVisible: false,
        },
        width: el.clientWidth || 400,
        height: el.clientHeight || 160,
      });

      const series = chart.addAreaSeries({
        lineColor: "#ecad0a",
        topColor: "rgba(236, 173, 10, 0.28)",
        bottomColor: "rgba(236, 173, 10, 0.02)",
        lineWidth: 2,
      });

      chartRef.current = chart;
      seriesRef.current = series;
    } catch {
      return;
    }

    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry && chartRef.current) {
              chartRef.current.applyOptions({
                width: Math.max(180, Math.floor(entry.contentRect.width)),
                height: Math.max(140, Math.floor(entry.contentRect.height)),
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
  }, []);

  useEffect(() => {
    if (!seriesRef.current || snapshots.length === 0) return;

    const deduped: { time: UTCTimestamp; value: number }[] = [];
    for (const snap of snapshots) {
      const parsed = Math.floor(Date.parse(snap.recorded_at) / 1000);
      const prevTime = deduped.length > 0 ? deduped[deduped.length - 1].time : 0;
      const t = (parsed > prevTime ? parsed : prevTime + 1) as UTCTimestamp;
      deduped.push({ time: t, value: snap.total_value });
    }

    seriesRef.current.setData(deduped);
    chartRef.current?.timeScale().fitContent();
  }, [snapshots]);

  const startValue = snapshots.length > 0 ? snapshots[0].total_value : 10000;
  const currentValue = liveTotalValue > 0 ? liveTotalValue : startValue;
  const totalReturnPct =
    startValue > 0 ? ((currentValue - startValue) / startValue) * 100 : 0;
  const returnColor =
    totalReturnPct > 0
      ? "text-terminal-green"
      : totalReturnPct < 0
        ? "text-terminal-red"
        : "text-terminal-muted";

  return (
    <section
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="Portfolio P&L Chart"
    >
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
          Portfolio Value History
        </h2>
        <div className="flex items-center gap-3 font-mono text-xs">
          <span className="tabular-nums text-terminal-text">
            {formatCurrency(currentValue)}
          </span>
          <span className={`tabular-nums ${returnColor}`}>
            {formatPercent(totalReturnPct)}
          </span>
          <span className="text-[10px] text-terminal-muted">
            ({snapshots.length} pts)
          </span>
        </div>
      </div>

      <div className="relative flex-1 min-h-[150px] p-1">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </section>
  );
}
