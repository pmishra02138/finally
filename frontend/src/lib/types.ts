import type { components } from "./api-types";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type PortfolioResponse = components["schemas"]["PortfolioResponse"];
export type PositionResponse = components["schemas"]["PositionResponse"];
export type TradeRequest = components["schemas"]["TradeRequest"];
export type TradeRecord = components["schemas"]["TradeRecord"];
export type TradeResponse = components["schemas"]["TradeResponse"];
export type PortfolioSnapshotResponse = components["schemas"]["PortfolioSnapshotResponse"];
export type WatchlistItemResponse = components["schemas"]["WatchlistItemResponse"];
export type WatchlistResponse = components["schemas"]["WatchlistResponse"];
export type WatchlistAddRequest = components["schemas"]["WatchlistAddRequest"];
export type WatchlistRemoveResponse = components["schemas"]["WatchlistRemoveResponse"];
export type ChatActionResult = components["schemas"]["ChatActionResult"];
export type ChatMessageResponse = components["schemas"]["ChatMessageResponse"];
export type ChatHistoryResponse = components["schemas"]["ChatHistoryResponse"];
export type ChatRequest = components["schemas"]["ChatRequest"];

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  direction: "up" | "down" | "flat";
}

export interface PricePoint {
  time: number;
  value: number;
}

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";
