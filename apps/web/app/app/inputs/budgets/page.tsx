"use client";

// Ngân sách quảng cáo theo tháng × nền tảng (spec 06 §6, FR-INP-04): lưới sửa trực tiếp. Ngân sách theo chiến dịch
// (FR-INP-05): một nền tảng trong một tháng nhập ở một mức, cả nền tảng hoặc từng chiến dịch.
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
type Campaign = components["schemas"]["CampaignOut"];

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
  const byKey = new Map(
    (budgets.data ?? [])
      .filter((b) => !b.campaign_id)
      .map((b) => [`${b.month.slice(0, 7)}|${b.platform}`, b]),
  );
  const campaignSum = new Map<string, number>();
  for (const b of budgets.data ?? []) {
    if (!b.campaign_id) continue;
    const k = `${b.month.slice(0, 7)}|${b.platform}`;
    campaignSum.set(k, (campaignSum.get(k) ?? 0) + b.budget_vnd);
  }
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
                    const byCampaign = campaignSum.get(`${m}|${p}`);
                    if (byCampaign !== undefined)
                      return (
                        <td
                          key={`${m}-${p}`}
                          className="text-right tabular-nums"
                          title="Nhập theo chiến dịch"
                        >
                          {formatVnd(byCampaign)}
                          <div className="text-xs text-slate-500">theo chiến dịch</div>
                        </td>
                      );
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
      {adPlatforms.length > 0 && (
        <CampaignBudgets
          months={monthList}
          platforms={adPlatforms}
          budgets={(budgets.data ?? []).filter((b) => !!b.campaign_id)}
          hasPlatformBudget={(m, p) => byKey.has(`${m}|${p}`)}
          editable={editable}
          onSaved={refresh}
        />
      )}
    </div>
  );
}

function CampaignBudgets({
  months: monthList,
  platforms,
  budgets,
  hasPlatformBudget,
  editable,
  onSaved,
}: {
  months: string[];
  platforms: string[];
  budgets: Budget[];
  hasPlatformBudget: (month: string, platform: string) => boolean;
  editable: boolean;
  onSaved: () => void;
}) {
  const { tenantId } = useTenant();
  const [month, setMonth] = useState(monthList[2] ?? monthList[0] ?? "");
  const [platform, setPlatform] = useState(platforms[0] ?? "");
  const [campaign, setCampaign] = useState("");
  const [amount, setAmount] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const campaigns = useQuery({
    queryKey: ["ad-campaigns", tenantId],
    queryFn: () => unwrap(api.GET("/v1/inputs/ad-campaigns")),
    enabled: !!tenantId,
  });
  const names = new Map((campaigns.data ?? []).map((c: Campaign) => [c.campaign_id, c.campaign_name]));
  const options = (campaigns.data ?? []).filter((c) => c.platform === platform);
  const rows = budgets.filter((b) => b.month.slice(0, 7) === month);
  const blocked = hasPlatformBudget(month, platform);
  const add = useMutation({
    mutationFn: async () => {
      const n = Number(amount.replace(/[.\s₫]/g, ""));
      if (!campaign) throw new Error("Chọn chiến dịch");
      if (!amount.trim() || !Number.isFinite(n) || n < 0) throw new Error("Số không hợp lệ");
      await unwrap(
        api.POST("/v1/inputs/ad-budgets", {
          body: { platform, month, campaign_id: campaign, budget_vnd: n },
        }),
      );
    },
    onSuccess: () => {
      setErr(null);
      setAmount("");
      setCampaign("");
      onSaved();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/v1/inputs/ad-budgets/{budget_id}", { params: { path: { budget_id: id } } })),
    onSuccess: onSaved,
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <div className="card mt-4">
      <h2 className="mb-1 font-semibold">Ngân sách theo chiến dịch</h2>
      <p className="mb-3 text-sm text-slate-500">
        Dùng khi muốn theo dõi tiến độ từng chiến dịch. Một nền tảng trong một tháng chỉ nhập một mức: cả nền
        tảng (bảng trên) hoặc từng chiến dịch (ở đây).
      </p>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          <span className="label">Tháng</span>
          <select className="input w-auto" value={month} onChange={(e) => setMonth(e.target.value)}>
            {monthList.map((m) => (
              <option key={m} value={m}>
                {m.slice(5)}/{m.slice(0, 4)}
              </option>
            ))}
          </select>
        </label>
        {editable && (
          <>
            <label className="text-sm">
              <span className="label">Nền tảng</span>
              <select
                className="input w-auto"
                value={platform}
                onChange={(e) => {
                  setPlatform(e.target.value);
                  setCampaign("");
                }}
              >
                {platforms.map((p) => (
                  <option key={p} value={p}>
                    {platformLabel(p)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="label">Chiến dịch</span>
              <select className="input w-64" value={campaign} onChange={(e) => setCampaign(e.target.value)}>
                <option value="">Chọn chiến dịch…</option>
                {options.map((c) => (
                  <option key={c.campaign_id} value={c.campaign_id}>
                    {c.campaign_name ?? c.campaign_id}
                    {c.spend_vnd_90d ? ` (chi 90 ngày ${formatVnd(c.spend_vnd_90d)})` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="label">Ngân sách tháng</span>
              <input
                className="input w-40 text-right"
                inputMode="numeric"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="btn-primary"
              disabled={add.isPending || blocked}
              title={blocked ? "Tháng này đã nhập ngân sách cả nền tảng" : undefined}
              onClick={() => add.mutate()}
            >
              Lưu
            </button>
          </>
        )}
      </div>
      {err && <p className="mb-2 text-sm text-red-700">{err}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">Tháng này chưa có ngân sách theo chiến dịch.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Nền tảng</th>
              <th>Chiến dịch</th>
              <th className="text-right">Ngân sách</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.id}>
                <td>{platformLabel(b.platform)}</td>
                <td>{names.get(b.campaign_id ?? "") ?? b.campaign_id}</td>
                <td className="text-right tabular-nums">{formatVnd(b.budget_vnd)}</td>
                <td className="text-right">
                  {editable && (
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => remove.mutate(b.id)}
                    >
                      Xóa
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
