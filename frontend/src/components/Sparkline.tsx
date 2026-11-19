"use client";

import type { PricePoint } from "@/lib/types";

interface SparklineProps {
  points: PricePoint[];
  width?: number;
  height?: number;
}

export function Sparkline({ points, width = 76, height = 22 }: SparklineProps) {
  if (points.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="overflow-visible"
        aria-hidden="true"
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#253041"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      </svg>
    );
  }

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const padY = 2;
  const innerH = height - padY * 2;

  const coords = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = padY + innerH - ((v - min) / spread) * innerH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const isUp = values[values.length - 1] >= values[0];
  const stroke = isUp ? "#22c55e" : "#ef4444";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={coords.join(" ")}
      />
    </svg>
  );
}
