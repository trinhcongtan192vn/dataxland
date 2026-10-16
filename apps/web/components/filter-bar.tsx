"use client";

// Bộ lọc chung của dashboard: khoảng ngày (preset hoặc chọn tay) và nền tảng; lưu trong URL (spec 06 §3).
import { PLATFORM_LABEL, PRESETS } from "@/lib/metrics";
import { useUrlState } from "@/lib/tenant";

export function FilterBar({
  platforms,
  defaultPreset = "last_30_days",
}: {
  platforms: string[];
  defaultPreset?: string;
}) {
  const [params, set] = useUrlState();
  const custom = !!(params.get("from") && params.get("to"));
  const preset = custom ? "custom" : (params.get("preset") ?? defaultPreset);
  const selected = new Set((params.get("platform") ?? "").split(",").filter(Boolean));

  const toggle = (p: string) => {
    const next = new Set(selected);
    if (next.has(p)) next.delete(p);
    else next.add(p);
    set({ platform: [...next].join(",") || null });
  };

  return (
    <div className="card mb-4 flex flex-wrap items-end gap-4">
      <label className="block">
        <span className="label">Khoảng thời gian</span>
        <select
          className="input"
          value={preset}
          onChange={(e) =>
            e.target.value === "custom"
              ? set({ preset: null, from: params.get("from") ?? "", to: params.get("to") ?? "" })
              : set({ preset: e.target.value, from: null, to: null })
          }
        >
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
          <option value="custom">Chọn ngày…</option>
        </select>
      </label>
      {preset === "custom" && (
        <>
          <label className="block">
            <span className="label">Từ ngày</span>
            <input
              className="input"
              type="date"
              value={params.get("from") ?? ""}
              onChange={(e) => set({ from: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="label">Đến ngày</span>
            <input
              className="input"
              type="date"
              value={params.get("to") ?? ""}
              onChange={(e) => set({ to: e.target.value })}
            />
          </label>
        </>
      )}
      {platforms.length > 1 && (
        <fieldset>
          <legend className="label">Kênh</legend>
          <div className="flex flex-wrap gap-2">
            {platforms.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => toggle(p)}
                className={`rounded-full border px-3 py-1 text-sm ${selected.has(p) ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300 bg-white text-slate-600"}`}
                aria-pressed={selected.has(p)}
              >
                {PLATFORM_LABEL[p] ?? p}
              </button>
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}
