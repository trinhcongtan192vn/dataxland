"use client";

import Link from "next/link";
import { formatAsOf } from "@/lib/format";
import type { Warning } from "@/lib/metrics";
import { useTenantHref } from "@/lib/tenant";

const TONE: Record<string, string> = {
  MISSING_COGS: "border-amber-200 bg-amber-50 text-amber-900",
  PROVISIONAL: "border-sky-200 bg-sky-50 text-sky-900",
  STALE: "border-red-200 bg-red-50 text-red-900",
};

/** "Cập nhật lúc HH:mm dd/mm" và dải cảnh báo dữ liệu (spec 06 §2, spec 03 §4.3). */
export function DataStatus({
  asOf,
  warnings = [],
}: {
  asOf: string | null | undefined;
  warnings?: Warning[];
}) {
  const href = useTenantHref();
  const seen = new Set<string>();
  const uniq = warnings.filter((w) => (seen.has(w.code) ? false : (seen.add(w.code), true)));
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">Cập nhật lúc {formatAsOf(asOf)}</p>
      {uniq.map((w) => (
        <div
          key={w.code}
          className={`rounded-lg border px-3 py-2 text-sm ${TONE[w.code] ?? TONE.PROVISIONAL}`}
        >
          {w.detail_vi}
          {w.action_url && (
            <Link className="ml-2 font-medium underline" href={href(w.action_url)}>
              Xử lý
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}
