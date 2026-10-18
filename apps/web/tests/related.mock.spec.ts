import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

test("related review requires explicit confirmation and prevents duplicate clicks", async ({
  page,
}) => {
  await page.goto("/tests/related.fixture.html");
  await expect(page.getByText(en.relatedBoundary)).toBeVisible();
  await expect(page.getByText("96%", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: en.relatedYes, exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("RLY-SYNTHETIC-A");
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
  await page
    .getByRole("button", { name: en.relatedConfirm, exact: true })
    .evaluate((button) => {
      (button as HTMLButtonElement).click();
      (button as HTMLButtonElement).click();
    });
  await expect(page.getByText(en.relatedSaved)).toBeVisible();
  const calls = JSON.parse(
    (await page.locator("#fixture-actions").textContent())!,
  );
  expect(calls).toHaveLength(1);
  expect(calls[0].body).toEqual({ decision: "related" });
  expect(calls[0].idempotencyKey).toMatch(/^[a-f0-9-]{36}$/);
});

test("stale proof needs manual GET refresh and never retries POST", async ({
  page,
}) => {
  await page.goto("/tests/related.fixture.html?mode=stale");
  await page.getByRole("button", { name: en.relatedNo, exact: true }).click();
  await page
    .getByRole("button", { name: en.relatedConfirm, exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(en.relatedStale);
  await expect(page.locator("#fixture-reads")).toHaveText("1");
  await expect(page.locator("#fixture-actions")).toContainText("not_related");
  await page.getByRole("button", { name: en.relatedRefresh }).click();
  await expect(page.locator("#fixture-reads")).toHaveText("2");
  expect(
    JSON.parse((await page.locator("#fixture-actions").textContent())!),
  ).toHaveLength(1);
});

test("safe GET handles429; denied and empty states stay honest", async ({
  page,
}) => {
  await page.goto("/tests/related.fixture.html?mode=rate");
  await expect(page.locator("#fixture-reads")).toHaveText("2");
  await expect(
    page.getByRole("button", { name: en.relatedYes, exact: true }),
  ).toBeVisible();
  await page.goto("/tests/related.fixture.html?mode=denied");
  await expect(page.getByRole("alert")).toContainText(en.relatedError);
  await expect(
    page.getByRole("button", { name: en.relatedYes, exact: true }),
  ).toHaveCount(0);
  await page.goto("/tests/related.fixture.html?mode=empty");
  await expect(page.getByText(en.relatedEmpty)).toBeVisible();
});

test("English Hindi related report view is responsive and accessible", async ({
  page,
}) => {
  await page.goto("/tests/related.fixture.html");
  for (const [language, strings] of [
    ["en", en],
    ["hi", hi],
  ] as const) {
    await page
      .getByRole("combobox", { name: "Language", exact: true })
      .selectOption(language);
    await expect(
      page.getByRole("heading", { name: strings.relatedTitle }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const serious = (
      await new AxeBuilder({ page }).analyze()
    ).violations.filter((v) =>
      ["serious", "critical"].includes(v.impact || ""),
    );
    expect(serious).toEqual([]);
  }
});
