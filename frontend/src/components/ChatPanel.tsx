"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Send, Sparkles, XCircle } from "lucide-react";
import { formatCurrency } from "@/lib/format";
import type { ChatActionResult, ChatMessageResponse } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessageResponse[];
  sending: boolean;
  onSend: (message: string) => Promise<void>;
}

function ActionBadge({ action }: { action: ChatActionResult }) {
  const ok = action.status === "executed";
  const label =
    action.type === "trade"
      ? `${(action.side ?? "trade").toUpperCase()} ${action.quantity ?? ""} ${action.ticker}${
          action.price ? ` @ ${formatCurrency(action.price)}` : ""
        }`
      : `${action.action === "remove" ? "UNWATCH" : "WATCH"} ${action.ticker}`;

  return (
    <div
      className={`mt-1.5 flex items-start gap-1.5 rounded border px-2 py-1 font-mono text-[11px] ${
        ok
          ? "border-terminal-green/40 bg-terminal-green/10 text-terminal-green"
          : "border-terminal-red/40 bg-terminal-red/10 text-terminal-red"
      }`}
    >
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      ) : (
        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      )}
      <div className="min-w-0">
        <div className="font-semibold">{label}</div>
        {!ok && action.error && (
          <div className="text-[10px] text-terminal-red/90">{action.error}</div>
        )}
      </div>
    </div>
  );
}

export function ChatPanel({ messages, sending, onSend }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages, sending]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setError(null);
    setInput("");
    try {
      await onSend(trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    }
  };

  return (
    <aside
      className="flex h-full flex-col rounded border border-terminal-border bg-terminal-panel"
      aria-label="AI Copilot Chat"
    >
      <div className="flex items-center justify-between border-b border-terminal-border px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-terminal-yellow" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-terminal-yellow">
            FinAlly AI Copilot
          </h2>
        </div>
        <span className="font-mono text-[10px] text-terminal-muted">Auto-Exec</span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3 text-xs">
        {messages.length === 0 && (
          <div className="rounded border border-dashed border-terminal-border p-3 text-terminal-muted">
            Ask about your portfolio, risk concentration, or execute trades directly
            (e.g. &ldquo;Buy 5 shares of AAPL&rdquo; or &ldquo;Watch PYPL&rdquo;).
          </div>
        )}

        {messages.map((msg) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[92%] rounded-lg px-3 py-2 leading-relaxed ${
                  isUser
                    ? "bg-terminal-blue/20 text-terminal-text border border-terminal-blue/40"
                    : "bg-terminal-elevated text-terminal-text border border-terminal-border"
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>
                {msg.actions && msg.actions.length > 0 && (
                  <div className="mt-1.5">
                    {msg.actions.map((action, idx) => (
                      <ActionBadge key={`${msg.id}-act-${idx}`} action={action} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {sending && (
          <div
            className="flex items-center gap-2 text-xs text-terminal-muted"
            role="status"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin text-terminal-purple" />
            <span>FinAlly is thinking…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <div
          role="alert"
          className="border-t border-terminal-red/30 bg-terminal-red/10 px-3 py-1.5 text-xs text-terminal-red"
        >
          {error}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 border-t border-terminal-border p-2.5"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={sending}
          placeholder="Ask FinAlly or place a trade…"
          aria-label="Chat message"
          className="flex-1 rounded border border-terminal-border bg-terminal-bg px-2.5 py-1.5 text-xs text-terminal-text placeholder:text-terminal-muted focus:border-terminal-purple focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          aria-label="Send message"
          className="flex items-center gap-1 rounded bg-terminal-purple px-3 py-1.5 text-xs font-semibold text-white hover:bg-terminal-purple/90 disabled:opacity-40"
        >
          <Send className="h-3.5 w-3.5" />
          <span>Send</span>
        </button>
      </form>
    </aside>
  );
}
