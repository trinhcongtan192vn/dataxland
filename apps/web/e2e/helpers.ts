import { type Page, expect } from "@playwright/test";

export const PASSWORD = "DataxLand@2026";
export const API = process.env.E2E_API_URL ?? "http://localhost:8000";
export const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

export const USERS = {
  lead: "lead@dataxland.local",
  ownerSeller: "owner.seller@demo.local",
  memberSeller: "member.seller@demo.local",
  ownerAgency: "owner.agency@demo.local",
  partner: "am@agency.local",
} as const;

export async function login(page: Page, email: string, next = "/app"): Promise<void> {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await page.waitForURL(/\/login/);
}

/** Tin email mới nhất gửi tới địa chỉ (Mailpit ở local). */
export async function latestMail(email: string, subjectPart: string): Promise<string> {
  for (let i = 0; i < 30; i++) {
    const r = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`);
    const body = (await r.json()) as { messages: { ID: string; Subject: string }[] };
    const m = body.messages.find((x) => x.Subject.includes(subjectPart));
    if (m) {
      const full = (await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json()) as { Text: string };
      return full.Text;
    }
    await new Promise((res) => setTimeout(res, 2000));
  }
  throw new Error(`Không thấy email "${subjectPart}" gửi ${email}`);
}

export async function expectNoErrors(page: Page): Promise<void> {
  await expect(page.getByRole("alert")).toHaveCount(0);
}
