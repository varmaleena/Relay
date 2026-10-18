import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));

// Opt in separately from the one-shot receipt test: this run makes exactly three
// new synthetic intake requests. It never opens or modifies a user's existing case.
test("three-turn intake retains amount currency recipient and confirmed corrections", async ({
  page,
}, info) => {
  test.skip(
    process.env.RELAY_MULTITURN_E2E !== "1",
    "Three-call live regression requires explicit opt-in.",
  );
  test.skip(
    info.project.name !== "desktop",
    "Avoid duplicate paid inference on the mobile project.",
  );
  test.setTimeout(150000);
  await mkdir(".tmp/ui-review", { recursive: true });
  await page.goto("/");
  await page.getByRole("button", { name: en.startAction }).click();
  await page.getByRole("button", { name: en.consentAction }).click();
  await expect(page).toHaveURL(/\/case\/.+\/intake/);
  await expect(
    page.getByRole("heading", { name: en.factsTitle }),
  ).toBeVisible();
  const turns = [
    "someone pretending to be my bank called me and asked me to transfer money.",
    "I am in India. I paid INR 45000 by UPI twenty minutes ago to safe.verify@fakebank. My fictional bank is Test Bank.",
    "INR.. I made the payment myself. The caller contacted me by phone. Contact has stopped. The reference is TEST0000000001.",
  ];
  const messages = [];
  const facts = page.locator(".facts-panel");
  const amount = page.locator(".fact-row").filter({ hasText: en.amount });
  const currency = page.locator(".fact-row").filter({ hasText: en.currency });
  const recipient = page.locator(".fact-row").filter({ hasText: en.recipient });
  const missingAmountQuestion =
    /\b(?:how much|what (?:was |is |exact )?(?:the )?amount|which currency|what currency)\b/i;
  for (let i = 0; i < turns.length; i++) {
    await page.getByRole("textbox", { name: en.messageLabel }).fill(turns[i]);
    await page.getByRole("button", { name: en.send, exact: true }).click();
    await expect(page.locator(".turn.assistant")).toHaveCount(i + 1, {
      timeout: 30000,
    });
    const reply = await page.locator(".turn.assistant").last().innerText();
    messages.push({ user: turns[i], reply });
    await writeFile(
      ".tmp/ui-review/multiturn-synthetic-transcript.json",
      JSON.stringify(messages, null, 2),
    );
    if (i >= 1) {
      await expect
        .poll(async () =>
          Number(
            ((await amount.locator(".fact-value").textContent()) || "").replace(
              /[^\d.]/g,
              "",
            ),
          ),
        )
        .toBe(45000);
      await expect(currency).toContainText("INR");
      await expect(recipient).toContainText("safe.verify@fakebank");
      expect(reply).not.toMatch(missingAmountQuestion);
    }
    if (i === 1) {
      await page
        .getByRole("button", { name: `${en.edit} ${en.bank}`, exact: true })
        .click();
      await page.locator("#fact-victimBank").fill("Northwind Test Bank");
      await page.getByRole("button", { name: en.save, exact: true }).click();
      await expect(facts).toContainText("Northwind Test Bank");
    }
  }
  await expect(facts).toContainText("Northwind Test Bank");
  await expect(facts).toContainText("TEST0000000001");
  await page.reload();
  await expect(page.locator(".turn.assistant")).toHaveCount(3);
  await expect(facts).toContainText("Northwind Test Bank");
  await expect
    .poll(async () =>
      Number(
        ((await amount.locator(".fact-value").textContent()) || "").replace(
          /[^\d.]/g,
          "",
        ),
      ),
    )
    .toBe(45000);
  await expect(currency).toContainText("INR");
  await expect(recipient).toContainText("safe.verify@fakebank");
  await page.screenshot({
    path: ".tmp/ui-review/multiturn-corrected-desktop.png",
    fullPage: true,
  });
  // All stored contents here are from this deliberately synthetic test, never user data.
  await writeFile(
    ".tmp/ui-review/multiturn-synthetic-transcript.json",
    JSON.stringify(messages, null, 2),
  );
  await page.getByRole("button", { name: en.delete, exact: true }).click();
  await page
    .getByRole("button", { name: en.deleteAction, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.startTitle }),
  ).toBeVisible();
});
