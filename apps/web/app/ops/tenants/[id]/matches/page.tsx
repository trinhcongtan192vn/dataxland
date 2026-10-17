"use client";

// Hàng chờ ghép sản phẩm (spec 10 §5.2): hai sản phẩm cạnh nhau với tên, SKU, giá, kênh, điểm và lý do;
// duyệt, từ chối, duyệt hàng loạt; gỡ cặp đã duyệt. Gợi ý không bao giờ tự duyệt.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime, formatPercent, formatVnd } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";
import { useMe } from "@/lib/tenant";
import { setCurrentTenant } from "@/lib/tenant-store";

type Side = {
  source: string;
  source_id: string;
  name?: string;
  seller_sku?: string;
  price_vnd?: number;
  label?: string;
};

function Product({ p }: { p: Side }) {
  return (
    <div>
      <div className="font-medium">{p.name ?? p.label}</div>
      <div className="text-xs text-slate-500">
        {platformLabel(p.source)} · SKU {p.seller_sku ?? "—"} · {p.price_vnd ? formatVnd(p.price_vnd) : "—"}
      </div>
    </div>
  );
}

const METHOD: Record<string, string> = {
  llm: "AI so cặp",
  similarity: "Độ giống tên",
  rule_barcode: "Trùng mã vạch",
  rule_sku: "Trùng SKU",
};

export default function Matches() {
  const { id } = useParams<{ id: string }>();
  setCurrentTenant(id);
  const qc = useQueryClient();
  const { data: me } = useMe();
  const canWrite = me?.staff_role === "data_lead";
  const [status, setStatus] = useState("proposed");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["matches", id, status],
    queryFn: () => unwrap(api.GET("/v1/identity/matches", { params: { query: { status } } })),
  });
  const refresh = () => {
    setPicked(new Set());
    void qc.invalidateQueries({ queryKey: ["matches", id] });
  };
  const act = useMutation({
    mutationFn: async ({ ids, action }: { ids: string[]; action: "approve" | "reject" | "undo" }) => {
      if (action === "undo") {
        return unwrap(
          api.POST("/v1/identity/matches/{match_id}/undo", { params: { path: { match_id: ids[0] ?? "" } } }),
        );
      }
      return unwrap(api.POST("/v1/identity/matches/bulk", { body: { ids, action } }));
    },
    onSuccess: () => {
      setErr(null);
      refresh();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const rows = q.data ?? [];
  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href={`/ops/tenants/${id}`}>
          ← Khách {id}
        </Link>
      </div>
      <PageHeader
        title="Ghép sản phẩm chờ duyệt"
        subtitle="Duyệt xong, dữ liệu được dựng lại ở lần chạy kế tiếp (khoảng vài phút): dashboard lãi theo SKU gộp các dòng đã ghép."
        actions={
          <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="proposed">Chờ duyệt</option>
            <option value="approved">Đã duyệt</option>
            <option value="rejected">Đã từ chối</option>
            <option value="undone">Đã gỡ</option>
          </select>
        }
      />
      {err && (
        <div className="mb-3">
          <ErrorBox error={new Error(err)} />
        </div>
      )}
      {canWrite && status === "proposed" && picked.size > 0 && (
        <div className="card mb-3 flex items-center gap-2 text-sm">
          Đã chọn {picked.size} cặp
          <button
            type="button"
            className="btn-primary px-2 py-1"
            onClick={() => act.mutate({ ids: [...picked], action: "approve" })}
          >
            Duyệt các cặp đã chọn
          </button>
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            onClick={() => act.mutate({ ids: [...picked], action: "reject" })}
          >
            Từ chối
          </button>
        </div>
      )}
      <div className="card overflow-x-auto">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-500">Không có cặp nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                {canWrite && status === "proposed" && (
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Chọn tất cả"
                      checked={picked.size === rows.length}
                      onChange={(e) =>
                        setPicked(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())
                      }
                    />
                  </th>
                )}
                <th>Sản phẩm A</th>
                <th>Sản phẩm B</th>
                <th>Điểm</th>
                <th>Lý do</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id}>
                  {canWrite && status === "proposed" && (
                    <td>
                      <input
                        type="checkbox"
                        aria-label="Chọn cặp"
                        checked={picked.has(m.id)}
                        onChange={(e) => {
                          const next = new Set(picked);
                          if (e.target.checked) next.add(m.id);
                          else next.delete(m.id);
                          setPicked(next);
                        }}
                      />
                    </td>
                  )}
                  <td>
                    <Product p={m.left as Side} />
                  </td>
                  <td>
                    <Product p={m.right as Side} />
                  </td>
                  <td className="whitespace-nowrap">
                    {m.score != null ? formatPercent(m.score, 0) : "—"}
                    <div className="text-xs text-slate-500">{METHOD[m.method] ?? m.method}</div>
                  </td>
                  <td className="text-sm">{m.reason_vi ?? "—"}</td>
                  <td className="whitespace-nowrap text-right">
                    {canWrite && m.status === "proposed" && (
                      <>
                        <button
                          type="button"
                          className="btn-primary px-2 py-1 text-xs"
                          onClick={() => act.mutate({ ids: [m.id], action: "approve" })}
                        >
                          Duyệt
                        </button>
                        <button
                          type="button"
                          className="ml-1 btn-secondary px-2 py-1 text-xs"
                          onClick={() => act.mutate({ ids: [m.id], action: "reject" })}
                        >
                          Từ chối
                        </button>
                      </>
                    )}
                    {canWrite && m.status === "approved" && (
                      <button
                        type="button"
                        className="text-xs text-red-600 hover:underline"
                        onClick={() =>
                          confirm("Gỡ cặp này? Nhóm sản phẩm sẽ bị tách ở lần chạy kế tiếp.") &&
                          act.mutate({ ids: [m.id], action: "undo" })
                        }
                      >
                        Gỡ
                      </button>
                    )}
                    {m.decided_at && (
                      <div className="text-xs text-slate-500">
                        <Badge>{m.decided_by === "system" ? "Tự động" : "Đã quyết"}</Badge>{" "}
                        {formatDateTime(m.decided_at)}
                      </div>
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
