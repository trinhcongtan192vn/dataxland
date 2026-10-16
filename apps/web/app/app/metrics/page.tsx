"use client";

// Sổ tay chỉ số (FR-DSH-04, spec 06 §5): mọi nội dung từ `GET /v1/metrics` (handbook.json), không viết tay.
import Link from "next/link";
import { useMemo, useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { useHandbook } from "@/lib/metrics";
import { useTenantHref } from "@/lib/tenant";

const PACK_LABEL: Record<string, string> = { seller: "Gói Seller", agency: "Gói Agency" };

function norm(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
}

export default function MetricsHandbook() {
  const { data, isLoading, error, refetch } = useHandbook();
  const [q, setQ] = useState("");
  const href = useTenantHref();
  const groups = useMemo(() => {
    const needle = norm(q.trim());
    const list = (data?.list ?? []).filter(
      (m) => !needle || [m.name_vi, m.metric, ...(m.synonyms_vi ?? [])].some((s) => norm(s).includes(needle)),
    );
    const out = new Map<string, typeof list>();
    for (const m of list) {
      const key = m.packs.length > 1 ? "common" : (m.packs[0] ?? "common");
      out.set(key, [...(out.get(key) ?? []), m]);
    }
    return [...out.entries()].sort(([a], [b]) =>
      a === "common" ? -1 : b === "common" ? 1 : a.localeCompare(b),
    );
  }, [data, q]);

  return (
    <div>
      <PageHeader
        title="Sổ tay chỉ số"
        subtitle="Định nghĩa, cách tính và lịch sử thay đổi của mọi chỉ số bạn xem được"
      />
      <input
        className="input mb-4 max-w-md"
        placeholder="Tìm theo tên hoặc từ đồng nghĩa, ví dụ “lãi”, “ROAS”"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        aria-label="Tìm chỉ số"
      />
      {isLoading ? (
        <Spinner />
      ) : error ? (
        <ErrorBox error={error} onRetry={() => refetch()} />
      ) : (
        <div className="space-y-6">
          {groups.map(([pack, list]) => (
            <section key={pack}>
              <h2 className="mb-2 font-semibold text-slate-700">{PACK_LABEL[pack] ?? "Dùng chung"}</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {list.map((m) => (
                  <Link
                    key={m.metric}
                    href={href(`/app/metrics/${m.metric}`)}
                    className="card block hover:border-brand-500"
                  >
                    <div className="font-medium">{m.name_vi}</div>
                    <div className="mt-1 line-clamp-2 text-sm text-slate-600">{m.description_vi}</div>
                    <div className="mt-2 text-xs text-slate-400">
                      {m.metric} · v{m.version}
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
          {groups.length === 0 && <p className="text-sm text-slate-500">Không có chỉ số khớp “{q}”.</p>}
        </div>
      )}
    </div>
  );
}
