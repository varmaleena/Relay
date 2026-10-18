import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const metrics = async (page: import("@playwright/test").Page) =>
  JSON.parse((await page.locator("#voice-metrics").textContent()) || "{}");
test("mocked late microphone permission after End never starts audio or a socket", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html?mode=late-permission");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await page.getByRole("button", { name: en.voiceEnd, exact: true }).click();
  await expect.poll(async () => (await metrics(page)).stoppedTracks).toBe(1);
  expect(await metrics(page)).toMatchObject({ openedContexts: 0, sockets: 0 });
});
test("mocked voice starts explicitly, captions, mutes, interrupts and closes audio", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html");
  expect((await metrics(page)).openedContexts).toBe(0);
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.listening, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Synthetic caption only.")).toBeVisible();
  await page.getByRole("button", { name: "Fixture microphone frame" }).click();
  await page.getByRole("button", { name: en.voiceMute }).click();
  await page.getByRole("button", { name: "Fixture microphone frame" }).click();
  expect((await metrics(page)).audioFrames).toBe(1);
  await page.getByRole("button", { name: "Fixture interruption" }).click();
  expect((await metrics(page)).flushes).toBeGreaterThan(0);
  await page.getByLabel(en.voiceTextLabel).fill("Synthetic typed turn");
  await page
    .getByRole("button", { name: en.voiceSendText, exact: true })
    .click();
  await page.getByRole("button", { name: en.voiceEnd, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.ended, { exact: true }),
  ).toBeVisible();
  expect(await metrics(page)).toMatchObject({
    authExact: true,
    starts: 1,
    texts: 1,
    ends: 1,
    pongs: 1,
    closedContexts: 2,
  });
});
test("mocked voice resumes network loss at most three times, forbidden never retries", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.listening, { exact: true }),
  ).toBeVisible();
  for (let index = 0; index < 3; index++) {
    await page.getByRole("button", { name: "Fixture network loss" }).click();
    await expect(
      page.getByText(en.voiceStates.reconnecting, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(en.voiceStates.listening, { exact: true }),
    ).toBeVisible({ timeout: 6000 });
  }
  await page.getByRole("button", { name: "Fixture network loss" }).click();
  await expect(page.getByRole("alert")).toContainText(en.voiceFallback);
  expect((await metrics(page)).sockets).toBe(4);
  await page.goto("/tests/voice.fixture.html");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.listening, { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Fixture forbidden" }).click();
  await expect(page.getByRole("alert")).toContainText(en.voiceFallback);
  expect((await metrics(page)).sockets).toBe(1);
});
test("review handoff uses only user captions and never sends automatically", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.listening, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Fixture spoken statement", exact: true })
    .click();
  await page
    .getByRole("button", { name: en.voiceReviewText, exact: true })
    .click();
  await expect
    .poll(async () => (await metrics(page)).reviewedText)
    .toBe("Synthetic spoken amount INR45000.");
  expect((await metrics(page)).texts).toBe(0);
  await expect.poll(async () => (await metrics(page)).stoppedTracks).toBe(1);
});

test("server failure offers text fallback and releases microphone", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(
    page.getByText(en.voiceStates.listening, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Fixture server failure", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(en.voiceFallback);
  await expect.poll(async () => (await metrics(page)).stoppedTracks).toBe(1);
  await expect(
    page.getByRole("button", { name: en.voiceMute, exact: true }),
  ).toHaveCount(0);
});

test("mocked unavailable and microphone permission failure keep typing accessible in Hindi", async ({
  page,
}) => {
  await page.goto("/tests/voice.fixture.html?mode=unavailable");
  await expect(
    page.getByRole("button", { name: en.voiceStart, exact: true }),
  ).toBeDisabled();
  expect((await metrics(page)).openedContexts).toBe(0);
  await page.goto("/tests/voice.fixture.html?mode=permission");
  await page.getByRole("button", { name: en.voiceStart, exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(en.voiceFallback);
  expect((await metrics(page)).sockets).toBe(0);
  for (const language of ["en", "hi"]) {
    await page
      .getByRole("combobox", { name: "Fixture language" })
      .selectOption(language);
    expect(
      (await new AxeBuilder({ page }).analyze()).violations.filter((v) =>
        ["critical", "serious"].includes(v.impact || ""),
      ),
    ).toEqual([]);
  }
});
