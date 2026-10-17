"use client";

// Hãng vận chuyển (FR-ING-09, ADR 0005): URL webhook cho GHN, GHTK; tải file đối soát J&T; trạng thái nạp.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, rawFetch, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { can, useTenant } from "@/lib/tenant";

const FILE_STATUS: Record<string, { label: string; tone: "green" | "red" | "gray" }> = {
  received: { label: "Chờ nạp", tone: "gray" },
  loaded: { label: "Đã nạp", tone: "green" },
  rejected: { label: "Bị từ chối", tone: "red" },
};

export default function CarriersPage() {
  const { tenantId, tenant } = useTenant();
  const editable = can(tenant, "inputs.write");
  const qc = useQueryClient();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const carriers = useQuery({
    queryKey: ["carriers", tenantId],
    queryFn: () => unwrap(api.GET("/v1/carriers")),
    enabled: !!tenantId,
  });
  const files = useQuery({
    queryKey: ["carrier-files", tenantId],
    queryFn: () => unwrap(api.GET("/v1/inputs/carrier-files")),
    enabled: !!tenantId,
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await rawFetch("/v1/inputs/carrier-files", { method: "POST", body: fd });
      if (!r.ok) {
        const body = (await r.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `Lỗi ${r.status}`);
      }
    },
    onSuccess: () => {
      setMsg({ ok: true, text: "Đã nhận file; dữ liệu được nạp ở lần chạy kế tiếp (khoảng 10–20 phút)." });
      void qc.invalidateQueries({ queryKey: ["carrier-files", tenantId] });
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });

  const list = carriers.data ?? [];
  const hasFile = list.some((c) => c.kind === "file");
  return (
    <div>
      <PageHeader
        title="Hãng vận chuyển"
        subtitle="Phí vận chuyển, phí hoàn và tiền thu hộ (COD) theo vận đơn của GHN, GHTK, J&T"
      />
      {msg && <p className={`mb-3 text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>}
      <div className="card mb-4 overflow-x-auto">
        {carriers.isLoading ? (
          <Spinner />
        ) : carriers.error ? (
          <ErrorBox error={carriers.error} onRetry={() => carriers.refetch()} />
        ) : list.length === 0 ? (
          <p className="text-sm text-slate-500">
            Khách chưa bật hãng vận chuyển nào. Liên hệ đội DataxLand để kết nối GHN, GHTK hoặc J&T Express.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Hãng</th>
                <th>Cách nạp</th>
                <th className="text-right">Vận đơn đã nhận</th>
                <th>Lần nhận gần nhất</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.carrier}>
                  <td className="font-medium">{c.label}</td>
                  <td className="text-sm">
                    {c.kind === "webhook" ? (
                      <>
                        Webhook
                        {c.webhook_url && (
                          <div className="mt-1 flex items-center gap-2">
                            <code className="max-w-md truncate rounded bg-slate-100 px-2 py-0.5 text-xs">
                              {c.webhook_url}
                            </code>
                            <button
                              type="button"
                              className="text-xs text-brand-600 hover:underline"
                              onClick={() => void navigator.clipboard.writeText(c.webhook_url ?? "")}
                            >
                              Sao chép
                            </button>
                          </div>
                        )}
                        <div className="text-xs text-slate-500">
                          Dán URL vào phần cấu hình webhook trên trang khách hàng của {c.label}.
                        </div>
                      </>
                    ) : (
                      "File đối soát"
                    )}
                  </td>
                  <td className="text-right tabular-nums">{c.kind === "webhook" ? c.waybills : "—"}</td>
                  <td className="text-sm">{c.last_event_at ? formatDateTime(c.last_event_at) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {hasFile && (
        <div className="card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">File đối soát J&T Express</h2>
            {editable && (
              <label className="btn-primary cursor-pointer">
                Tải file J&T
                <input
                  type="file"
                  accept=".xlsx,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) upload.mutate(f);
                    e.target.value = "";
                  }}
                />
              </label>
            )}
          </div>
          <p className="mb-3 text-xs text-slate-500">
            File cần cột Mã vận đơn, Mã đơn hàng, Trạng thái, Phí vận chuyển, Tiền COD, Ngày gửi. Cột thông
            tin người nhận không được đọc.
          </p>
          {files.isLoading ? (
            <Spinner />
          ) : (files.data ?? []).length === 0 ? (
            <p className="text-sm text-slate-500">Chưa có file nào.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Tải lúc</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {(files.data ?? []).map((f) => (
                  <tr key={f.id}>
                    <td>{f.filename}</td>
                    <td className="text-sm">{formatDateTime(f.created_at)}</td>
                    <td className="text-sm">
                      <Badge tone={FILE_STATUS[f.status]?.tone}>
                        {FILE_STATUS[f.status]?.label ?? f.status}
                      </Badge>{" "}
                      {f.rows_loaded != null && `${f.rows_loaded} vận đơn`}
                      {f.error_message_vi && <div className="text-xs text-red-700">{f.error_message_vi}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Số liệu xem ở{" "}
        <Link className="text-brand-600 hover:underline" href="/app/metrics/carrier_fees">
          Sổ tay chỉ số: Phí hãng vận chuyển
        </Link>
        .
      </p>
    </div>
  );
}
