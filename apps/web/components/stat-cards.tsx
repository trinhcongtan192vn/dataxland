"use client";

import { Change, Value, changeOf } from "@/components/money";
import { MetricLabel } from "@/components/metric-label";
import type { MetricInfo, QueryOut } from "@/lib/metrics";

/** Thẻ số từ một truy vấn có `compare: previous_period`. */
export function StatCards({
  data,
  metrics,
  handbook,
}: {
  data: QueryOut | undefined;
  metrics: string[];
  handbook?: Record<string, MetricInfo>;
}) {
  const row = (data?.rows?.[0] ?? {}) as Record<string, unknown> & {
    compare?: Record<string, number | null>;
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {metrics.map((m) => {
        const meta = data?.metrics?.[m];
        const cur = row[m] as number | null | undefined;
        const prev = row.compare?.[m];
        return (
          <div key={m} className="rounded-lg border border-slate-200 p-3">
            <div className="text-sm text-slate-600">
              <MetricLabel metric={m} fallback={meta?.name_vi} />
            </div>
            <div className="mt-1 text-lg font-semibold">
              <Value value={cur ?? null} unit={meta?.unit ?? "count"} />
            </div>
            <div className="text-xs">
              <Change value={changeOf(cur, prev)} goodDirection={handbook?.[m]?.good_direction ?? "up"} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
