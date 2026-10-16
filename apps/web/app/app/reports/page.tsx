"use client";

// Lưu trữ báo cáo tuần (spec 06 §4.7): các tuần đã gửi, mới nhất trước.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatDateTime, formatWeekLabel } from "@/lib/format";
import { REPORT_STATUS_VI as STATUS_VI } from "@/lib/report-status";
import { useTenant, useTenantHref } from "@/lib/tenant";

export default function ReportsPage() {
  const { tenantId } = useTenant();
  const href = useTenantHref();
  const q = useQuery({
    queryKey: ["reports", tenantId],
    queryFn: () => unwrap(api.GET("/v1/reports")),
    enabled: !!tenantId,
  });
  return (
    <div>
      <PageHeader title="Báo cáo tuần" subtitle="Báo cáo một trang mỗi tuần, kèm nhận định của DataxLand" />
      <div className="card">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} onRetry={() => q.refetch()} />
        ) : (q.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có báo cáo tuần nào được gửi.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Tuần</th>
                <th>Trạng thái</th>
                <th>Gửi lúc</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link className="text-brand-600 hover:underline" href={href(`/app/reports/${r.id}`)}>
                      {formatWeekLabel(r.period_start)}
                    </Link>
                  </td>
                  <td>
                    <Badge tone={STATUS_VI[r.status]?.tone}>{STATUS_VI[r.status]?.label ?? r.status}</Badge>
                  </td>
                  <td>{formatDateTime(r.sent_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
