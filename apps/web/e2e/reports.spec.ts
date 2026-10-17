// Kịch bản spec 06 §11 (báo cáo tuần): dựng → viết nhận định → duyệt → gửi → ghi nhận mở; số cũ giữ nguyên.
import { expect, test } from "@playwright/test";
import { API, USERS, latestMail, login } from "./helpers";

const INTERNAL = {
  Authorization: `Bearer ${process.env.INTERNAL_API_TOKEN ?? "local-internal-token"}`,
  "X-Service": "dagster",
};

test.describe.serial("báo cáo tuần", () => {
  let reportId = "";

  test("FR-REP-01, FR-REP-04, FR-REP-05: dựng, khóa duyệt khi trống nhận định, duyệt và nhận email có ba số", async ({
    page,
  }) => {
    const r = await fetch(`${API}/v1/internal/reports/build`, {
      method: "POST",
      headers: { ...INTERNAL, "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: "demo_seller" }),
    });
    expect(r.ok).toBeTruthy();
    reportId = ((await r.json()) as { report_id: string }).report_id;

    await login(page, USERS.lead, `/ops/reports/${reportId}?t=demo_seller`);
    const approve = page.getByRole("button", { name: "Duyệt và gửi" });
    await page.getByLabel("Nhận định (Markdown)").fill("");
    await expect(approve).toBeDisabled();
    await page
      .getByLabel("Nhận định (Markdown)")
      .fill("Lãi tăng nhờ Shopee; cần bổ sung giá vốn cho SKU mới.");
    await page.getByLabel(/Việc cần làm/).fill("Bổ sung giá vốn SKU thiếu");
    page.on("dialog", (d) => d.accept());
    await approve.click();
    await expect(page.getByText("Đã duyệt.")).toBeVisible();

    const text = await latestMail(USERS.ownerSeller, "Báo cáo tuần");
    expect(text).toContain("Doanh thu thực nhận");
    expect(text).toContain("Lãi sau phí");
    expect(text).toMatch(/\/r\/[\w-]+/);
  });

  test("FR-REP-06: mở link /r/<token>, màn hình vận hành hiện đã mở", async ({ page }) => {
    const text = await latestMail(USERS.ownerSeller, "Báo cáo tuần");
    const link = text.match(/https?:\/\/[^\s]+\/r\/[\w-]+/)?.[0] ?? "";
    await page.goto(new URL(link).pathname);
    await page.waitForURL(/\/(login|app\/reports)/);
    await login(page, USERS.lead, `/ops/reports/${reportId}?t=demo_seller`);
    await expect(page.getByText(/Đã mở .* Link email/)).toBeVisible();
  });

  test("FR-REP-07: chạy lại dựng báo cáo, báo cáo đã gửi vẫn hiện số cũ", async ({ page }) => {
    await login(page, USERS.ownerSeller, `/app/reports/${reportId}?t=demo_seller`);
    const before = await page.locator("article").innerText();
    const r = await fetch(`${API}/v1/internal/reports/build`, {
      method: "POST",
      headers: { ...INTERNAL, "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: "demo_seller" }),
    });
    expect(((await r.json()) as { rebuilt: boolean }).rebuilt).toBeFalsy();
    await page.reload();
    expect(await page.locator("article").innerText()).toBe(before);
  });
});
