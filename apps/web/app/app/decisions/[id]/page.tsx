"use client";

// Chi tiết quyết định (spec 06 §7.2, FR-DEC-02): lấy giá trị hiện tại qua API hoặc nhập tay, chọn kết luận.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Value } from "@/components/money";
import { MetricLabel } from "@/components/metric-label";
import { Badge, ErrorBox, Field, PageHeader, Spinner, TextLink } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDate, formatDateTime } from "@/lib/format";
import { can, useTenant, useTenantHref } from "@/lib/tenant";

const CONCLUSIONS = [
  { value: "achieved", label: "Đạt", tone: "green" },
  { value: "not_achieved", label: "Không đạt", tone: "red" },
  { value: "inconclusive", label: "Chưa rõ", tone: "gray" },
] as const;

export default function DecisionDetail() {
  const { id } = useParams<{ id: string }>();
  const { tenantId, tenant } = useTenant();
  const href = useTenantHref();
  const qc = useQueryClient();
  const editable = can(tenant, "decisions.write");
  const q = useQuery({
    queryKey: ["decision", tenantId, id],
    queryFn: () => unwrap(api.GET("/v1/decisions/{decision_id}", { params: { path: { decision_id: id } } })),
    enabled: !!tenantId,
  });
  const [manual, setManual] = useState("");
  const [conclusion, setConclusion] = useState<string>("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (q.data) {
      setConclusion(q.data.conclusion ?? "");
      setNote(q.data.conclusion_md ?? "");
    }
  }, [q.data]);
  const done = (data: unknown) => {
    setErr(null);
    qc.setQueryData(["decision", tenantId, id], data);
    void qc.invalidateQueries({ queryKey: ["decisions", tenantId] });
  };
  const measure = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/v1/decisions/{decision_id}/measure", { params: { path: { decision_id: id } } })),
    onSuccess: done,
    onError: (e) => setErr(errorMessage(e)),
  });
  const update = useMutation({
    mutationFn: (body: {
      after_value?: number;
      conclusion?: "achieved" | "not_achieved" | "inconclusive";
      conclusion_md?: string;
    }) => unwrap(api.PUT("/v1/decisions/{decision_id}", { params: { path: { decision_id: id } }, body })),
    onSuccess: done,
    onError: (e) => setErr(errorMessage(e)),
  });

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  if (!d) return null;
  return (
    <div className="max-w-3xl">
      <div className="mb-2 text-sm">
        <TextLink href={href("/app/decisions")}>← Nhật ký quyết định</TextLink>
      </div>
      <PageHeader
        title={d.title}
        subtitle={`${formatDate(d.decided_on)} · ${d.decided_by}`}
        actions={d.due && <Badge tone="yellow">Đến hạn đo lại</Badge>}
      />
      <div className="card mb-4 space-y-3 text-sm">
        {d.detail_md && (
          <div className="prose-dx">
            <ReactMarkdown>{d.detail_md}</ReactMarkdown>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="text-slate-500">
              <MetricLabel metric={d.metric} fallback={d.metric_name_vi} /> trước
            </div>
            <div className="text-lg font-semibold">
              <Value value={d.baseline_value} unit={d.metric_unit} />
            </div>
            <div className="text-xs text-slate-500">
              {formatDate(d.baseline_from)}–{formatDate(d.baseline_to)}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="text-slate-500">Mục tiêu</div>
            <div className="text-lg font-semibold">
              <Value value={d.target_value} unit={d.metric_unit} />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="text-slate-500">Sau quyết định</div>
            <div className="text-lg font-semibold">
              <Value value={d.after_value} unit={d.metric_unit} />
            </div>
            <div className="text-xs text-slate-500">
              {formatDate(d.after_from)}–{formatDate(d.after_to)}
              {d.after_measured_at && <> · đo lúc {formatDateTime(d.after_measured_at)}</>}
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Chỉ số phiên bản {d.metric_version} · đo lại ngày {formatDate(d.remeasure_on)}
        </p>
      </div>

      {editable && (
        <div className="card space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <button
              type="button"
              className="btn-primary"
              disabled={measure.isPending}
              onClick={() => measure.mutate()}
            >
              {measure.isPending ? "Đang tính…" : "Lấy giá trị hiện tại"}
            </button>
            <span className="text-sm text-slate-500">hoặc</span>
            <Field label="Nhập tay giá trị sau">
              <input
                className="input w-40"
                inputMode="decimal"
                value={manual}
                onChange={(e) => setManual(e.target.value.replace(",", "."))}
              />
            </Field>
            <button
              type="button"
              className="btn-secondary"
              disabled={!manual || update.isPending}
              onClick={() => update.mutate({ after_value: Number(manual) })}
            >
              Lưu giá trị
            </button>
          </div>
          <div>
            <span className="label">Kết luận</span>
            <div className="flex gap-2">
              {CONCLUSIONS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  aria-pressed={conclusion === c.value}
                  onClick={() => setConclusion(c.value)}
                  className={`rounded-full border px-3 py-1 text-sm ${conclusion === c.value ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300"}`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
          <Field label="Nhận xét">
            <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          {err && <p className="text-sm text-red-700">{err}</p>}
          <button
            type="button"
            className="btn-primary"
            disabled={!conclusion || update.isPending}
            onClick={() =>
              update.mutate({
                conclusion: conclusion as "achieved" | "not_achieved" | "inconclusive",
                conclusion_md: note,
              })
            }
          >
            Lưu kết luận
          </button>
        </div>
      )}
    </div>
  );
}
