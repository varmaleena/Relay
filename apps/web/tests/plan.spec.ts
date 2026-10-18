import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

// Exactly one explicit planning request. One authenticated real confirmed-facts patch
// avoids extra inference and leaves room in the unchanged read budget.
test("real draft plan sources stale guard and responsive view", async ({
  page,
}, info) => {
  test.skip(
    process.env.RELAY_PLAN_E2E !== "1",
    "Live planning requires scoped opt-in.",
  );
  test.skip(
    info.project.name !== "desktop",
    "One planning request only; resize this case for mobile.",
  );
  test.setTimeout(150000);
  await page.goto("/");
  await page.getByRole("button", { name: en.startAction }).click();
  await page.getByRole("button", { name: en.consentAction }).click();
  await expect(
    page.getByRole("heading", { name: en.factsTitle }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: en.planBuild })).toBeDisabled();
  async function edit(
    label: string,
    key: string,
    value: string,
    select = false,
  ) {
    await page
      .getByRole("button", { name: `${en.edit} ${label}`, exact: true })
      .click();
    const input = page.locator(`[id="fact-${key}"]`);
    if (select) await input.selectOption(value);
    else await input.fill(value);
    await page.getByRole("button", { name: en.save, exact: true }).click();
    await expect(input).not.toBeVisible();
  }
  await page.evaluate(async () => {
    const path = "/src/lib/connection.ts";
    const { api } = await import(/* @vite-ignore */ path);
    const caseId = decodeURIComponent(location.pathname.split("/")[2]);
    await api.E4({
      caseId,
      body: {
        source: "confirmed",
        ifRevision: 0,
        facts: {
          country: {
            value: "IN",
            provenance: { source: "confirmed", confidence: 1 },
          },
          payment: {
            method: "upi",
            amount: { value: "45000", currency: "INR" },
            timestamp: new Date(Date.now() - 30 * 60000).toISOString(),
            authorizedByVictim: true,
            recipientIdentifier: {
              type: "upi_id",
              value: "safe.verify@fakebank",
            },
          },
          contact: { channel: "phone" },
          ongoingContact: false,
          victimBank: "Fictional Test Bank",
        },
      },
    });
  });
  await page.reload();
  await expect(page.getByRole("button", { name: en.planBuild })).toBeEnabled();
  const preview = page.getByRole("checkbox", { name: en.planPreviewChoice });
  await expect(preview).not.toBeChecked();
  await preview.check();
  await page.getByRole("button", { name: en.planBuild }).click();
  await expect(page).toHaveURL(/\/plan$/, { timeout: 60000 });
  await expect(page.getByText(en.planDraftNotice)).toBeVisible();
  await expect(page.locator(".plan-stations > li")).toHaveCount(3);
  await expect(page.locator(".plan-stations")).toContainText("1930");
  await expect(
    page.locator('.plan-stations a[href="https://www.cybercrime.gov.in/"]'),
  ).toBeVisible();
  await expect(page.locator(".plan-source-list details")).not.toHaveCount(0);
  await page.locator(".plan-stations details summary").first().click();
  await mkdir(".tmp/ui-review", { recursive: true });
  for (const size of ["desktop", "mobile"]) {
    await page.setViewportSize(
      size === "desktop"
        ? { width: 1440, height: 1000 }
        : { width: 390, height: 844 },
    );
    for (const lang of ["en", "hi"]) {
      await page.locator(".language-label select").selectOption(lang);
      expect(
        (await new AxeBuilder({ page }).analyze()).violations.filter((v) =>
          ["serious", "critical"].includes(v.impact || ""),
        ),
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `.tmp/ui-review/plan-${lang}-${size}.png`,
        fullPage: true,
      });
    }
  }
  await page.getByRole("combobox", { name: hi.language }).selectOption("en");
  await page.reload();
  await expect(page.getByText(en.planDraftNotice)).toBeVisible();
  await page.getByRole("button", { name: en.planEdit }).click();
  await edit(en.bank, "victimBank", "Another Fictional Test Bank");
  await page.getByRole("button", { name: en.planView }).click();
  await expect(page.getByText(en.planStale)).toBeVisible();
  await page.getByRole("button", { name: en.delete, exact: true }).click();
  await page
    .getByRole("button", { name: en.deleteAction, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.startTitle }),
  ).toBeVisible();
});
