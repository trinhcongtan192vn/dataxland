"use client";

import { Change, Value } from "@/components/money";
import { MetricLabel } from "@/components/metric-label";
import { ErrorBox, Spinner } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { useKeyNumbers } from "@/lib/metrics";

const KEY_PERIODS = ["this_week", "last_week", "this_month", "last_month"];

/** Ba số chính (spec 03 §5) – cùng nguồn với báo cáo tuần và bot. */
export function KeyNumbersCards({ preset }: { preset: string | null }) {
  const period = preset && KEY_PERIODS.includes(preset) ? preset : "last_week";
  const q = useKeyNumbers(period);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return null;
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">
        Ba số chính {formatDate(d.period.from)}–{formatDate(d.period.to)} so với {formatDate(d.previous.from)}
        –{formatDate(d.previous.to)}
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {d.numbers.map((n) => (
          <div key={n.key} className="rounded-lg border border-brand-100 bg-brand-50 p-3">
            <div className="text-sm text-slate-600">
              {n.key === "net_profit_change_pct" ? (
                n.label_vi
              ) : (
                <MetricLabel metric={n.metric} fallback={n.label_vi} />
              )}
              {n.month && <span className="ml-1 text-xs text-slate-400">(tháng {n.month.slice(5)})</span>}
            </div>
            <div className="mt-1 text-2xl font-semibold">
              {n.value === null ? (
                <span className="text-base font-normal text-slate-500">{n.note_vi ?? "—"}</span>
              ) : n.key === "net_profit_change_pct" ? (
                <Change value={n.value} />
              ) : (
                <Value value={n.value} unit={n.unit} />
              )}
            </div>
            {n.change_pct !== undefined && n.key !== "net_profit_change_pct" && (
              <div className="text-xs">
                <Change value={n.change_pct} goodDirection={n.metric === "ad_spend" ? "neutral" : "up"} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
