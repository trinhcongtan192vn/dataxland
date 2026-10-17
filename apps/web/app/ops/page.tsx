"use client";

// Màn hình vận hành (spec 06 §10, FR-OPS-04): một dòng mỗi khách, ô màu theo nguồn, test chặn, báo cáo tuần.
// Tự làm mới mỗi 60 giây.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatAsOf, formatDateTime, formatVnd, formatWeekLabel } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";
import { REPORT_STATUS_VI } from "@/lib/report-status";

const CELL: Record<string, string> = {
  green: "bg-green-100 text-green-800 border-green-200",
  yellow: "bg-amber-100 text-amber-800 border-amber-200",
  red: "bg-red-100 text-red-800 border-red-200",
  grey: "bg-slate-100 text-slate-500 border-slate-200",
};

export default function OpsOverview() {
  const q = useQuery({
    queryKey: ["ops-overview"],
    queryFn: () => unwrap(api.GET("/v1/ops/overview")),
    refetchInterval: 60_000,
  });
  return (
    <div>
      <PageHeader
        title="Tổng quan vận hành"
        subtitle={
          q.dataUpdatedAt ? `Làm mới lúc ${formatAsOf(new Date(q.dataUpdatedAt).toISOString())}` : undefined
        }
      />
      <div className="card overflow-x-auto">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Khách</th>
                <th>Nguồn</th>
                <th>Lần chạy gần nhất</th>
                <th className="text-right">Test</th>
                <th>Báo cáo tuần</th>
                <th className="text-right">Chi phí / giờ tháng này</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((t) => (
                <tr key={t.tenant_id}>
                  <td>
                    <Link
                      className="font-medium text-brand-600 hover:underline"
                      href={`/ops/tenants/${t.tenant_id}`}
                    >
                      {t.name}
                    </Link>
                    <div className="text-xs text-slate-500">
                      {t.tenant_id} · {t.pack === "seller" ? "Seller" : "Agency"}
                      {t.status !== "active" && <> · {t.status}</>}
                    </div>
                    {t.bootstrap_required && <Badge tone="yellow">Chờ bootstrap</Badge>}
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {t.sources.map((s) => (
                        <span
                          key={`${s.source}-${s.account_id}`}
                          className={`rounded border px-1.5 py-0.5 text-xs ${CELL[s.color] ?? CELL.grey}`}
                          title={`${s.last_status ?? "chưa chạy"}${s.last_error_code ? ` – ${s.last_error_code}` : ""} · thành công ${formatDateTime(s.last_success_at)}`}
                        >
                          {platformLabel(s.source)} {s.last_success_at ? formatAsOf(s.last_success_at) : ""}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="text-xs">
                    {t.last_run ? (
                      <>
                        <Badge
                          tone={
                            t.last_run.status === "success"
                              ? "green"
                              : t.last_run.status === "running"
                                ? "blue"
                                : "red"
                          }
                        >
                          {String(t.last_run.status)}
                        </Badge>{" "}
                        {formatDateTime(String(t.last_run.started_at ?? ""))}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="text-right text-xs">
                    {t.blocking_tests > 0 && <Badge tone="red">{t.blocking_tests} chặn</Badge>}{" "}
                    {t.warning_tests > 0 && <Badge tone="yellow">{t.warning_tests} cảnh báo</Badge>}
                    {t.blocking_tests === 0 && t.warning_tests === 0 && (
                      <span className="text-green-700">Ổn</span>
                    )}
                  </td>
                  <td className="text-xs">
                    {t.weekly_report.period_start && formatWeekLabel(t.weekly_report.period_start)}
                    <div>
                      {t.weekly_report.report_id ? (
                        <Link
                          className="hover:underline"
                          href={`/ops/reports/${t.weekly_report.report_id}?t=${t.tenant_id}`}
                        >
                          <Badge tone={REPORT_STATUS_VI[t.weekly_report.status]?.tone}>
                            {REPORT_STATUS_VI[t.weekly_report.status]?.label ?? t.weekly_report.status}
                          </Badge>
                        </Link>
                      ) : (
                        <Badge>Chưa dựng</Badge>
                      )}{" "}
                      {t.weekly_report.recipients > 0 && (
                        <span>
                          mở {t.weekly_report.opened}/{t.weekly_report.recipients}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="text-right text-xs tabular-nums">
                    {t.costs_month_vnd != null ? formatVnd(t.costs_month_vnd) : "—"}
                    <div>{t.hours_month != null ? `${t.hours_month} giờ` : ""}</div>
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
