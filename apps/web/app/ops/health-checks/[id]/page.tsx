"use client";

// Duyệt kết quả kiểm tra sức khỏe (spec 07 §6.1) và chuyển thành khách (spec 07 §8).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { HcResultView } from "@/components/hc-result";
import { Badge, ErrorBox, Field, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export default function OpsHealthCheckDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["ops-hc", id],
    queryFn: () =>
      unwrap(api.GET("/v1/ops/health-checks/{check_id}", { params: { path: { check_id: id } } })),
  });
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [conv, setConv] = useState({ tenant_id: "", pack: "seller" });
  const [yaml, setYaml] = useState<string | null>(null);
  useEffect(() => {
    if (q.data) setNotes(q.data.reviewer_notes_md ?? "");
  }, [q.data]);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["ops-hc"] });
  };
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/v1/ops/health-checks/{check_id}", {
          params: { path: { check_id: id } },
          body: { reviewer_notes_md: notes },
        }),
      ),
    onSuccess: () => {
      setMsg({ ok: true, text: "Đã lưu ghi chú." });
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const approve = useMutation({
    mutationFn: async () => {
      await unwrap(
        api.PUT("/v1/ops/health-checks/{check_id}", {
          params: { path: { check_id: id } },
          body: { reviewer_notes_md: notes },
        }),
      );
      return unwrap(
        api.POST("/v1/ops/health-checks/{check_id}/approve", { params: { path: { check_id: id } } }),
      );
    },
    onSuccess: (d) => {
      const r = d as { email_sent?: boolean };
      setMsg({
        ok: true,
        text: r.email_sent
          ? "Đã duyệt và gửi email kết quả."
          : "Đã duyệt; gửi email lỗi, gửi lại link thủ công.",
      });
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const convert = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/v1/ops/health-checks/{check_id}/convert", {
          params: { path: { check_id: id } },
          body: conv,
        }),
      ),
    onSuccess: (d) => {
      setYaml((d as { yaml?: string }).yaml ?? null);
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const h = q.data;
  if (!h) return null;
  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href="/ops/health-checks">
          ← Kiểm tra sức khỏe
        </Link>
      </div>
      <PageHeader
        title={h.shop_name ?? h.email}
        subtitle={
          <>
            <Badge tone="blue">{h.status_vi}</Badge> {h.email} · gửi {formatDateTime(h.created_at)} · xóa{" "}
            {formatDateTime(h.expires_at)}
            {h.consent_convert_at && <> · đã đồng ý chuyển dữ liệu</>}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          {h.result ? (
            <HcResultView result={h.result} notes={notes} staff />
          ) : (
            <div className="card">
              <p className="text-sm text-slate-500">Chưa có kết quả.</p>
              <ul className="mt-2 space-y-1 text-sm">
                {h.file_list.map((f) => (
                  <li key={String(f.id)}>
                    {String(f.filename)} – {String(f.status)}{" "}
                    {f.error_message_vi ? `(${String(f.error_message_vi)})` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <aside className="space-y-4">
          {(h.status === "ready_for_review" || h.status === "approved") && (
            <div className="card space-y-3">
              <Field label="Ghi chú cho khách (Markdown, hiện đầu trang kết quả)">
                <textarea
                  className="input text-sm"
                  rows={8}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  maxLength={4000}
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => save.mutate()}
                  disabled={save.isPending}
                >
                  Lưu ghi chú
                </button>
                {h.status === "ready_for_review" && (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={approve.isPending}
                    onClick={() => confirm("Duyệt và gửi kết quả cho người gửi?") && approve.mutate()}
                  >
                    Duyệt và gửi
                  </button>
                )}
              </div>
            </div>
          )}
          {h.status !== "expired" && h.status !== "uploaded" && (
            <div className="card space-y-3">
              <h2 className="font-semibold">Chuyển thành khách</h2>
              <Field label="tenant_id">
                <input
                  className="input"
                  value={conv.tenant_id}
                  onChange={(e) => setConv({ ...conv, tenant_id: e.target.value })}
                  placeholder="vd. shop_abc"
                />
              </Field>
              <Field label="Gói">
                <select
                  className="input"
                  value={conv.pack}
                  onChange={(e) => setConv({ ...conv, pack: e.target.value })}
                >
                  <option value="seller">Seller</option>
                  <option value="agency">Agency</option>
                </select>
              </Field>
              <button
                type="button"
                className="btn-secondary"
                disabled={!conv.tenant_id || convert.isPending}
                onClick={() => convert.mutate()}
              >
                Sinh cấu hình nháp
              </button>
              {yaml && (
                <div>
                  <p className="text-xs text-slate-500">
                    Lưu thành <code>tenants/{conv.tenant_id}.yml</code>, điền account_id, mở PR. Sau khi
                    bootstrap, chạy job Dagster <code>healthcheck_convert</code> để chuyển dữ liệu (nếu khách
                    đã đồng ý).
                  </p>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                    {yaml}
                  </pre>
                </div>
              )}
            </div>
          )}
          {msg && <p className={`text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>}
        </aside>
      </div>
    </div>
  );
}
