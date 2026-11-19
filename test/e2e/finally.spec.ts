import { expect, test } from "@playwright/test";

const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

test.describe.serial("FinAlly E2E Trading Workstation", () => {
  test("1. Fresh start: default watchlist, $10k cash, live streaming prices", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
    await expect(page.getByTestId("header-total-value")).toHaveText("$10,000.00");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    for (const ticker of DEFAULT_TICKERS) {
      const row = page.getByTestId(`watchlist-row-${ticker}`);
      await expect(row).toBeVisible();
      await expect(row).toContainText("$");
    }

    // Confirm ticks accumulate in MainChart from live SSE stream
    await expect(page.getByLabel("Main Price Chart")).toContainText("TICKS:");
    await expect(async () => {
      const text = await page.getByLabel("Main Price Chart").innerText();
      const match = text.match(/TICKS:\s*(\d+)/);
      expect(Number(match?.[1] ?? 0)).toBeGreaterThanOrEqual(2);
    }).toPass({ timeout: 6000 });
  });

  test("2. Watchlist CRUD: add and remove a ticker", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    // Add PYPL
    const addInput = page.getByLabel("Add ticker to watchlist");
    await addInput.fill("PYPL");
    await page.getByRole("button", { name: "Add ticker" }).click();

    const pyplRow = page.getByTestId("watchlist-row-PYPL");
    await expect(pyplRow).toBeVisible();
    await expect(pyplRow).toContainText("$");

    // Remove PYPL
    await page.getByRole("button", { name: "Remove PYPL" }).click();
    await expect(pyplRow).toBeHidden();
  });

  test("3. Buy shares: cash decreases, position appears, heatmap updates", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    // Click AAPL row and buy 5 shares
    await page.getByTestId("watchlist-row-AAPL").click();
    await expect(page.getByTestId("main-chart-ticker")).toHaveText("AAPL");

    const qtyInput = page.getByLabel("Trade quantity");
    await qtyInput.fill("5");
    await page.getByRole("button", { name: "Buy" }).click();

    await expect(page.getByText(/BUY 5 AAPL filled/i)).toBeVisible();

    // Cash should decrease below $10,000.00
    await expect(page.getByTestId("header-cash")).not.toHaveText("$10,000.00");

    // Position row appears in Positions table
    const positionsSection = page.getByLabel("Positions");
    await expect(positionsSection).toContainText("AAPL");
    await expect(positionsSection).toContainText("5");

    // Heatmap tile renders for AAPL
    await expect(page.getByTestId("heatmap-grid")).toContainText("AAPL");
  });

  test("4. Sell shares: partial sell updates quantity, full sell removes position", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    const cashBeforeText = await page.getByTestId("header-cash").innerText();
    const cashBefore = Number(cashBeforeText.replace(/[$,]/g, ""));

    // Partial sell 2 AAPL
    await page.getByLabel("Trade ticker").fill("AAPL");
    await page.getByLabel("Trade quantity").fill("2");
    await page.getByRole("button", { name: "Sell" }).click();

    await expect(page.getByText(/SELL 2 AAPL filled/i)).toBeVisible();
    await expect(async () => {
      const cashAfterText = await page.getByTestId("header-cash").innerText();
      const cashAfter = Number(cashAfterText.replace(/[$,]/g, ""));
      expect(cashAfter).toBeGreaterThan(cashBefore);
    }).toPass();

    // Full sell remaining 3 AAPL
    await page.getByLabel("Trade quantity").fill("3");
    await page.getByRole("button", { name: "Sell" }).click();

    await expect(page.getByText(/SELL 3 AAPL filled/i)).toBeVisible();
    await expect(page.getByLabel("Positions")).toContainText("No open positions yet");
  });

  test("5. Portfolio visualization: heatmap colors and P&L chart data points", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    // Buy MSFT and NVDA to create multi-tile heatmap and multiple snapshots
    await page.getByLabel("Trade ticker").fill("MSFT");
    await page.getByLabel("Trade quantity").fill("2");
    await page.getByRole("button", { name: "Buy" }).click();
    await expect(page.getByText(/BUY 2 MSFT filled/i)).toBeVisible();

    await page.getByLabel("Trade ticker").fill("NVDA");
    await page.getByLabel("Trade quantity").fill("1");
    await page.getByRole("button", { name: "Buy" }).click();
    await expect(page.getByText(/BUY 1 NVDA filled/i)).toBeVisible();

    const heatmap = page.getByTestId("heatmap-grid");
    await expect(heatmap).toContainText("MSFT");
    await expect(heatmap).toContainText("NVDA");

    // Verify tiles have explicit backgroundColor style
    const tileBg = await heatmap
      .locator("button")
      .first()
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(tileBg).not.toBe("rgba(0, 0, 0, 0)");

    // P&L chart shows >= 3 snapshot data points and renders a canvas
    const pnlSection = page.getByLabel("Portfolio P&L Chart");
    await expect(async () => {
      const text = await pnlSection.innerText();
      const match = text.match(/\((\d+)\s+pts\)/);
      expect(Number(match?.[1] ?? 0)).toBeGreaterThanOrEqual(3);
    }).toPass();
    await expect(pnlSection.locator("canvas").first()).toBeVisible();
  });

  test("6. AI chat (LLM_MOCK=true): executes trade and displays failed action badge", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    const chatSection = page.getByLabel("AI Copilot Chat");
    const chatInput = page.getByLabel("Chat message");

    // Execute buy via chat
    await chatInput.fill("buy 3 GOOGL");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(chatSection).toContainText(/Buying 3 shares of GOOGL/i);
    await expect(chatSection).toContainText(/BUY 3 GOOGL @ \$/);
    await expect(page.getByLabel("Positions")).toContainText("GOOGL");

    // Trigger failed trade via chat (insufficient cash)
    await chatInput.fill("buy 99999 GOOGL");
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(chatSection).toContainText("Insufficient cash");
  });

  test("7. SSE resilience: recovers after stream interruption", async ({ page }) => {
    let blockStream = false;

    await page.route("**/api/stream/prices*", async (route) => {
      if (blockStream) {
        await route.abort("failed");
      } else {
        await route.continue();
      }
    });

    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("LIVE");

    // Simulate network drop and reload/reconnect cycle
    blockStream = true;
    await page.reload();
    await expect(page.getByTestId("connection-status")).not.toContainText("LIVE");

    // Restore stream; EventSource auto-retries per retry: 1000
    blockStream = false;
    await expect(page.getByTestId("connection-status")).toContainText("LIVE", {
      timeout: 10_000,
    });
    await expect(page.getByTestId("watchlist-row-AAPL")).toContainText("$");
  });
});
