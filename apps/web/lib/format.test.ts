import { describe, expect, it } from "vitest";
import { csvFilename, toCsv } from "./csv";
import {
  formatAsOf,
  formatChange,
  formatDate,
  formatPercent,
  formatRatio,
  formatVnd,
  formatVndCompact,
  formatWeekLabel,
} from "./format";

describe("định dạng (NFR-09, spec 06 §2)", () => {
  it("tiền VND", () => {
    expect(formatVnd(1234567)).toBe("1.234.567 ₫");
    expect(formatVnd(-5000)).toBe("−5.000 ₫");
    expect(formatVnd(0)).toBe("0 ₫");
    expect(formatVnd(null)).toBe("—");
  });

  it("tiền rút gọn trên biểu đồ", () => {
    expect(formatVndCompact(1_200_000)).toBe("1,2 tr ₫");
    expect(formatVndCompact(3_400_000_000)).toBe("3,4 tỷ ₫");
    expect(formatVndCompact(2_000_000)).toBe("2 tr ₫");
  });

  it("phần trăm, ROAS, thay đổi", () => {
    expect(formatPercent(0.125)).toBe("12,5%");
    expect(formatPercent(-0.094)).toBe("−9,4%");
    expect(formatRatio(3.2)).toBe("3,2x");
    expect(formatChange(0.087)).toBe("▲ 8,7%");
    expect(formatChange(-0.094)).toBe("▼ 9,4%");
  });

  it("ngày, tuần, thời điểm cập nhật", () => {
    expect(formatDate("2026-10-06")).toBe("06/10/2026");
    expect(formatWeekLabel("2026-10-05")).toBe("Tuần 41 (05/10–11/10)");
    expect(formatAsOf("2026-10-16T03:05:00Z")).toBe("10:05 16/10");
  });
});

describe("CSV (FR-DSH-05)", () => {
  it("có BOM, tiêu đề tiếng Việt, tiền là số nguyên", () => {
    const csv = toCsv(
      [
        { key: "product", label: "Sản phẩm" },
        { key: "sku_profit", label: "Lãi theo SKU", unit: "VND" },
      ],
      [{ product: "Serum, 30ml", sku_profit: 1234567.6 }],
    );
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv).toContain("Sản phẩm,Lãi theo SKU");
    expect(csv).toContain('"Serum, 30ml",1234568');
    expect(csvFilename("sku_profit", "2026-10-01", "2026-10-15")).toBe(
      "sku_profit_2026-10-01_2026-10-15.csv",
    );
  });
});
