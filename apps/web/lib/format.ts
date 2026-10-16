// Định dạng số, tiền, ngày theo tiếng Việt (spec 06 §2, NFR-09).
// Web không tính toán chỉ số; các hàm ở đây chỉ định dạng giá trị API trả về.

const VN_TZ = "Asia/Ho_Chi_Minh";

function groupThousands(n: number): string {
  const s = Math.abs(Math.round(n)).toString();
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function decimalVi(n: number, digits: number): string {
  const fixed = Math.abs(n).toFixed(digits);
  const [int, frac] = fixed.split(".");
  const intPart = (int ?? "0").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const trimmed = frac ? frac.replace(/0+$/, "") : "";
  return trimmed ? `${intPart},${trimmed}` : intPart;
}

/** `1.234.567 ₫`; giá trị âm dùng dấu trừ "−". */
export function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  return `${sign}${groupThousands(value)} ₫`;
}

/** Rút gọn cho trục biểu đồ: `1,2 tr ₫`, `3,4 tỷ ₫`, `850 N ₫`. */
export function formatVndCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${sign}${decimalVi(abs / 1e9, 1)} tỷ ₫`;
  if (abs >= 1e6) return `${sign}${decimalVi(abs / 1e6, 1)} tr ₫`;
  if (abs >= 1e3) return `${sign}${decimalVi(abs / 1e3, 0)} N ₫`;
  return `${sign}${decimalVi(abs, 0)} ₫`;
}

/** Tỷ lệ ở thang 0–1 → `12,5%`. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  return `${sign}${decimalVi(Math.abs(value) * 100, digits)}%`;
}

/** ROAS và các tỷ số `ratio`: `3,2x`. */
export function formatRatio(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  return `${sign}${decimalVi(Math.abs(value), digits)}x`;
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "−" : "";
  return `${sign}${groupThousands(value)}`;
}

export type MetricUnit = "VND" | "ratio" | "percent" | "count";

export function formatByUnit(value: number | null | undefined, unit: MetricUnit | string): string {
  switch (unit) {
    case "VND":
      return formatVnd(value);
    case "ratio":
      return formatRatio(value);
    case "percent":
      return formatPercent(value);
    default:
      return formatCount(value);
  }
}

/** Thay đổi so với kỳ trước: `▲ 8,7%` / `▼ 9,4%`. */
export function formatChange(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value === 0) return "0%";
  return `${value > 0 ? "▲" : "▼"} ${decimalVi(Math.abs(value) * 100, 1)}%`;
}

function parseDateOnly(d: string): Date {
  // "YYYY-MM-DD" là ngày nghiệp vụ theo giờ Việt Nam, không đổi múi giờ.
  const [y, m, day] = d.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, day ?? 1));
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

/** `dd/mm/yyyy` từ ngày nghiệp vụ `YYYY-MM-DD`. */
export function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = parseDateOnly(d);
  return `${pad(dt.getUTCDate())}/${pad(dt.getUTCMonth() + 1)}/${dt.getUTCFullYear()}`;
}

/** Số tuần ISO của một ngày. */
export function isoWeek(d: string): number {
  const dt = parseDateOnly(d);
  const dayNum = dt.getUTCDay() || 7;
  dt.setUTCDate(dt.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(dt.getUTCFullYear(), 0, 1));
  return Math.ceil(((dt.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

/** `Tuần 41 (06/10–12/10)` từ ngày thứ Hai đầu tuần. */
export function formatWeekLabel(start: string): string {
  const s = parseDateOnly(start);
  const e = new Date(s.getTime() + 6 * 86400000);
  return `Tuần ${isoWeek(start)} (${pad(s.getUTCDate())}/${pad(s.getUTCMonth() + 1)}–${pad(e.getUTCDate())}/${pad(e.getUTCMonth() + 1)})`;
}

/** Timestamp ISO (UTC) → `HH:mm dd/mm` theo giờ Việt Nam (spec 06 §2). */
export function formatAsOf(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: VN_TZ,
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    hour12: false,
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("day")}/${get("month")}`;
}

/** Timestamp ISO → `HH:mm dd/mm/yyyy` theo giờ Việt Nam. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: VN_TZ,
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour12: false,
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("day")}/${get("month")}/${get("year")}`;
}
