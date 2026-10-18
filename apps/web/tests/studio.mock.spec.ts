import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
test("mocked Studio access and absent canonical publication remain blocked", async ({
  page,
}) => {
  await page.goto("/tests/studio.fixture.html?mode=no-session");
  await expect(page.getByText(en.studioAccess)).toBeVisible();
  await page.goto("/tests/studio.fixture.html");
  await expect(page.getByText(en.studioPublicationUnavailable)).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.studioPublish, exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "bank", exact: true }).click();
  await expect(page.getByText("Synthetic source evidence")).toBeVisible();
  await page
    .getByRole("button", { name: en.studioAccept, exact: true })
    .click();
  await expect(page.locator("#fixture-actions")).toContainText(
    '"ifRevision":2',
  );
  await expect(page.locator("#fixture-actions")).not.toContainText("packDraft");
});
test("mocked Studio publication requires human checklist and explicit version confirmation", async ({
  page,
}) => {
  await page.goto("/tests/studio.fixture.html?mode=canonical");
  await page.getByLabel(en.studioReviewerName).fill("Synthetic Reviewer");
  await page
    .getByLabel(en.studioPublishNotes)
    .fill("Fixture review only, not an actual review.");
  for (const text of Object.values(en.studioChecks))
    await page.getByLabel(text as string, { exact: true }).check();
  await page
    .getByRole("button", { name: en.studioPublish, exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("fixture-pack");
  await expect(page.locator("#fixture-actions")).toHaveText("[]");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: en.studioPublish, exact: true })
    .click();
  await expect(page.locator("#fixture-actions")).toContainText(
    '"ifRevision":2',
  );
  await expect(page.locator("#fixture-actions")).toContainText(
    '"sourcesChecked":true',
  );
  await expect(
    page.getByRole("status").filter({ hasText: "fixture-pack" }),
  ).toContainText("fixture-pack");
  await page
    .getByRole("button", { name: en.studioRetire, exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: en.studioRetireConfirm, exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel(en.studioRetireReason)
    .fill("Synthetic retired fixture");
  await page
    .getByRole("button", { name: en.studioRetireConfirm, exact: true })
    .click();
  await expect(page.locator("#fixture-actions")).toContainText(
    "Synthetic retired fixture",
  );
});
test("mocked Studio responsive English Hindi accessibility", async ({
  page,
}) => {
  await page.goto("/tests/studio.fixture.html");
  await expect(page.getByText(en.studioPublicationUnavailable)).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "पैक स्टूडियो",
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("mocked Studio source selection feeds five-pass build without automatic publication", async ({
  page,
}) => {
  await page.goto("/tests/studio.fixture.html");
  await page
    .getByLabel(en.studioSourceTitle, { exact: true })
    .fill("Synthetic source");
  await page
    .getByLabel(en.studioPublisher, { exact: true })
    .fill("Synthetic publisher");
  await page
    .getByLabel(en.studioUrl, { exact: true })
    .fill("https://example.org/source");
  await page
    .getByRole("button", { name: en.studioAddSource, exact: true })
    .click();
  await page
    .getByRole("button", { name: en.studioExtractSource, exact: true })
    .click();
  await page.getByLabel(en.studioUseSource).check();
  await page.getByLabel(en.studioPackName).fill("Synthetic pack");
  await page.getByLabel(en.studioJurisdiction).fill("IN");
  await page.getByRole("button", { name: en.studioBuild, exact: true }).click();
  await expect(page.locator("#fixture-actions")).toContainText(
    '"sourceIds":["src_fixture"]',
  );
  await page.getByRole("button", { name: "bank", exact: true }).click();
  await expect(
    page.getByText("Synthetic exact source passage", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("#fixture-actions")).not.toContainText("packDraft");
});
