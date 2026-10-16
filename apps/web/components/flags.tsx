"use client";

import { Badge, ErrorBox, Spinner } from "@/components/ui";
import { type Flag, useFlags } from "@/lib/metrics";

const LABEL: Record<string, string> = {
  OVERSPEND: "Chi vượt tiến độ",
  ROAS_DROP: "ROAS thật giảm",
  PLATFORM_OVERCLAIM: "Nền tảng báo cao",
};

/** Cờ cần chú ý của gói Agency (FR-AGY-01, spec 03 §7). */
export function FlagList({ flags }: { flags?: Flag[] }) {
  const q = useFlags(flags === undefined);
  const list = flags ?? q.data;
  if (flags === undefined && q.isLoading) return <Spinner />;
  if (flags === undefined && q.error) return <ErrorBox error={q.error} />;
  if (!list?.length) return <p className="text-sm text-green-700">Không có cờ nào cần chú ý.</p>;
  return (
    <ul className="space-y-2">
      {list.map((f, i) => (
        <li key={`${f.code}-${f.platform ?? i}`} className="flex items-start gap-2 text-sm">
          <Badge tone="red">{LABEL[f.code] ?? f.code}</Badge>
          <span>{f.message_vi}</span>
        </li>
      ))}
    </ul>
  );
}
