import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePriceStream } from "@/hooks/usePriceStream";
import { setStoredPassword } from "@/lib/api";

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: MockEventSource[] = [];

  url: string;
  readyState = MockEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
    this.readyState = MockEventSource.CLOSED;
  }

  emitOpen() {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.();
  }

  emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  emitError(closed = false) {
    this.readyState = closed ? MockEventSource.CLOSED : MockEventSource.CONNECTING;
    this.onerror?.();
  }
}

describe("usePriceStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    setStoredPassword(null);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setStoredPassword(null);
  });

  it("connects, appends ?key= when password is stored, tracks flashes, and handles disconnect", () => {
    setStoredPassword("my-secret");
    const { result, unmount } = renderHook(() => usePriceStream(true, 0));

    expect(MockEventSource.instances).toHaveLength(1);
    const es = MockEventSource.instances[0];
    expect(es.url).toBe("/api/stream/prices?key=my-secret");

    act(() => {
      es.emitOpen();
      es.emitMessage({
        AAPL: {
          ticker: "AAPL",
          price: 190,
          previous_price: 190,
          timestamp: 1700000001,
          change: 0,
          change_percent: 0,
          direction: "flat",
        },
      });
    });

    expect(result.current.connectionStatus).toBe("connected");
    expect(result.current.prices.AAPL.price).toBe(190);
    expect(result.current.flashes.AAPL).toBeUndefined();

    // Uptick triggers flash-up and clears after 500ms
    act(() => {
      es.emitMessage({
        AAPL: {
          ticker: "AAPL",
          price: 192,
          previous_price: 190,
          timestamp: 1700000002,
          change: 2,
          change_percent: 1.05,
          direction: "up",
        },
      });
    });

    expect(result.current.flashes.AAPL).toBe("up");
    expect(result.current.history.AAPL).toHaveLength(2);

    act(() => {
      vi.advanceTimersByTime(550);
    });
    expect(result.current.flashes.AAPL).toBeUndefined();

    // Error -> reconnecting, closed -> disconnected
    act(() => {
      es.emitError(false);
    });
    expect(result.current.connectionStatus).toBe("reconnecting");

    act(() => {
      es.emitError(true);
    });
    expect(result.current.connectionStatus).toBe("disconnected");

    unmount();
    expect(es.closed).toBe(true);
  });
});
