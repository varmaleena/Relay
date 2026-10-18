import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

test("real anonymous intake, correction, evidence, persistence and ownership", async ({
  page,
  context,
  request,
}, info) => {
  test.skip(
    process.env.RELAY_LIVE_E2E !== "1",
    "Live inference is explicitly opt-in; two bounded synthetic calls.",
  );
  test.skip(
    info.project.name !== "desktop",
    "One deliberate live run covers both viewport sizes without duplicating model charges.",
  );
  test.setTimeout(180000);
  await mkdir(".tmp/ui-review", { recursive: true });
  await page.goto("/");
  await page.getByRole("button", { name: en.startAction }).click();
  await page.getByRole("button", { name: en.consentAction }).click();
  await expect(page).toHaveURL(/\/case\/.+\/intake/, { timeout: 15000 });
  await expect(
    page.getByRole("heading", { name: en.factsTitle }),
  ).toBeVisible();
  const caseId = page.url().split("/case/")[1].split("/")[0];
  const paidAt = new Date(Date.now() - 20 * 60000).toISOString();
  await page
    .getByRole("textbox", { name: en.messageLabel })
    .fill(
      `Synthetic demo: I am in India. I paid INR 45000 by UPI at ${paidAt} to safe.verify@fakebank, reference TEST0000000001. A fake Test Bank security caller +91 90000 00000 asked me to send it. I made the payment myself. Contact has stopped. My fictional bank is Test Bank.`,
    );
  await page.getByRole("button", { name: en.send, exact: true }).click();
  await expect(page.locator(".turn.assistant")).toHaveCount(1, {
    timeout: 30000,
  });
  await expect(
    page.locator(".fact-row").filter({ hasText: en.amount }),
  ).toContainText("45,000");
  await page
    .getByRole("button", { name: `${en.edit} ${en.bank}`, exact: true })
    .click();
  await page.locator("#fact-victimBank").fill("Northwind Test Bank");
  await page.getByRole("button", { name: en.save, exact: true }).click();
  await expect(page.locator(".facts-panel")).toContainText(
    "Northwind Test Bank",
  );
  const receipt = await context.newPage();
  await receipt.setViewportSize({ width: 520, height: 350 });
  await receipt.setContent(
    `<html><body style="font:20px sans-serif;padding:25px;background:#fff;color:#172033"><h2>Synthetic payment receipt</h2><p>Test Bank | UPI transfer</p><p>Amount: INR 45000</p><p>Recipient: safe.verify@fakebank</p><p>Reference: TEST0000000001</p><p>Paid: ${paidAt}</p></body></html>`,
  );
  await receipt.screenshot({ path: ".tmp/ui-review/synthetic-receipt.png" });
  await receipt.close();
  await page
    .locator("#file")
    .setInputFiles(".tmp/ui-review/synthetic-receipt.png");
  await page.getByRole("button", { name: en.upload, exact: true }).click();
  await expect(
    page.locator(".evidence-row").filter({ hasText: "safe.verify@fakebank" }),
  ).toBeVisible({ timeout: 45000 });
  const upi = page
    .locator(".evidence-row")
    .filter({ hasText: "safe.verify@fakebank" });
  await upi.getByRole("button", { name: en.confirm, exact: true }).click();
  await expect(upi).toContainText(en.evidenceConfirmed);
  for (const language of ["en", "hi"] as const) {
    await page
      .getByRole("combobox", {
        name: language === "en" ? en.language : en.language,
      })
      .selectOption(language);
    for (const viewport of [
      { name: "desktop", width: 1440, height: 1000 },
      { name: "mobile", width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await page.screenshot({
        path: `.tmp/ui-review/intake-${language}-${viewport.name}.png`,
        fullPage: true,
      });
      const violations = (await new AxeBuilder({ page }).analyze()).violations;
      expect(
        violations.filter((v) =>
          ["critical", "serious"].includes(v.impact || ""),
        ),
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.getByRole("combobox", { name: hi.language }).selectOption("en");
  await page.reload();
  await expect(page.locator(".facts-panel")).toContainText(
    "Northwind Test Bank",
  );
  await expect(page.locator(".turn.assistant")).toHaveCount(1);
  // A separately issued real anonymous Firebase emulator identity must be denied.
  const signup = await request.post(
    "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-emulator-key",
    { data: { returnSecureToken: true } },
  );
  expect(signup.ok()).toBe(true);
  const outsider = await signup.json();
  const forbidden = await request.get(
    `http://127.0.0.1:8000/api/v1/cases/${caseId}`,
    { headers: { Authorization: `Bearer ${outsider.idToken}` } },
  );
  expect([403, 404]).toContain(forbidden.status());
  await page.getByRole("button", { name: en.delete, exact: true }).click();
  await page
    .getByRole("button", { name: en.deleteAction, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.startTitle }),
  ).toBeVisible();
});
