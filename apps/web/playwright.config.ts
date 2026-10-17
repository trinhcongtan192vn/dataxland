// Kịch bản end-to-end (spec 06 §11) trên stack local: `make up && make seed-local`, rồi `make e2e`.
// Cần Firebase Auth Emulator, API, Cube, Dagster đang chạy; tài khoản demo từ `ops/seed_users.py`.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
