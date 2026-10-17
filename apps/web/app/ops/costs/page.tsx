"use client";

// Chi phí và giờ người theo khách (FR-OPS-06, spec 04 §6): GCP từ billing export (job `gcp_costs`), hóa đơn Windsor
// và Claude chia theo khách, giờ người nhập tay.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatVnd } from "@/lib/format";
import { useMe } from "@/lib/tenant";

const ITEM_VI: Record<string, string> = { gcp: "GCP", windsor: "Windsor", ai: "Claude" };

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function HoursCell({
  tenantId,
  month,
  hours,
  editable,
  onSaved,
}: {
  tenantId: string;
  month: string;
  hours: number | null | undefined;
  editable: boolean;
  onSaved: () => void;
}) {
  const [value, setValue] = useState(hours != null ? String(hours) : "");
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const n = Number(value.replace(",", "."));
      if (!value.trim() || !Number.isFinite(n) || n < 0) throw new Error("Số giờ không hợp lệ");
      return unwrap(
        api.PUT("/v1/ops/tenants/{tenant_id}/hours", {
          params: { path: { tenant_id: tenantId } },
          body: { month, hours: n },
        }),
      );
    },
    onSuccess: () => {
      setErr(null);
      onSaved();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  if (!editable) return <>{hours != null ? `${hours} giờ` : "—"}</>;
  return (
    <input
      className={`input w-24 text-right ${err ? "border-red-500" : ""}`}
      inputMode="decimal"
      value={value}
      placeholder="—"
      title={err ?? undefined}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => value !== (hours != null ? String(hours) : "") && save.mutate()}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      aria-label={`Giờ người ${tenantId}`}
    />
  );
}

export default function OpsCosts() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const canWrite = me?.staff_role === "data_lead";
  const [month, setMonth] = useState(thisMonth());
  const [item, setItem] = useState<"windsor" | "claude">("windsor");
  const [amount, setAmount] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const q = useQuery({
    queryKey: ["ops-costs", month],
    queryFn: () => unwrap(api.GET("/v1/ops/costs", { params: { query: { month } } })),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["ops-costs", month] });
  const allocate = useMutation({
    mutationFn: () => {
      const n = Number(amount.replace(/[.\s₫]/g, ""));
      if (!amount.trim() || !Number.isFinite(n) || n < 0) throw new Error("Số tiền không hợp lệ");
      return unwrap(api.POST("/v1/ops/costs/allocate", { body: { month, item, amount_vnd: n } }));
    },
    onSuccess: (d) => {
      const n = Object.keys((d as { allocated?: Record<string, number> }).allocated ?? {}).length;
      setMsg({ ok: true, text: `Đã chia hóa đơn cho ${n} khách.` });
      setAmount("");
      refresh();
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  const rows = q.data ?? [];
  const items = [...new Set(["gcp", "windsor", "ai", ...rows.flatMap((r) => Object.keys(r.items))])];
  const total = rows.reduce((s, r) => s + r.total_vnd, 0);

  return (
    <div>
      <PageHeader
        title="Chi phí theo khách"
        subtitle="GCP tự nạp mỗi ngày từ billing export theo nhãn tenant_id; Windsor và Claude chia từ hóa đơn tháng"
        actions={
          <input
            type="month"
            className="input w-auto"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            aria-label="Tháng"
          />
        }
      />
      {canWrite && (
        <div className="card mb-4 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="label">Hóa đơn</span>
            <select
              className="input w-auto"
              value={item}
              onChange={(e) => setItem(e.target.value as "windsor" | "claude")}
            >
              <option value="windsor">Windsor (chia theo số nguồn Windsor)</option>
              <option value="claude">Claude (chia theo mức dùng AI đã ghi)</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="label">Số tiền tháng (₫)</span>
            <input
              className="input w-44 text-right"
              inputMode="numeric"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={allocate.isPending}
            onClick={() => allocate.mutate()}
          >
            Chia cho khách
          </button>
          {msg && <p className={`text-sm ${msg.ok ? "text-green-700" : "text-red-700"}`}>{msg.text}</p>}
        </div>
      )}
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
                {items.map((i) => (
                  <th key={i} className="text-right">
                    {ITEM_VI[i] ?? i}
                  </th>
                ))}
                <th className="text-right">Tổng</th>
                <th className="text-right">Giờ người</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.tenant_id}>
                  <td>
                    <div className="font-medium">{r.name}</div>
                    <div className="text-xs text-slate-500">{r.tenant_id}</div>
                  </td>
                  {items.map((i) => (
                    <td key={i} className="text-right tabular-nums">
                      {r.items[i] != null ? formatVnd(r.items[i]) : "—"}
                    </td>
                  ))}
                  <td className="text-right font-medium tabular-nums">{formatVnd(r.total_vnd)}</td>
                  <td className="text-right">
                    <HoursCell
                      key={`${r.tenant_id}-${month}-${r.hours ?? ""}`}
                      tenantId={r.tenant_id}
                      month={month}
                      hours={r.hours}
                      editable={canWrite}
                      onSaved={refresh}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="font-semibold">Tổng</td>
                {items.map((i) => (
                  <td key={i} className="text-right tabular-nums">
                    {formatVnd(rows.reduce((s, r) => s + (r.items[i] ?? 0), 0))}
                  </td>
                ))}
                <td className="text-right font-semibold tabular-nums">{formatVnd(total)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Claude: trước khi chia hóa đơn, cột là ước tính từ số token của hỏi đáp và agent. Chia hóa đơn thật
          sẽ thay số ước tính. GCP cần cấu hình GCP_BILLING_EXPORT_TABLE cho job gcp_costs.
        </p>
      </div>
    </div>
  );
}
