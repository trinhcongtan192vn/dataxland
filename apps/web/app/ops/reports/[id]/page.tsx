"use client";

// Viết nhận định và duyệt (spec 06 §4.4, FR-REP-04): xem trước đúng như khách thấy; nút duyệt khóa khi nhận định trống.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ReportView } from "@/components/report-view";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime, formatWeekLabel } from "@/lib/format";
import { REPORT_STATUS_VI } from "@/lib/report-status";
import { useMe, useTenant } from "@/lib/tenant";

const MAX = 2000;
const VIA: Record<string, string> = {
  email_link: "Link email",
  telegram_button: "Nút Telegram",
  portal: "Cổng",
};

export default function OpsReportDetail() {
  const { id } = useParams<{ id: string }>();
  const { tenantId } = useTenant();
  const { data: me } = useMe();
  const qc = useQueryClient();
  const canApprove = me?.staff_role === "data_lead";
  const q = useQuery({
    queryKey: ["report", tenantId, id],
    queryFn: () => unwrap(api.GET("/v1/reports/{report_id}", { params: { path: { report_id: id } } })),
    enabled: !!tenantId,
  });
  const opens = useQuery({
    queryKey: ["report-opens", id],
    queryFn: () => unwrap(api.GET("/v1/reports/{report_id}/opens", { params: { path: { report_id: id } } })),
  });
  const [insight, setInsight] = useState("");
  const [actions, setActions] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (q.data) {
      setInsight(q.data.insight_md ?? q.data.insight_draft_md ?? "");
      setActions((q.data.actions.length ? q.data.actions : (q.data.actions_draft ?? [])).join("\n"));
    }
  }, [q.data]);
  const refresh = (data?: unknown) => {
    if (data) qc.setQueryData(["report", tenantId, id], data);
    void qc.invalidateQueries({ queryKey: ["ops-reports"] });
    void qc.invalidateQueries({ queryKey: ["report-opens", id] });
  };
  const body = () => ({
    insight_md: insight,
    actions: actions
      .split("\n")
      .map((a) => a.trim())
      .filter(Boolean),
  });
  const save = useMutation({
    mutationFn: () =>
      unwrap(api.PUT("/v1/reports/{report_id}", { params: { path: { report_id: id } }, body: body() })),
    onSuccess: (d) => {
      setMsg({ ok: true, text: "Đã lưu." });
      refresh(d);
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const approve = useMutation({
    mutationFn: async () => {
      await unwrap(api.PUT("/v1/reports/{report_id}", { params: { path: { report_id: id } }, body: body() }));
      return unwrap(api.POST("/v1/reports/{report_id}/approve", { params: { path: { report_id: id } } }));
    },
    onSuccess: (d) => {
      setMsg({ ok: true, text: "Đã duyệt. Báo cáo đang được gửi qua email và Telegram." });
      refresh(d);
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const supersede = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/v1/reports/{report_id}/supersede", { params: { path: { report_id: id } } })),
    onSuccess: (d) => {
      refresh();
      window.location.href = `/ops/reports/${d.id}?t=${d.tenant_id}`;
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const resend = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/v1/reports/{report_id}/resend", { params: { path: { report_id: id } } })),
    onSuccess: (d) => {
      setMsg({ ok: true, text: `Đã xếp gửi lại ${(d as { requeued?: number }).requeued ?? 0} tin.` });
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const r = q.data;
  if (!r) return null;
  const draft = r.status === "draft";
  const preview = {
    ...r,
    insight_md: draft ? insight : r.insight_md,
    actions: draft ? body().actions : r.actions,
  };

  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href="/ops/reports">
          ← Báo cáo tuần
        </Link>
      </div>
      <PageHeader
        title={`${r.tenant_name} – ${formatWeekLabel(r.period_start)}`}
        subtitle={
          <>
            <Badge tone={REPORT_STATUS_VI[r.status]?.tone}>
              {REPORT_STATUS_VI[r.status]?.label ?? r.status}
            </Badge>{" "}
            Dựng lúc {formatDateTime(r.built_at)}
            {r.approved_by && <> · duyệt bởi {r.approved_by}</>}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <ReportView report={preview} />
        <aside className="space-y-4">
          {draft ? (
            <div className="card space-y-3">
              <label className="block">
                <span className="label">Nhận định (Markdown)</span>
                <textarea
                  className="input font-mono text-xs"
                  rows={12}
                  maxLength={MAX}
                  value={insight}
                  onChange={(e) => setInsight(e.target.value)}
                  disabled={!canApprove}
                />
                <span className="text-xs text-slate-500">
                  {insight.length}/{MAX} ký tự
                </span>
              </label>
              <label className="block">
                <span className="label">Việc cần làm (mỗi dòng một việc, tối đa 5)</span>
                <textarea
                  className="input text-sm"
                  rows={5}
                  value={actions}
                  onChange={(e) => setActions(e.target.value)}
                  disabled={!canApprove}
                />
              </label>
              {canApprove ? (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={save.isPending}
                    onClick={() => save.mutate()}
                  >
                    Lưu nháp
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={!insight.trim() || approve.isPending}
                    title={!insight.trim() ? "Cần viết nhận định trước khi duyệt" : undefined}
                    onClick={() =>
                      confirm("Duyệt và gửi báo cáo cho khách? Sau khi duyệt không sửa được.") &&
                      approve.mutate()
                    }
                  >
                    Duyệt và gửi
                  </button>
                </div>
              ) : (
                <p className="text-xs text-slate-500">Chỉ trưởng nhóm data viết và duyệt báo cáo.</p>
              )}
            </div>
          ) : (
            canApprove && (
              <div className="card space-y-2">
                {r.status === "partially_sent" && (
                  <button type="button" className="btn-secondary w-full" onClick={() => resend.mutate()}>
                    Gửi lại cho người nhận bị lỗi
                  </button>
                )}
                {r.status !== "superseded" && (
                  <button
                    type="button"
                    className="btn-secondary w-full"
                    onClick={() =>
                      confirm("Tạo bản mới cho cùng tuần? Bản này sẽ chuyển sang “Đã thay”.") &&
                      supersede.mutate()
                    }
                  >
                    Tạo bản sửa cho tuần này
                  </button>
                )}
              </div>
            )
          )}
          {msg && <p className={`text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>}
          <div className="card">
            <h2 className="mb-2 font-semibold">Người nhận</h2>
            {opens.isLoading ? (
              <Spinner />
            ) : (opens.data ?? []).length === 0 ? (
              <p className="text-sm text-slate-500">Chưa gửi.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {opens.data?.map((o) => (
                  <li key={o.recipient_id} className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      {o.channel === "email" ? "✉️" : "💬"} {o.recipient}
                    </span>
                    <span className="text-xs">
                      {o.delivery_status === "failed" && <Badge tone="red">Gửi lỗi</Badge>}{" "}
                      {o.opened ? (
                        <Badge tone="green">
                          Đã mở {formatDateTime(o.first_opened_at)} · {VIA[o.via ?? ""] ?? o.via}
                        </Badge>
                      ) : (
                        <Badge>Chưa mở</Badge>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
