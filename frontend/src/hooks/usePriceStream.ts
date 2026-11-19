"use client";

import { useEffect, useRef, useState } from "react";
import { getStoredPassword } from "@/lib/api";
import type { ConnectionStatus, PricePoint, PriceUpdate } from "@/lib/types";

const MAX_HISTORY_POINTS = 120;
const FLASH_DURATION_MS = 500;

export interface PriceStreamState {
  prices: Record<string, PriceUpdate>;
  history: Record<string, PricePoint[]>;
  flashes: Record<string, "up" | "down">;
  connectionStatus: ConnectionStatus;
}

export function usePriceStream(enabled: boolean, authNonce: number): PriceStreamState {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({});
  const [history, setHistory] = useState<Record<string, PricePoint[]>>({});
  const [flashes, setFlashes] = useState<Record<string, "up" | "down">>({});
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("reconnecting");

  const prevPricesRef = useRef<Record<string, number>>({});
  const flashTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    if (!enabled || typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    const password = getStoredPassword();
    const url = password
      ? `/api/stream/prices?key=${encodeURIComponent(password)}`
      : "/api/stream/prices";

    setConnectionStatus("reconnecting");
    const es = new EventSource(url);

    es.onopen = () => {
      setConnectionStatus("connected");
    };

    es.onmessage = (event) => {
      try {
        const incoming = JSON.parse(event.data) as Record<string, PriceUpdate>;
        setConnectionStatus("connected");
        setPrices(incoming);

        const nextFlashes: Record<string, "up" | "down"> = {};
        const nowSec = Math.floor(Date.now() / 1000);

        for (const [ticker, update] of Object.entries(incoming)) {
          const prev = prevPricesRef.current[ticker];
          if (prev !== undefined && update.price !== prev) {
            nextFlashes[ticker] = update.price > prev ? "up" : "down";
          }
          prevPricesRef.current[ticker] = update.price;
        }

        // Remove tickers no longer in the stream from prevPricesRef
        for (const existing of Object.keys(prevPricesRef.current)) {
          if (!(existing in incoming)) {
            delete prevPricesRef.current[existing];
          }
        }

        if (Object.keys(nextFlashes).length > 0) {
          setFlashes((prev) => ({ ...prev, ...nextFlashes }));
          for (const ticker of Object.keys(nextFlashes)) {
            if (flashTimersRef.current[ticker]) {
              clearTimeout(flashTimersRef.current[ticker]);
            }
            flashTimersRef.current[ticker] = setTimeout(() => {
              setFlashes((curr) => {
                if (!(ticker in curr)) return curr;
                const copy = { ...curr };
                delete copy[ticker];
                return copy;
              });
            }, FLASH_DURATION_MS);
          }
        }

        setHistory((prev) => {
          const next = { ...prev };
          for (const [ticker, update] of Object.entries(incoming)) {
            const series = prev[ticker] ? [...prev[ticker]] : [];
            const ts = Math.max(
              Math.floor(update.timestamp || nowSec),
              series.length > 0 ? series[series.length - 1].time + 1 : 0
            );
            series.push({ time: ts, value: update.price });
            if (series.length > MAX_HISTORY_POINTS) {
              series.splice(0, series.length - MAX_HISTORY_POINTS);
            }
            next[ticker] = series;
          }
          return next;
        });
      } catch {
        // Ignore malformed SSE frames
      }
    };

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        setConnectionStatus("disconnected");
      } else {
        setConnectionStatus("reconnecting");
      }
    };

    return () => {
      es.close();
      for (const timer of Object.values(flashTimersRef.current)) {
        clearTimeout(timer);
      }
      flashTimersRef.current = {};
    };
  }, [enabled, authNonce]);

  return { prices, history, flashes, connectionStatus };
}
