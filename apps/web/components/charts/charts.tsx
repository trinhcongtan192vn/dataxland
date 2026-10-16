"use client";

// Biểu đồ (Recharts). Trục tiền rút gọn `1,2 tr ₫` (NFR-09); không tính toán số, chỉ vẽ dữ liệu API trả về.
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatByUnit, formatDate, formatPercent, formatRatio, formatVndCompact } from "@/lib/format";

export const COLORS = [
  "#2563eb",
  "#16a34a",
  "#f59e0b",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#65a30d",
];

export type Series = { key: string; label: string; unit: string; color?: string; stack?: string };

function axisFormatter(unit: string): (v: number) => string {
  if (unit === "VND") return formatVndCompact;
  if (unit === "percent") return (v) => formatPercent(v, 0);
  if (unit === "ratio") return (v) => formatRatio(v, 1);
  return (v) => formatByUnit(v, unit);
}

function xFormatter(v: unknown): string {
  const s = String(v ?? "");
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? formatDate(s).slice(0, 5) : s;
}

export function LineChartView({
  data,
  x,
  series,
  height = 260,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
}) {
  const unit = series[0]?.unit ?? "count";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={x} tickFormatter={xFormatter} fontSize={12} />
        <YAxis tickFormatter={axisFormatter(unit)} fontSize={12} width={80} />
        <Tooltip
          formatter={(v: number, name: string) => {
            const s = series.find((x) => x.label === name);
            return formatByUnit(v, s?.unit ?? unit);
          }}
          labelFormatter={xFormatter}
        />
        <Legend />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color ?? COLORS[i % COLORS.length]}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BarChartView({
  data,
  x,
  series,
  height = 260,
  xLabel,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
  xLabel?: (v: unknown) => string;
}) {
  const unit = series[0]?.unit ?? "count";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey={x} tickFormatter={xLabel ?? xFormatter} fontSize={12} />
        <YAxis tickFormatter={axisFormatter(unit)} fontSize={12} width={80} />
        <Tooltip
          formatter={(v: number, name: string) => {
            const s = series.find((x) => x.label === name);
            return formatByUnit(v, s?.unit ?? unit);
          }}
          labelFormatter={(v) => (xLabel ? xLabel(v) : xFormatter(v))}
        />
        <Legend />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={s.color ?? COLORS[i % COLORS.length]}
            stackId={s.stack}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Đưa dòng dạng dài (ngày × chiều) về dạng rộng để vẽ cột chồng. */
export function pivot(
  rows: Record<string, unknown>[],
  x: string,
  by: string,
  metric: string,
): { data: Record<string, unknown>[]; keys: string[] } {
  const keys: string[] = [];
  const map = new Map<string, Record<string, unknown>>();
  for (const r of rows) {
    const xv = String(r[x] ?? "");
    const k = String(r[by] ?? "");
    if (!keys.includes(k)) keys.push(k);
    const row = map.get(xv) ?? { [x]: xv };
    row[k] = r[metric];
    map.set(xv, row);
  }
  return { data: [...map.values()].sort((a, b) => String(a[x]).localeCompare(String(b[x]))), keys };
}
