"use client";

// Chi tiết khách trên màn vận hành (spec 06 §10): cấu hình đã đồng bộ (chỉ đọc), nguồn và nút kết nối OAuth,
// lịch sử chạy, chi tiết lỗi chặn, nút chạy lại. Có link tới hướng dẫn tích hợp của từng nguồn (ADR 0001).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";
import { useMe } from "@/lib/tenant";
import { setCurrentTenant } from "@/lib/tenant-store";

const MARKETPLACES = ["shopee", "tiktok_shop", "lazada"];
const GUIDE: Record<string, string> = {
  shopee: "shopee",
  tiktok_shop: "tiktok_shop",
  lazada: "lazada",
  meta_ads: "windsor",
  tiktok_ads: "windsor",
  google_ads: "windsor",
  amazon_ads: "windsor",
  amazon_seller: "windsor",
};
const CONNECT_ERR: Record<string, string> = {
  STATE_INVALID: "Phiên kết nối không hợp lệ hoặc đã hết hạn (15 phút). Bấm Kết nối lại.",
  DENIED: "Chủ shop đã từ chối cấp quyền.",
  SHOP_ID_MISSING: "Sàn không trả mã shop.",
  EXCHANGE_FAILED: "Đổi mã lấy token thất bại. Kiểm tra khóa ứng dụng và URL callback.",
};

type Source = {
  type: string;
  connector: string;
  account_id?: string | null;
  secret_ref?: string | null;
  enabled?: boolean;
};

export default function OpsTenant() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  setCurrentTenant(id);
  const qc = useQueryClient();
  const { data: me } = useMe();
  const canWrite = me?.staff_role === "data_lead";
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const tenant = useQuery({
    queryKey: ["ops-tenant", id],
    queryFn: () => unwrap(api.GET("/v1/tenants/{tenant_id}", { params: { path: { tenant_id: id } } })),
  });
  const syncs = useQuery({
    queryKey: ["ops-sources", id],
    queryFn: () =>
      unwrap(api.GET("/v1/ops/tenants/{tenant_id}/sources", { params: { path: { tenant_id: id } } })),
  });
  const runs = useQuery({
    queryKey: ["ops-runs", id],
    queryFn: () =>
      unwrap(api.GET("/v1/ops/tenants/{tenant_id}/runs", { params: { path: { tenant_id: id } } })),
    refetchInterval: 30_000,
  });
  const rerun = useMutation({
    mutationFn: (full: boolean) =>
      unwrap(
        api.POST("/v1/ops/tenants/{tenant_id}/runs", {
          params: { path: { tenant_id: id } },
          body: { full_refresh: full, reason: "Chạy lại từ màn vận hành" },
        }),
      ),
    onSuccess: () => {
      setMsg({ ok: true, text: "Đã yêu cầu chạy lại; Dagster sẽ bắt đầu trong khoảng 1 phút." });
      void qc.invalidateQueries({ queryKey: ["ops-runs", id] });
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const connect = useMutation({
    mutationFn: (source: string) =>
      unwrap(api.POST("/v1/connect/{source}/start", { params: { path: { source } } })),
    onSuccess: (d) => {
      window.location.href = (d as { authorize_url: string }).authorize_url;
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });

  const connected = params.get("connected");
  const connectError = params.get("connect_error");
  if (tenant.isLoading) return <Spinner />;
  if (tenant.error) return <ErrorBox error={tenant.error} />;
  const t = tenant.data;
  if (!t) return null;
  const cfg = t.config as {
    sources?: Source[];
    schedule?: Record<string, string>;
    quality?: Record<string, unknown>;
  };
  const syncBy = new Map((syncs.data ?? []).map((s) => [`${String(s.source)}|${String(s.account_id)}`, s]));

  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href="/ops">
          ← Tổng quan
        </Link>
      </div>
      <PageHeader
        title={t.name}
        subtitle={`${t.tenant_id} · gói ${t.pack} · ${t.status} · đồng bộ cấu hình ${formatDateTime(t.synced_at)}`}
        actions={
          canWrite && (
            <>
              <button
                type="button"
                className="btn-primary"
                disabled={rerun.isPending}
                onClick={() => rerun.mutate(false)}
              >
                Chạy lại
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={rerun.isPending}
                onClick={() => confirm("Chạy lại toàn bộ (full refresh) dbt?") && rerun.mutate(true)}
              >
                Chạy lại toàn bộ
              </button>
            </>
          )
        }
      />
      {connected && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          Đã kết nối {platformLabel(connected)} (shop {params.get("account_id")}). Thêm vào{" "}
          <code>tenants/{t.tenant_id}.yml</code>:{" "}
          <code>account_id: &quot;{params.get("account_id")}&quot;</code>,{" "}
          <code>secret_ref: {params.get("secret_ref")}</code>, rồi mở PR.
        </div>
      )}
      {connectError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {CONNECT_ERR[connectError] ?? connectError}
        </div>
      )}
      {msg && <p className={`mb-4 text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-3 font-semibold">Nguồn dữ liệu</h2>
          <table className="table">
            <tbody>
              {(cfg.sources ?? []).map((s) => {
                const st = syncBy.get(`${s.type}|${s.account_id ?? ""}`);
                return (
                  <tr key={`${s.type}-${s.account_id}`}>
                    <td>
                      <div className="font-medium">{platformLabel(s.type)}</div>
                      <div className="text-xs text-slate-500">
                        {s.connector} · {s.account_id ?? "—"}
                        {s.enabled === false && " · tắt"}
                      </div>
                    </td>
                    <td className="text-xs">
                      {st ? (
                        <>
                          <Badge
                            tone={
                              st.last_status === "failed"
                                ? "red"
                                : st.last_status === "success"
                                  ? "green"
                                  : "gray"
                            }
                          >
                            {String(st.last_status ?? "chưa chạy")}
                          </Badge>
                          {st.last_error_code ? (
                            <span className="ml-1 text-red-700">{String(st.last_error_code)}</span>
                          ) : null}
                          <div>Thành công: {formatDateTime(st.last_success_at as string | null)}</div>
                        </>
                      ) : (
                        <span className="text-slate-400">Chưa chạy</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-right text-xs">
                      {canWrite && MARKETPLACES.includes(s.type) && (
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          disabled={connect.isPending}
                          onClick={() => connect.mutate(s.type)}
                        >
                          {st?.connected_at ? "Kết nối lại" : "Kết nối"}
                        </button>
                      )}
                      {GUIDE[s.type] && (
                        <Link
                          className="ml-2 text-brand-600 hover:underline"
                          href={`/ops/integrations/${GUIDE[s.type]}`}
                        >
                          Hướng dẫn
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {canWrite && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="text-slate-500">Kết nối sàn chưa có trong cấu hình:</span>
              {MARKETPLACES.filter((m) => !(cfg.sources ?? []).some((s) => s.type === m)).map((m) => (
                <button
                  key={m}
                  type="button"
                  className="text-brand-600 hover:underline"
                  onClick={() => connect.mutate(m)}
                >
                  {platformLabel(m)}
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="card">
          <h2 className="mb-3 font-semibold">Cấu hình đã đồng bộ (chỉ đọc)</h2>
          <pre className="max-h-96 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
            {JSON.stringify(t.config, null, 2)}
          </pre>
          <p className="mt-2 text-xs text-slate-500">
            Sửa ở <code>tenants/{t.tenant_id}.yml</code> qua PR; không sửa trên cổng.
          </p>
        </section>
      </div>

      <section className="card mt-4">
        <h2 className="mb-3 font-semibold">Lịch sử chạy</h2>
        {runs.isLoading ? (
          <Spinner />
        ) : (runs.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có lần chạy nào.</p>
        ) : (
          <div className="space-y-3">
            {(runs.data ?? []).map((r) => (
              <details
                key={r.run_id}
                className="rounded-lg border border-slate-200 p-3"
                open={r.status === "blocked"}
              >
                <summary className="cursor-pointer text-sm">
                  <Badge tone={r.status === "success" ? "green" : r.status === "running" ? "blue" : "red"}>
                    {r.status}
                  </Badge>{" "}
                  {r.job} · {formatDateTime(r.started_at)}
                  {r.failed_step && <> · lỗi ở bước {r.failed_step}</>}
                </summary>
                {r.triage_md && <p className="mt-2 whitespace-pre-wrap text-sm">{r.triage_md}</p>}
                {(r.blocking_failures ?? []).length > 0 && (
                  <div className="mt-2 overflow-x-auto">
                    <h3 className="mb-1 text-sm font-medium text-red-700">Test chặn</h3>
                    <table className="table">
                      <tbody>
                        {(r.blocking_failures ?? []).map((f, i) => (
                          <tr key={i}>
                            <td className="font-mono text-xs">{String(f.test)}</td>
                            <td className="text-xs">
                              {Array.isArray(f.rows) ? (
                                <table className="w-full">
                                  <tbody>
                                    {(f.rows as Record<string, unknown>[]).slice(0, 20).map((row, j) => (
                                      <tr key={j}>
                                        {Object.entries(row).map(([k, v]) => (
                                          <td key={k} className="pr-2">
                                            <span className="text-slate-400">{k}:</span> {String(v)}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              ) : (
                                String(f.failures ?? "")
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <pre className="mt-2 overflow-x-auto text-xs text-slate-500">
                  {JSON.stringify(r.steps, null, 1)}
                </pre>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
