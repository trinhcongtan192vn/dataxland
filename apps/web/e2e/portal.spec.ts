// Kịch bản spec 06 §11 (phần cổng khách và agency).
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { USERS, login, logout } from "./helpers";

test("FR-DSH-01, FR-DSH-03: owner demo_seller xem dashboard Seller, mọi khối có số và thời điểm cập nhật", async ({
  page,
}) => {
  await login(page, USERS.ownerSeller);
  await page.waitForURL(/\/app\/dashboards\/seller/);
  await expect(page.getByText(/Cập nhật lúc \d{2}:\d{2} \d{2}\/\d{2}/)).toBeVisible();
  for (const title of [
    "Tổng quan",
    "Lãi lỗ theo thời gian",
    "Lãi theo kênh",
    "Phí theo loại",
    "Lãi theo SKU",
  ]) {
    const block = page.locator("section", { has: page.getByRole("heading", { name: title }) });
    await expect(block.getByText("₫").first()).toBeVisible();
  }
});

test("FR-DSH-03, FR-DSH-04: bấm tên chỉ số mở định nghĩa sổ tay", async ({ page }) => {
  await login(page, USERS.ownerSeller, "/app/dashboards/seller");
  await page.getByRole("button", { name: "Doanh thu thực nhận" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Doanh thu thực nhận" });
  await expect(drawer.getByText("Phiên bản")).toBeVisible();
  await drawer.getByRole("link", { name: "Mở trong sổ tay chỉ số" }).click();
  await expect(page.getByRole("heading", { name: "Lịch sử thay đổi" })).toBeVisible();
});

test("FR-DSH-05: xuất CSV khối lãi theo SKU, file đúng cột", async ({ page }) => {
  await login(page, USERS.ownerSeller, "/app/dashboards/seller");
  const block = page.locator("section", { has: page.getByRole("heading", { name: "Lãi theo SKU" }) });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    block.getByRole("button", { name: "Xuất CSV" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^lai-theo-sku_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.csv$/);
  const text = readFileSync((await download.path()) as string, "utf-8");
  expect(text.charCodeAt(0)).toBe(0xfeff);
  expect(text.slice(1).split("\r\n")[0]).toBe("SKU,Sản phẩm,Lãi theo SKU,Doanh thu thực nhận,Số đơn");
});

test("FR-INP-02: tải file giá vốn có dòng lỗi, thấy bảng lỗi đúng dòng", async ({ page }) => {
  await login(page, USERS.ownerSeller, "/app/inputs/costs");
  const csv = "ma_sku,gia_von,ap_dung_tu,ghi_chu\nDS-SRM-C30,110000,01/10/2026,\nDS-LOI,abc,01/10/2026,\n";
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "gia-von.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText(/dòng lỗi/)).toBeVisible();
  const row = page.locator("tr", { hasText: "gia_von" }).first();
  await expect(row.locator("td").first()).toHaveText("3");
});

test("FR-AGY-01, FR-AGY-02, FR-AUTH-04: agency thấy demo_agency khi được cấp, mất khi bị thu", async ({
  page,
  browser,
}) => {
  await login(page, USERS.partner, "/partner");
  await expect(page.getByRole("link", { name: "Brand Demo (Agency)" })).toBeVisible();
  // Chủ shop thu quyền.
  const owner = await browser.newPage();
  await login(owner, USERS.ownerAgency, "/app/settings/partners");
  owner.on("dialog", (d) => d.accept());
  await owner.getByRole("button", { name: "Thu quyền" }).click();
  await expect(owner.getByText("Chưa agency nào được xem dữ liệu.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Chưa shop nào cấp quyền cho agency của bạn.")).toBeVisible();
  // Cấp lại để các kịch bản khác dùng được.
  await owner.getByRole("combobox").selectOption({ label: "Agency Demo" });
  await owner.getByRole("button", { name: "Cấp quyền" }).click();
  await logout(owner);
});

test("FR-DEC-01: tạo quyết định, giá trị lúc quyết định tự điền", async ({ page }) => {
  await login(page, USERS.ownerSeller, "/app/decisions");
  await page.getByRole("button", { name: "Thêm quyết định" }).click();
  await page.getByLabel("Quyết định").fill("Giảm giá combo 10% trên Shopee");
  await page.getByLabel("Người quyết định").fill("Chủ shop");
  await page.getByLabel("Chỉ số theo dõi").selectOption({ label: "Doanh thu thực nhận" });
  await page.getByRole("button", { name: "Ghi quyết định" }).click();
  const row = page.locator("tr", { hasText: "Giảm giá combo 10%" });
  await expect(row.locator("td").nth(3)).toContainText("₫");
});
