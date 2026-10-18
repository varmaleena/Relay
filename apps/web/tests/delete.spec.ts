import { test, expect } from "@playwright/test";
test("model-free create and delete transport", async ({ page }, info) => {
  test.skip(
    info.project.name !== "desktop",
    "Single model-free transport check.",
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Start by typing" }).click();
  await page
    .getByRole("button", { name: "I understand. Start report" })
    .click();
  await expect(page).toHaveURL(/\/case\/.+\/intake/);
  await expect(
    page.getByRole("heading", { name: "What we know so far" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete this report" }).click();
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "DELETE" &&
      new URL(r.url()).pathname.startsWith("/api/v1/cases/"),
  );
  await page
    .getByRole("button", { name: "Delete report", exact: true })
    .click();
  const result = await response;
  const code = result.ok() ? "none" : (await result.json()).code;
  console.log(`Delete transport status=${result.status()} code=${code}`);
  expect(result.status()).toBe(204);
  await expect(
    page.getByRole("heading", { name: "Were you just scammed?" }),
  ).toBeVisible();
});
