import { test, expect, type Download } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

// Real HTTP/Firebase/domain/MCP transport. Classifier/writer/verifier are explicitly
// synthetic test fixtures; this is not live-AI quality or latency evidence.
test("real M3 transport with synthetic model-stage fixtures", async ({
  page,
  context,
}, info) => {
  test.skip(
    process.env.RELAY_M3_TRANSPORT_E2E !== "1" ||
      process.env.RELAY_WORKER_DISABLED !== "1",
    "Root must explicitly enable the workerless synthetic-domain gate.",
  );
  test.skip(
    info.project.name !== "desktop",
    "One real fixture; resize it for mobile checks.",
  );
  test.setTimeout(180000);
  await mkdir(".tmp/ui-review", { recursive: true });
  await mkdir(".tmp/m3-fixture-runtime", { recursive: true });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:5173",
  });
  await page.goto("/");
  await page.getByRole("button", { name: en.startAction }).click();
  await page.getByRole("button", { name: en.consentAction }).click();
  await expect(
    page.getByRole("heading", { name: en.factsTitle }),
  ).toBeVisible();
  const caseId = decodeURIComponent(new URL(page.url()).pathname.split("/")[2]);
  const output = await promisify(execFile)(
    resolve(".venv/Scripts/python.exe"),
    [
      "-m",
      "scripts.seed_m3_browser_fixture",
      "--case-id",
      caseId,
      "--confirm-new-synthetic-case",
      "--worker-disabled",
    ],
    {
      cwd: process.cwd(),
      timeout: 60000,
      env: {
        ...process.env,
        FIRESTORE_EMULATOR_HOST: "127.0.0.1:8095",
        GCP_PROJECT_ID: "demo-relay-local",
        GOOGLE_CLOUD_PROJECT: "demo-relay-local",
        TMP: resolve(".tmp/m3-fixture-runtime"),
        TEMP: resolve(".tmp/m3-fixture-runtime"),
      },
    },
  );
  const seeded = JSON.parse(output.stdout.trim().split(/\r?\n/).at(-1)!);
  expect(seeded.providerCalls).toBe(0);
  expect(seeded.packetIds).toHaveLength(3);
  await writeFile(
    ".tmp/m3-transport-checkpoint.json",
    JSON.stringify({ caseId, seeded }),
  );
  // Local emulator auth state is private, ignored and excluded from source uploads.
  // Retain only for model-free recovery if a later browser assertion fails.
  await context.storageState({
    path: ".tmp/m3-browser-auth.json",
    indexedDB: true,
  });
  await page.reload();
  await page.getByRole("button", { name: en.planView }).click();
  await page.getByRole("button", { name: en.messagesReview }).click();
  await expect(page.locator(".recipient-tabs button")).toHaveCount(3);
  await page.locator(".recipient-tabs button").first().click();
  await expect(
    page.getByRole("heading", { name: en.institutionCopy }),
  ).toBeVisible();
  await page.locator(".simulation-delivery > summary").click();
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toBeEnabled();
  await page.getByRole("button", { name: en.messageApprove }).click();
  await expect(page.getByRole("dialog")).toContainText("Your bank");
  await expect(page.getByRole("dialog")).toContainText("Version 1");
  const approved = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/approve"),
  );
  await page.getByRole("button", { name: en.messageConfirmSend }).click();
  const response = await approved;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toEqual({
    confirm: true,
    confirmedRecipientId: "bank",
    packetVersion: 1,
  });
  const receipt = (await response.json()).delivery;
  await writeFile(
    ".tmp/m3-transport-checkpoint.json",
    JSON.stringify({ caseId, seeded, receipt }),
  );
  expect(receipt.simulated).toBe(true);
  expect(receipt.ticketRef).toMatch(/^SIM-/);
  expect(receipt.status).toBe("RECEIVED");
  await expect(page.getByText(new RegExp(receipt.ticketRef))).toBeVisible();
  await page.getByRole("button", { name: en.messageCopy }).click();
  await expect(page.getByText(en.messageCopied)).toBeVisible();
  const downloaded = new Promise<Download>((accept, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Browser PDF download not observed")),
      15000,
    );
    const observe = (surface: typeof page) =>
      surface.once("download", (download) => {
        clearTimeout(timer);
        accept(download);
      });
    context.pages().forEach(observe);
    context.once("page", observe);
  });
  await page.getByRole("button", { name: en.messageDownload }).click();
  const pdf = await downloaded;
  await pdf.saveAs(".tmp/ui-review/transport-fixture-message.pdf");
  expect(
    (await readFile(".tmp/ui-review/transport-fixture-message.pdf"))
      .subarray(0, 5)
      .toString(),
  ).toBe("%PDF-");
  for (const viewport of ["desktop", "mobile"]) {
    await page.setViewportSize(
      viewport === "desktop"
        ? { width: 1440, height: 1000 }
        : { width: 390, height: 844 },
    );
    for (const language of ["en", "hi"]) {
      await page.locator(".language-label select").selectOption(language);
      expect(
        (await new AxeBuilder({ page }).analyze()).violations.filter((item) =>
          ["serious", "critical"].includes(item.impact || ""),
        ),
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `.tmp/ui-review/transport-review-${language}-${viewport}.png`,
        fullPage: true,
      });
    }
  }
  await page.locator(".language-label select").selectOption("en");
  await page.getByRole("button", { name: en.openTracker }).click();
  await expect(page.getByText(new RegExp(receipt.ticketRef))).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.markRead }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: en.markRead }).first().click();
  await expect(page.locator(".notification-list .read")).not.toHaveCount(0);
  await page.screenshot({
    path: ".tmp/ui-review/transport-tracker-mobile.png",
    fullPage: true,
  });
  // Unload all polling, then let the unchanged rolling read window expire. This is
  // intentional rate-budget pacing, not application latency or a readiness sleep.
  await page.goto("/");
  await new Promise((resolve) => setTimeout(resolve, 61000));
  await page.goto(`/case/${encodeURIComponent(caseId)}/track`);
  await expect(page.getByText(new RegExp(receipt.ticketRef))).toBeVisible();
  await expect(page.locator(".notification-list .read")).not.toHaveCount(0);
  await page.goto(`/case/${encodeURIComponent(caseId)}/intake`);
  await page
    .getByRole("button", { name: `${en.edit} ${en.bank}`, exact: true })
    .click();
  await page
    .locator('[id="fact-victimBank"]')
    .fill("Another Fictional Test Bank");
  await page.getByRole("button", { name: en.save, exact: true }).click();
  await expect(page.locator('[id="fact-victimBank"]')).not.toBeVisible();
  await page.goto(
    `/case/${encodeURIComponent(caseId)}/packet/${encodeURIComponent(seeded.packetIds[1])}`,
  );
  await expect(page.getByText(en.messageStale)).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toBeDisabled();
  await page.getByRole("button", { name: en.delete, exact: true }).click();
  await page
    .getByRole("button", { name: en.deleteAction, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.startTitle }),
  ).toBeVisible();
  await writeFile(
    ".tmp/ui-review/m3-transport-result.json",
    JSON.stringify(
      {
        mode: seeded.fixtureMode,
        providerCalls: 0,
        realAuth: true,
        realHTTP: true,
        realDomain: true,
        realMCP: true,
        simulated: true,
        pdf: true,
        reload: true,
        inboxRead: true,
        staleBlocked: true,
        deleted: true,
      },
      null,
      2,
    ),
  );
});
