"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { MainChart } from "./MainChart";
import { PasswordModal } from "./PasswordModal";
import { PnLChart } from "./PnLChart";
import { PortfolioHeatmap } from "./PortfolioHeatmap";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { WatchlistPanel } from "./WatchlistPanel";
import { usePriceStream } from "@/hooks/usePriceStream";
import { ApiError, api, setStoredPassword } from "@/lib/api";
import { computeLivePortfolio } from "@/lib/format";
import type {
  ChatMessageResponse,
  PortfolioResponse,
  PortfolioSnapshotResponse,
  WatchlistItemResponse,
} from "@/lib/types";

export function TradingWorkstation() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshotResponse[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItemResponse[]>([]);
  const [messages, setMessages] = useState<ChatMessageResponse[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string>("AAPL");
  const [chatOpen, setChatOpen] = useState<boolean>(true);
  const [chatSending, setChatSending] = useState<boolean>(false);

  const [authRequired, setAuthRequired] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authNonce, setAuthNonce] = useState<number>(0);

  const {
    prices,
    history: priceHistory,
    flashes,
    connectionStatus,
  } = usePriceStream(!authRequired, authNonce);

  const handleApiError = useCallback((err: unknown): boolean => {
    if (err instanceof ApiError && err.status === 401) {
      setAuthRequired(true);
      setAuthError("Invalid or missing password");
      return true;
    }
    return false;
  }, []);

  const refreshData = useCallback(async () => {
    try {
      const [port, hist, wl] = await Promise.all([
        api.getPortfolio(),
        api.getPortfolioHistory(),
        api.getWatchlist(),
      ]);
      setPortfolio(port);
      setHistory(hist);
      setWatchlist(wl.tickers);
      setAuthRequired(false);
      setAuthError(null);
      setSelectedTicker((curr) => {
        if (curr) return curr;
        return wl.tickers[0]?.ticker ?? "AAPL";
      });
    } catch (err) {
      handleApiError(err);
    }
  }, [handleApiError]);

  const loadInitial = useCallback(async () => {
    try {
      const [port, hist, wl, chat] = await Promise.all([
        api.getPortfolio(),
        api.getPortfolioHistory(),
        api.getWatchlist(),
        api.getChatHistory(),
      ]);
      setPortfolio(port);
      setHistory(hist);
      setWatchlist(wl.tickers);
      setMessages(chat.messages);
      setAuthRequired(false);
      setAuthError(null);
      if (wl.tickers.length > 0) {
        setSelectedTicker((curr) => curr || wl.tickers[0].ticker);
      }
    } catch (err) {
      handleApiError(err);
    }
  }, [handleApiError]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial, authNonce]);

  // Periodically refresh portfolio history snapshots every 30s
  useEffect(() => {
    if (authRequired) return;
    const id = setInterval(() => {
      void api
        .getPortfolioHistory()
        .then(setHistory)
        .catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, [authRequired]);

  const livePortfolio = useMemo(
    () => computeLivePortfolio(portfolio, prices),
    [portfolio, prices]
  );

  const handleAddTicker = async (ticker: string) => {
    try {
      await api.addToWatchlist(ticker);
      await refreshData();
      setSelectedTicker(ticker);
    } catch (err) {
      if (!handleApiError(err)) throw err;
    }
  };

  const handleRemoveTicker = async (ticker: string) => {
    try {
      await api.removeFromWatchlist(ticker);
      await refreshData();
    } catch (err) {
      handleApiError(err);
    }
  };

  const handleTrade = async (
    ticker: string,
    side: "buy" | "sell",
    quantity: number
  ) => {
    try {
      const res = await api.executeTrade({ ticker, side, quantity });
      setPortfolio(res.portfolio);
      await refreshData();
    } catch (err) {
      if (!handleApiError(err)) throw err;
    }
  };

  const handleSendChat = async (text: string) => {
    const optimisticUser: ChatMessageResponse = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      actions: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setChatSending(true);
    try {
      const reply = await api.sendChat(text);
      setMessages((prev) => [...prev, reply]);
      await refreshData();
    } catch (err) {
      if (!handleApiError(err)) {
        throw err;
      }
    } finally {
      setChatSending(false);
    }
  };

  const handlePasswordSubmit = (password: string) => {
    setStoredPassword(password);
    setAuthError(null);
    setAuthNonce((n) => n + 1);
  };

  return (
    <div className="flex min-h-screen flex-col bg-terminal-bg text-terminal-text">
      <Header
        portfolio={livePortfolio}
        connectionStatus={connectionStatus}
        chatOpen={chatOpen}
        onToggleChat={() => setChatOpen((o) => !o)}
      />

      <main className="flex flex-1 flex-col gap-2.5 p-2.5 lg:flex-row">
        {/* Left/Center Trading Terminal Area */}
        <div className="flex min-w-0 flex-1 flex-col gap-2.5">
          {/* Top Row: Watchlist + Main Chart */}
          <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-12">
            <div className="h-[340px] lg:col-span-4">
              <WatchlistPanel
                items={watchlist}
                prices={prices}
                history={priceHistory}
                flashes={flashes}
                selectedTicker={selectedTicker}
                onSelectTicker={setSelectedTicker}
                onAddTicker={handleAddTicker}
                onRemoveTicker={handleRemoveTicker}
              />
            </div>
            <div className="h-[340px] lg:col-span-8">
              <MainChart
                ticker={selectedTicker}
                priceUpdate={prices[selectedTicker] ?? null}
                points={priceHistory[selectedTicker] ?? []}
              />
            </div>
          </div>

          {/* Trade Bar */}
          <TradeBar
            selectedTicker={selectedTicker}
            prices={prices}
            onTrade={handleTrade}
          />

          {/* Analytics Row: Portfolio Heatmap + P&L Chart */}
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
            <div className="min-h-[210px]">
              <PortfolioHeatmap
                positions={livePortfolio.positions}
                onSelectTicker={setSelectedTicker}
              />
            </div>
            <div className="min-h-[210px]">
              <PnLChart
                snapshots={history}
                liveTotalValue={livePortfolio.total_value}
              />
            </div>
          </div>

          {/* Positions Table */}
          <div className="min-h-[190px] flex-1">
            <PositionsTable
              positions={livePortfolio.positions}
              selectedTicker={selectedTicker}
              onSelectTicker={setSelectedTicker}
            />
          </div>
        </div>

        {/* Right Docked AI Copilot Sidebar */}
        {chatOpen && (
          <div className="h-[520px] w-full shrink-0 lg:h-[calc(100vh-76px)] lg:sticky lg:top-2.5 lg:w-[350px] xl:w-[390px]">
            <ChatPanel
              messages={messages}
              sending={chatSending}
              onSend={handleSendChat}
            />
          </div>
        )}
      </main>

      <PasswordModal
        open={authRequired}
        error={authError}
        onSubmit={handlePasswordSubmit}
      />
    </div>
  );
}
