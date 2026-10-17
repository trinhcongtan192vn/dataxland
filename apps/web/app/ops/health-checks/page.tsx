"use client";

// Danh sách lượt kiểm tra sức khỏe theo trạng thái (spec 07 §6.1).
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useUrlState } from "@/lib/tenant";

const TONE: Record<string, string> = {
  ready_for_review: "yellow",
  approved: "green",
  failed: "red",
  processing: "blue",
  converted: "blue",
};
const STATUSES = [
  "uploaded",
  "verified",
  "processing",
  "ready_for_review",
  "approved",
  "failed",
  "expired",
  "converted",
];

export default function OpsHealthChecks() {
  const [params, set] = useUrlState();
  const status = params.get("status") ?? "";
  const q = useQuery({
    queryKey: ["ops-hc", status],
    queryFn: () =>
      unwrap(api.GET("/v1/ops/health-checks", { params: { query: { status: status || undefined } } })),
  });
  return (
    <div>
      <PageHeader
        title="Kiểm tra sức khỏe dữ liệu"
        subtitle="Lượt khách tải file; duyệt kết quả trước khi gửi"
        actions={
          <select
            className="input w-auto"
            value={status}
            onChange={(e) => set({ status: e.target.value || null })}
          >
            <option value="">Mọi trạng thái</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        }
      />
      <div className="card">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} />
        ) : (q.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có lượt nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Gửi lúc</th>
                <th>Shop / email</th>
                <th>File</th>
                <th>Trạng thái</th>
                <th>Xóa lúc</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((h) => (
                <tr key={h.check_id}>
                  <td>
                    <Link
                      className="text-brand-600 hover:underline"
                      href={`/ops/health-checks/${h.check_id}`}
                    >
                      {formatDateTime(h.created_at)}
                    </Link>
                  </td>
                  <td>
                    {h.shop_name ?? "—"} <div className="text-xs text-slate-500">{h.email}</div>
                  </td>
                  <td>
                    {h.files}
                    {h.files_rejected > 0 && <span className="text-red-600"> ({h.files_rejected} lỗi)</span>}
                  </td>
                  <td>
                    <Badge tone={TONE[h.status] ?? "gray"}>{h.status_vi}</Badge>
                  </td>
                  <td className="text-xs">{formatDateTime(h.expires_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
