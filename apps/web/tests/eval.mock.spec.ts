import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));
test("offline evaluation keeps all product systems unmeasured and labels calculator fixture", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html");
  await expect(
    page.getByRole("heading", { name: en.evalTitle, exact: true }),
  ).toBeVisible();
  await expect(page.getByText(en.evalNoProductMeasurements)).toBeVisible();
  await expect(page.getByText(en.evalCannedOnly)).toBeVisible();
  for (const name of Object.values(en.evalSystems))
    await expect(
      page.getByRole("columnheader", { name: new RegExp(String(name)) }),
    ).toBeVisible();
  const row = page.getByRole("row").filter({
    has: page.getByRole("rowheader", {
      name: en.evalMetrics.authorization_accuracy,
      exact: true,
    }),
  });
  await expect(row.getByText(en.evalNotMeasured, { exact: true })).toHaveCount(
    5,
  );
  await expect(row).toContainText("0.8");
  await expect(row).toContainText("20");
  await expect(row).toContainText("95% CI");
  const usage = page.getByRole("row").filter({
    has: page.getByRole("rowheader", {
      name: en.evalMetrics.cost_usd,
      exact: true,
    }),
  });
  await expect(usage).toContainText("Unknown = 20");
  await expect(
    page.getByRole("button", { name: en.evalRunSmoke, exact: true }),
  ).toHaveCount(0);
});
test("missing CI never appears as a measured numeric result", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html?mode=invalid-ci");
  await expect(page.getByText("0.9999", { exact: true })).toHaveCount(0);
  const row = page.getByRole("row").filter({
    has: page.getByRole("rowheader", {
      name: en.evalMetrics.authorization_accuracy,
      exact: true,
    }),
  });
  await expect(row.getByText(en.evalNotMeasured, { exact: true })).toHaveCount(
    6,
  );
});
test("failure gallery filters and opens only sanitized recorded failure details", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html");
  await page.getByLabel(en.evalSystem, { exact: true }).selectOption("relay");
  await expect(page.getByText(en.evalNoFailures)).toBeVisible();
  await page
    .getByLabel(en.evalSystem, { exact: true })
    .selectOption("offline_fixture");
  const first = page.locator(".eval-failures button").first();
  await expect(first).toBeVisible();
  await first.click();
  await expect(page.getByRole("dialog")).toContainText(en.evalFailureBoundary);
  await page.getByRole("button", { name: en.close, exact: true }).click();
  await expect(first).toBeFocused();
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
});
test("slice filtering shows only actually recorded slice metrics", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html");
  await page
    .getByLabel(en.evalSlice, { exact: true })
    .selectOption("language:en");
  await expect(page.getByRole("rowheader")).toHaveCount(1);
  await expect(page.getByRole("rowheader")).toHaveText(
    en.evalMetrics.authorization_accuracy,
  );
  await page.getByLabel(en.evalSlice, { exact: true }).selectOption("");
  await expect(page.getByRole("rowheader")).toHaveCount(15);
});
test("JSON export retains evidence metadata and strips hidden case properties", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html");
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: en.evalExportJson, exact: true })
    .click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe("relay-evaluation.json");
  const content = readFileSync((await download.path())!, "utf8");
  expect(content).not.toContain("PRIVATE-FIELD-MUST-NOT-EXPORT");
  const result = JSON.parse(content);
  expect(result.synthetic).toBe(true);
  expect(result.datasetVersion).toBe("synthetic-templates.v1");
  expect(
    result.systems.find((item: { system: string }) => item.system === "relay")
      .metrics,
  ).toEqual([]);
  const metric = result.systems
    .find((item: { system: string }) => item.system === "offline_fixture")
    .metrics.find(
      (item: { metric: string }) => item.metric === "authorization_accuracy",
    );
  expect(metric.n).toBe(20);
  expect(metric.ciLow).toBeGreaterThan(0);
});
test("run control requires admin and bounded injected executor then explicit confirmation", async ({
  page,
}) => {
  for (const mode of ["callback-only", "bad-bound"]) {
    await page.goto(`/tests/eval.fixture.html?mode=${mode}`);
    await expect(
      page.getByRole("button", { name: en.evalRunSmoke, exact: true }),
    ).toHaveCount(0);
  }
  await page.goto("/tests/eval.fixture.html?mode=admin");
  await page
    .getByRole("button", { name: en.evalRunSmoke, exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(en.evalSmokeConfirm);
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
  await page
    .getByRole("button", { name: en.evalConfirmSmoke, exact: true })
    .dblclick();
  await expect(page.getByText(en.evalRunRequested)).toBeVisible();
  const actions = JSON.parse(
    await page.locator("#fixture-actions").innerText(),
  );
  expect(actions).toEqual([
    {
      kind: "smoke",
      maxCases: 20,
      datasetVersion: "synthetic-templates.v1",
      systems: ["relay"],
    },
  ]);
  await expect(page.getByText(en.evalNoProductMeasurements)).toBeVisible();
});
test("stale report confirmation blocks execution and failures do not retry", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html?mode=stale");
  await page
    .getByRole("button", { name: en.evalRunSmoke, exact: true })
    .click();
  await page
    .locator("header button")
    .filter({ hasText: "Replace report" })
    .evaluate((button: HTMLButtonElement) => button.click());
  await expect(
    page.getByRole("button", { name: en.evalConfirmSmoke, exact: true }),
  ).toBeDisabled();
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
  await page.goto("/tests/eval.fixture.html?mode=admin-failed");
  await page
    .getByRole("button", { name: en.evalRunSmoke, exact: true })
    .click();
  await page
    .getByRole("button", { name: en.evalConfirmSmoke, exact: true })
    .click();
  await expect(page.getByText(en.evalRunFailed)).toBeVisible();
  expect(
    JSON.parse(await page.locator("#fixture-actions").innerText()),
  ).toHaveLength(1);
});
test("empty unavailable and non-synthetic reports fail visibly", async ({
  page,
}) => {
  await page.goto("/tests/eval.fixture.html?mode=empty");
  await expect(page.getByText(en.evalNoReport)).toBeVisible();
  await page.goto("/tests/eval.fixture.html?mode=failed");
  await expect(page.getByRole("alert")).toHaveText(en.evalLoadFailed);
  await page.goto("/tests/eval.fixture.html?mode=unsupported");
  await expect(page.getByRole("alert")).toHaveText(en.evalUnsupported);
  await expect(page.getByRole("table")).toHaveCount(0);
});
test("English and Hindi evaluation views pass axe and keep mobile page width", async ({
  page,
}, testInfo) => {
  await page.goto("/tests/eval.fixture.html");
  for (const language of ["en", "hi"]) {
    if (language === "hi")
      await page
        .getByRole("button", { name: "Switch language", exact: true })
        .click();
    await expect(
      page.getByRole("heading", {
        name: language === "hi" ? hi.evalTitle : en.evalTitle,
        exact: true,
      }),
    ).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await mkdir(".tmp/ui-review", { recursive: true });
    await page.screenshot({
      path: `.tmp/ui-review/eval-${testInfo.project.name}-${language}.png`,
      fullPage: true,
    });
  }
});
