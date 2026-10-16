import { formatByUnit, formatChange } from "@/lib/format";

/** Giá trị định dạng theo đơn vị của chỉ số (NFR-09). */
export function Value({ value, unit }: { value: number | null | undefined; unit: string }) {
  return <span className="tabular-nums">{formatByUnit(value, unit)}</span>;
}

/** Thay đổi so với kỳ trước; màu theo hướng tốt của chỉ số. */
export function Change({
  value,
  goodDirection = "up",
}: {
  value: number | null | undefined;
  goodDirection?: string;
}) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  const good = goodDirection === "down" ? value < 0 : value > 0;
  const tone = value === 0 ? "text-slate-500" : good ? "text-green-700" : "text-red-700";
  return <span className={`tabular-nums ${tone}`}>{formatChange(value)}</span>;
}

/** Tỷ lệ thay đổi giữa hai giá trị API trả về (chỉ để hiển thị so sánh, không phải chỉ số). */
export function changeOf(cur: unknown, prev: unknown): number | null {
  if (typeof cur !== "number" || typeof prev !== "number" || prev === 0) return null;
  return (cur - prev) / Math.abs(prev);
}
