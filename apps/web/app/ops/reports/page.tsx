"use client";

// Danh sách báo cáo tuần theo trạng thái, lọc theo khách (spec 06 §4.4).
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatDateTime, formatWeekLabel } from "@/lib/format";
import { REPORT_STATUS_VI } from "@/lib/report-status";
import { useMe, useUrlState } from "@/lib/tenant";

export default function OpsReports() {
  const [params, set] = useUrlState();
  const { data: me } = useMe();
  const status = params.get("status") ?? "";
  const tenant = params.get("tenant") ?? "";
  const q = useQuery({
    queryKey: ["ops-reports", status, tenant],
    queryFn: () =>
      unwrap(
        api.GET("/v1/ops/reports", {
          params: { query: { status: status || undefined, tenant_id: tenant || undefined } },
        }),
      ),
  });
  return (
    <div>
      <PageHeader title="Báo cáo tuần" subtitle="Viết nhận định, duyệt và theo dõi người nhận đã mở" />
      <div className="card mb-4 flex flex-wrap gap-3">
        <label className="block">
          <span className="label">Trạng thái</span>
          <select className="input" value={status} onChange={(e) => set({ status: e.target.value || null })}>
            <option value="">Tất cả</option>
            {Object.entries(REPORT_STATUS_VI).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label">Khách</span>
          <select className="input" value={tenant} onChange={(e) => set({ tenant: e.target.value || null })}>
            <option value="">Tất cả</option>
            {(me?.tenants ?? []).map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="card">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} onRetry={() => q.refetch()} />
        ) : (q.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Không có báo cáo nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Khách</th>
                <th>Tuần</th>
                <th>Trạng thái</th>
                <th>Dựng lúc</th>
                <th className="text-right">Đã mở / người nhận</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td>{r.tenant_name}</td>
                  <td>
                    <Link
                      className="text-brand-600 hover:underline"
                      href={`/ops/reports/${r.id}?t=${r.tenant_id}`}
                    >
                      {formatWeekLabel(r.period_start)}
                    </Link>
                    {r.data_stale && (
                      <span className="ml-2">
                        <Badge tone="yellow">Dữ liệu cũ</Badge>
                      </span>
                    )}
                  </td>
                  <td>
                    <Badge tone={REPORT_STATUS_VI[r.status]?.tone}>
                      {REPORT_STATUS_VI[r.status]?.label ?? r.status}
                    </Badge>
                  </td>
                  <td>{formatDateTime(r.built_at)}</td>
                  <td className="text-right tabular-nums">
                    {r.opened}/{r.recipients}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
