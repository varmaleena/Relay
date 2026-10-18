import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "*.spec.ts",
  timeout: 60000,
  workers: 1,
  outputDir: "../../.tmp/web-tests",
  use: { baseURL: "http://127.0.0.1:5173", headless: true },
  reporter: [["list"]],
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 } } },
  ],
});
