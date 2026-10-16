"use client";

// Ngân sách quảng cáo theo tháng × nền tảng (spec 06 §6, FR-INP-04): lưới sửa trực tiếp.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatVnd } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";
import { can, useTenant } from "@/lib/tenant";
import { useTenantSources } from "@/lib/tenant-config";

type Budget = components["schemas"]["BudgetOut"];

function months(center: Date, before: number, after: number): string[] {
  const out: string[] = [];
  for (let i = -before; i <= after; i++) {
    const d = new Date(Date.UTC(center.getUTCFullYear(), center.getUTCMonth() + i, 1));
    out.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

function Cell({
  month,
  platform,
  budget,
  editable,
  onSaved,
}: {
  month: string;
  platform: string;
  budget?: Budget;
  editable: boolean;
  onSaved: () => void;
}) {
  const [value, setValue] = useState(budget ? String(budget.budget_vnd) : "");
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      const raw = value.replace(/[.\s₫]/g, "");
      if (!raw) {
        if (budget)
          await unwrap(
            api.DELETE("/v1/inputs/ad-budgets/{budget_id}", { params: { path: { budget_id: budget.id } } }),
          );
        return;
      }
      const n = Number(raw);
      if (!Number.isFinite(n) || n < 0) throw new Error("Số không hợp lệ");
      await unwrap(api.POST("/v1/inputs/ad-budgets", { body: { platform, month, budget_vnd: n } }));
    },
    onSuccess: () => {
      setErr(null);
      onSaved();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const original = budget ? String(budget.budget_vnd) : "";
  if (!editable)
    return <td className="text-right tabular-nums">{budget ? formatVnd(budget.budget_vnd) : "—"}</td>;
  return (
    <td className="text-right">
      <input
        className={`input w-36 text-right ${err ? "border-red-500" : ""}`}
        inputMode="numeric"
        value={value}
        placeholder="—"
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => value !== original && save.mutate()}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        aria-label={`Ngân sách ${platformLabel(platform)} tháng ${month}`}
        title={err ?? undefined}
      />
    </td>
  );
}

export default function BudgetsPage() {
  const { tenantId, tenant } = useTenant();
  const editable = can(tenant, "inputs.write");
  const { adPlatforms, isLoading: srcLoading } = useTenantSources();
  const qc = useQueryClient();
  const monthList = useMemo(() => months(new Date(), 2, 3), []);
  const budgets = useQuery({
    queryKey: ["budgets", tenantId],
    queryFn: () =>
      unwrap(
        api.GET("/v1/inputs/ad-budgets", {
          params: { query: { from_month: monthList[0], to_month: monthList[monthList.length - 1] } },
        }),
      ),
    enabled: !!tenantId,
  });
  const byKey = new Map((budgets.data ?? []).map((b) => [`${b.month.slice(0, 7)}|${b.platform}`, b]));
  const refresh = () => void qc.invalidateQueries({ queryKey: ["budgets", tenantId] });

  return (
    <div>
      <PageHeader
        title="Ngân sách quảng cáo"
        subtitle="Ngân sách tháng theo nền tảng; dùng cho tiến độ ngân sách và cờ chi vượt"
      />
      <div className="card overflow-x-auto">
        {budgets.isLoading || srcLoading ? (
          <Spinner />
        ) : budgets.error ? (
          <ErrorBox error={budgets.error} onRetry={() => budgets.refetch()} />
        ) : adPlatforms.length === 0 ? (
          <p className="text-sm text-slate-500">Khách chưa có nguồn quảng cáo nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Tháng</th>
                {adPlatforms.map((p) => (
                  <th key={p} className="text-right">
                    {platformLabel(p)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {monthList.map((m) => (
                <tr key={m}>
                  <td className="whitespace-nowrap">
                    {m.slice(5)}/{m.slice(0, 4)}
                  </td>
                  {adPlatforms.map((p) => {
                    const b = byKey.get(`${m}|${p}`);
                    return (
                      <Cell
                        key={`${m}-${p}-${b?.updated_at ?? ""}`}
                        month={m}
                        platform={p}
                        budget={b}
                        editable={editable}
                        onSaved={refresh}
                      />
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {editable && (
          <p className="mt-3 text-xs text-slate-500">
            Nhập số rồi bấm Enter hoặc chuyển ô để lưu; xóa trắng ô để bỏ ngân sách.
          </p>
        )}
      </div>
    </div>
  );
}
