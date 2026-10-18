import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));

test("model-free money editor requires explicit currency and preserves decimal precision", async ({
  page,
}, info) => {
  test.skip(
    info.project.name !== "desktop",
    "One real transport test; no inference calls.",
  );
  await page.goto("/");
  await page.getByRole("button", { name: en.startAction }).click();
  await page.getByRole("button", { name: en.consentAction }).click();
  await expect(
    page.getByRole("heading", { name: en.factsTitle }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: `${en.edit} ${en.amount}`, exact: true })
    .click();
  const exact = "123456789012.12345678";
  const amount = page.getByRole("textbox", { name: en.amount, exact: true });
  const currency = page.getByRole("combobox", {
    name: en.currency,
    exact: true,
  });
  await expect(currency).toHaveValue("");
  await amount.fill(exact);
  await expect(
    page.getByRole("button", { name: en.save, exact: true }),
  ).toBeDisabled();
  await currency.selectOption("GBP");
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      new URL(response.url()).pathname.endsWith("/facts"),
  );
  await page.getByRole("button", { name: en.save, exact: true }).click();
  const response = await saved;
  const problemCode = response.ok() ? "none" : (await response.json()).code;
  expect(response.status(), `Money update problem code: ${problemCode}`).toBe(
    200,
  );
  const body = response.request().postDataJSON();
  expect(body.facts.payment.amount).toEqual({ value: exact, currency: "GBP" });
  await expect(amount).not.toBeVisible();
  await page.reload();
  const row = page.locator(".fact-row").filter({ hasText: en.amount });
  await expect
    .poll(async () =>
      (await row.locator(".fact-value").innerText()).replace(/[^\d.]/g, ""),
    )
    .toBe(exact);
  await expect(
    page.locator(".fact-row").filter({ hasText: en.currency }),
  ).toContainText("GBP");
  await page
    .getByRole("button", { name: `${en.edit} ${en.currency}`, exact: true })
    .click();
  await expect(amount).toHaveValue(exact);
  await expect(currency).toHaveValue("GBP");
  await page.getByRole("button", { name: en.delete, exact: true }).click();
  await page
    .getByRole("button", { name: en.deleteAction, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.startTitle }),
  ).toBeVisible();
});
