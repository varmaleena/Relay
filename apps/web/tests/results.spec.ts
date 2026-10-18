import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

test("results separates actual hosted checks from unmeasured comparisons", async ({
  page,
}) => {
  let writes = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/v1/"))
      writes++;
  });
  await page.goto("/results");
  await expect(
    page.getByRole("heading", { name: en.evalReleaseTitle, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(en.evalReleaseLimit, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(en.evalNoProductMeasurements, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.evalRunSmoke, exact: true }),
  ).toHaveCount(0);
  expect(writes).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("combobox", { name: en.language }).selectOption("hi");
  await expect(
    page.getByRole("heading", { name: hi.evalReleaseTitle, exact: true }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("home links to results without creating a case", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("link", { name: en.evalResultsLink, exact: true })
    .click();
  await expect(page).toHaveURL(/\/results$/);
  await page
    .getByRole("link", { name: en.evalReturnDemo, exact: true })
    .click();
  await expect(page).toHaveURL(/\/$/);
});
