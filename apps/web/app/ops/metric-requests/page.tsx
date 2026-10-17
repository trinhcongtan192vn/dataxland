"use client";

// Câu hỏi ngoài thư viện chỉ số (spec 09 §4, FR-AI-02): team xem mô tả chỉ số khách cần, số lần hỏi, đổi trạng thái.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useMe } from "@/lib/tenant";

const STATUS: Record<string, string> = {
  new: "Mới",
  planned: "Đã lên kế hoạch",
  done: "Đã có chỉ số",
  declined: "Không làm",
};
type Status = "new" | "planned" | "done" | "declined";

export default function MetricRequests() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const canWrite = me?.staff_role === "data_lead";
  const [filter, setFilter] = useState<Status | "">("new");
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["metric-requests", filter],
    queryFn: () =>
      unwrap(api.GET("/v1/ops/metric-requests", { params: { query: filter ? { status: filter } : {} } })),
  });
  const patch = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Status }) =>
      unwrap(
        api.PATCH("/v1/ops/metric-requests/{request_id}", {
          params: { path: { request_id: id } },
          body: { status },
        }),
      ),
    onSuccess: () => {
      setErr(null);
      void qc.invalidateQueries({ queryKey: ["metric-requests"] });
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <div>
      <PageHeader
        title="Chỉ số được hỏi nhưng chưa có"
        subtitle="Từ hỏi đáp AI trên cổng và Telegram. Câu hỏi đã che số điện thoại, email."
        actions={
          <select
            className="input w-auto"
            value={filter}
            onChange={(e) => setFilter(e.target.value as Status | "")}
            aria-label="Lọc trạng thái"
          >
            <option value="">Tất cả</option>
            {Object.entries(STATUS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        }
      />
      {err && <p className="mb-3 text-sm text-red-700">{err}</p>}
      <div className="card overflow-x-auto">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} onRetry={() => q.refetch()} />
        ) : (q.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có câu hỏi nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Chỉ số cần có</th>
                <th>Câu hỏi gần nhất</th>
                <th>Khách</th>
                <th className="text-right">Số lần</th>
                <th>Cập nhật</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.description_vi}</td>
                  <td className="text-sm text-slate-600">{r.question}</td>
                  <td className="text-sm">{r.tenant_name}</td>
                  <td className="text-right tabular-nums">{r.count}</td>
                  <td className="whitespace-nowrap text-xs">{formatDateTime(r.updated_at)}</td>
                  <td>
                    {canWrite ? (
                      <select
                        className="input w-auto py-1 text-sm"
                        value={r.status}
                        disabled={patch.isPending}
                        onChange={(e) => patch.mutate({ id: r.id, status: e.target.value as Status })}
                        aria-label="Trạng thái"
                      >
                        {Object.entries(STATUS).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    ) : (
                      (STATUS[r.status] ?? r.status)
                    )}
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
