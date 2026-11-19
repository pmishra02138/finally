"use client";

import { FormEvent, useState } from "react";
import { Lock } from "lucide-react";

interface PasswordModalProps {
  open: boolean;
  error: string | null;
  onSubmit: (password: string) => void;
}

export function PasswordModal({ open, error, onSubmit }: PasswordModalProps) {
  const [value, setValue] = useState("");

  if (!open) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    onSubmit(value);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Access Password Required"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-terminal-border bg-terminal-panel p-5 shadow-2xl"
      >
        <div className="flex items-center gap-2 text-terminal-yellow">
          <Lock className="h-4 w-4" />
          <h2 className="text-sm font-semibold">FinAlly Access Password</h2>
        </div>
        <p className="mt-2 text-xs text-terminal-muted">
          This deployment is protected by <code className="font-mono">APP_PASSWORD</code>.
          Enter the password to connect.
        </p>

        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Enter password"
          autoFocus
          className="mt-3 w-full rounded border border-terminal-border bg-terminal-bg px-3 py-2 text-sm text-terminal-text focus:border-terminal-purple focus:outline-none"
        />

        {error && (
          <p role="alert" className="mt-2 text-xs text-terminal-red">
            {error}
          </p>
        )}

        <button
          type="submit"
          className="mt-4 w-full rounded bg-terminal-purple py-2 text-xs font-semibold text-white hover:bg-terminal-purple/90"
        >
          Unlock Terminal
        </button>
      </form>
    </div>
  );
}
