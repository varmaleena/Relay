import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

test("start and consent are clear, accessible and responsive", async ({
  page,
}, info) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Were you just scammed?" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Talk to Relay" }),
  ).toBeDisabled();
  const violations = (await new AxeBuilder({ page }).analyze()).violations;
  expect(
    violations.filter((v) => ["critical", "serious"].includes(v.impact || "")),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await mkdir(".tmp/web", { recursive: true });
  await page.screenshot({
    path: `.tmp/web/start-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Start by typing" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "I understand. Start report" }),
  ).toBeVisible();
  const modalViolations = (await new AxeBuilder({ page }).analyze()).violations;
  expect(
    modalViolations.filter((v) =>
      ["critical", "serious"].includes(v.impact || ""),
    ),
  ).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start by typing" }),
  ).toBeFocused();
  await mkdir(".tmp/ui-review", { recursive: true });
  await page.screenshot({
    path: `.tmp/ui-review/start-en-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("combobox", { name: "Language" }).selectOption("hi");
  await expect(
    page.getByRole("heading", { name: hi.startTitle }),
  ).toBeVisible();
  await page.screenshot({
    path: `.tmp/ui-review/start-hi-${info.project.name}.png`,
    fullPage: true,
  });
  const hindiViolations = (await new AxeBuilder({ page }).analyze()).violations;
  expect(
    hindiViolations.filter((v) =>
      ["critical", "serious"].includes(v.impact || ""),
    ),
  ).toEqual([]);
});
