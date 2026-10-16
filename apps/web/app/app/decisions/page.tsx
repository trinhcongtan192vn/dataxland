"use client";

// Nhật ký quyết định (spec 06 §7, FR-DEC-01): danh sách và tạo mới; giá trị lúc quyết định do API tự lấy.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Value } from "@/components/money";
import { Badge, ErrorBox, Field, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { useHandbook } from "@/lib/metrics";
import { can, useTenant, useTenantHref } from "@/lib/tenant";

const CONCLUSION: Record<string, { label: string; tone: string }> = {
  achieved: { label: "Đạt", tone: "green" },
  not_achieved: { label: "Không đạt", tone: "red" },
  inconclusive: { label: "Chưa rõ", tone: "gray" },
};

function todayVn(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

function addDays(d: string, n: number): string {
  const dt = new Date(`${d}T00:00:00Z`);
  dt.setUTCDate(dt.getUTCDate() + n);
  return dt.toISOString().slice(0, 10);
}

function NewDecision({ onCreated }: { onCreated: () => void }) {
  const { data: hb } = useHandbook();
  const today = todayVn();
  const [f, setF] = useState({
    decided_on: today,
    title: "",
    detail_md: "",
    decided_by: "",
    metric: "",
    baseline_window: "last_7_days" as "last_7_days" | "last_28_days",
    target_value: "",
    remeasure_on: addDays(today, 14),
  });
  const [err, setErr] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/v1/decisions", {
          body: {
            decided_on: f.decided_on,
            title: f.title,
            detail_md: f.detail_md || null,
            decided_by: f.decided_by,
            metric: f.metric,
            baseline_window: f.baseline_window,
            target_value: f.target_value ? Number(f.target_value) : null,
            remeasure_on: f.remeasure_on,
            dimension_filter: [],
          },
        }),
      ),
    onSuccess: () => onCreated(),
    onError: (e) => setErr(errorMessage(e)),
  });
  return (
    <form
      className="card mb-6 grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        setErr(null);
        create.mutate();
      }}
    >
      <Field label="Quyết định">
        <input
          className="input"
          required
          maxLength={200}
          value={f.title}
          onChange={(e) => setF({ ...f, title: e.target.value })}
          placeholder="Ví dụ: Giảm giá combo 10% trên Shopee"
        />
      </Field>
      <Field label="Người quyết định">
        <input
          className="input"
          required
          value={f.decided_by}
          onChange={(e) => setF({ ...f, decided_by: e.target.value })}
        />
      </Field>
      <Field label="Chỉ số theo dõi">
        <select
          className="input"
          required
          value={f.metric}
          onChange={(e) => setF({ ...f, metric: e.target.value })}
        >
          <option value="">Chọn chỉ số…</option>
          {(hb?.list ?? []).map((m) => (
            <option key={m.metric} value={m.metric}>
              {m.name_vi}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Mục tiêu (tùy chọn)" hint="Cùng đơn vị với chỉ số; tỷ lệ nhập dạng 0,15 cho 15%">
        <input
          className="input"
          inputMode="decimal"
          value={f.target_value}
          onChange={(e) => setF({ ...f, target_value: e.target.value.replace(",", ".") })}
        />
      </Field>
      <Field label="Ngày quyết định">
        <input
          className="input"
          type="date"
          required
          value={f.decided_on}
          onChange={(e) => setF({ ...f, decided_on: e.target.value })}
        />
      </Field>
      <Field label="So với">
        <select
          className="input"
          value={f.baseline_window}
          onChange={(e) => setF({ ...f, baseline_window: e.target.value as "last_7_days" | "last_28_days" })}
        >
          <option value="last_7_days">7 ngày trước khi quyết định</option>
          <option value="last_28_days">28 ngày trước khi quyết định</option>
        </select>
      </Field>
      <Field label="Ngày đo lại">
        <input
          className="input"
          type="date"
          required
          value={f.remeasure_on}
          onChange={(e) => setF({ ...f, remeasure_on: e.target.value })}
        />
      </Field>
      <Field label="Chi tiết (tùy chọn)">
        <textarea
          className="input"
          rows={2}
          value={f.detail_md}
          onChange={(e) => setF({ ...f, detail_md: e.target.value })}
        />
      </Field>
      {err && <p className="text-sm text-red-700 sm:col-span-2">{err}</p>}
      <div className="sm:col-span-2">
        <button type="submit" className="btn-primary" disabled={create.isPending}>
          {create.isPending ? "Đang lấy giá trị hiện tại…" : "Ghi quyết định"}
        </button>
      </div>
    </form>
  );
}

export default function DecisionsPage() {
  const { tenantId, tenant } = useTenant();
  const href = useTenantHref();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const list = useQuery({
    queryKey: ["decisions", tenantId],
    queryFn: () => unwrap(api.GET("/v1/decisions")),
    enabled: !!tenantId,
  });
  return (
    <div>
      <PageHeader
        title="Nhật ký quyết định"
        subtitle="Ghi lại quyết định kinh doanh và đo lại chỉ số sau khi làm"
        actions={
          can(tenant, "decisions.write") && (
            <button type="button" className="btn-primary" onClick={() => setAdding((v) => !v)}>
              {adding ? "Đóng" : "Thêm quyết định"}
            </button>
          )
        }
      />
      {adding && (
        <NewDecision
          onCreated={() => {
            setAdding(false);
            void qc.invalidateQueries({ queryKey: ["decisions", tenantId] });
          }}
        />
      )}
      <div className="card">
        {list.isLoading ? (
          <Spinner />
        ) : list.error ? (
          <ErrorBox error={list.error} onRetry={() => list.refetch()} />
        ) : (list.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có quyết định nào.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Ngày</th>
                <th>Quyết định</th>
                <th>Chỉ số</th>
                <th className="text-right">Trước</th>
                <th className="text-right">Sau</th>
                <th>Đo lại</th>
                <th>Kết luận</th>
              </tr>
            </thead>
            <tbody>
              {(list.data ?? []).map((d) => (
                <tr key={d.id}>
                  <td className="whitespace-nowrap">{formatDate(d.decided_on)}</td>
                  <td>
                    <Link className="text-brand-600 hover:underline" href={href(`/app/decisions/${d.id}`)}>
                      {d.title}
                    </Link>
                  </td>
                  <td>{d.metric_name_vi}</td>
                  <td className="text-right">
                    <Value value={d.baseline_value} unit={d.metric_unit} />
                  </td>
                  <td className="text-right">
                    <Value value={d.after_value} unit={d.metric_unit} />
                  </td>
                  <td className="whitespace-nowrap">
                    {formatDate(d.remeasure_on)} {d.due && <Badge tone="yellow">Đến hạn</Badge>}
                  </td>
                  <td>
                    {d.conclusion ? (
                      <Badge tone={CONCLUSION[d.conclusion]?.tone}>{CONCLUSION[d.conclusion]?.label}</Badge>
                    ) : (
                      "—"
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
