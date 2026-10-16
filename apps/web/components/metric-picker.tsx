"use client";

import { useHandbook } from "@/lib/metrics";

/** Chọn nhiều chỉ số (allowlist của member, phạm vi nhóm Telegram). */
export function MetricPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const { data } = useHandbook();
  const set = new Set(value);
  return (
    <div className="grid max-h-56 gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
      {(data?.list ?? []).map((m) => (
        <label key={m.metric} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={set.has(m.metric)}
            onChange={(e) => {
              const next = new Set(set);
              if (e.target.checked) next.add(m.metric);
              else next.delete(m.metric);
              onChange([...next]);
            }}
          />
          {m.name_vi}
        </label>
      ))}
    </div>
  );
}
