import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinAlly — AI Trading Workstation",
  description:
    "Live streaming market data, simulated portfolio trading, and AI copilot.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased bg-terminal-bg text-terminal-text">
        {children}
      </body>
    </html>
  );
}
