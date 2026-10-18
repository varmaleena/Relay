import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
test("mocked receiver rejects absent staff session and denied queue", async ({
  page,
}) => {
  await page.goto("/tests/receiver.fixture.html?mode=no-session");
  await expect(page.getByText(en.receiverAccess)).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.receiverReviewDecision }),
  ).toHaveCount(0);
  await page.goto("/tests/receiver.fixture.html?mode=denied");
  await expect(page.getByRole("alert")).toContainText(en.receiverDenied);
});
test("mocked receiver decision is explicit version-bound and reason guarded", async ({
  page,
}) => {
  await page.goto("/tests/receiver.fixture.html");
  await page.getByRole("button", { name: /RLY-STAFF-FIXTURE/ }).click();
  await expect(page.getByText("INR45000")).toBeVisible();
  await page.getByLabel(en.receiverAction).selectOption("reject");
  await expect(
    page.getByRole("button", { name: en.receiverReviewDecision }),
  ).toBeDisabled();
  await page
    .getByLabel(en.receiverReasonRequired)
    .fill("Synthetic duplicate report");
  await page.getByRole("button", { name: en.receiverReviewDecision }).click();
  await expect(page.getByRole("dialog")).toContainText("version 4");
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
  await page
    .getByRole("button", { name: en.receiverConfirmAction })
    .evaluate((button) => {
      (button as HTMLButtonElement).click();
      (button as HTMLButtonElement).click();
    });
  await expect(page.getByRole("status")).toContainText(
    en.receiverDecisionSaved,
  );
  const actions = JSON.parse(
    (await page.locator("#fixture-actions").textContent()) || "[]",
  );
  expect(actions).toHaveLength(1);
  expect(actions[0].body).toMatchObject({
    action: "reject",
    packetVersion: 4,
    reason: "Synthetic duplicate report",
  });
});
test("mocked receiver missing-info and stale guards; English Hindi accessibility", async ({
  page,
}, info) => {
  await page.goto("/tests/receiver.fixture.html");
  await page.getByRole("button", { name: /RLY-STAFF-FIXTURE/ }).click();
  await page.getByLabel(en.receiverAction).selectOption("request_info");
  await expect(
    page.getByRole("button", { name: en.receiverReviewDecision }),
  ).toBeDisabled();
  await page.getByRole("checkbox", { name: "Transaction reference" }).check();
  await expect(
    page.getByRole("button", { name: en.receiverReviewDecision }),
  ).toBeEnabled();
  for (const language of ["en", "hi"]) {
    await page
      .getByRole("combobox", { name: "Language", exact: true })
      .selectOption(language);
    const serious = (
      await new AxeBuilder({ page }).analyze()
    ).violations.filter((v) =>
      ["critical", "serious"].includes(v.impact || ""),
    );
    expect(serious).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await mkdir(".tmp/ui-review", { recursive: true });
    await page.screenshot({
      path: `.tmp/ui-review/receiver-mocked-${language}-${info.project.name}.png`,
      fullPage: true,
    });
  }
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("en");
  await page.goto("/tests/receiver.fixture.html?mode=stale");
  await page.getByRole("button", { name: /RLY-STAFF-FIXTURE/ }).click();
  await expect(
    page.getByRole("button", { name: en.receiverReviewDecision }),
  ).toBeDisabled();
});
