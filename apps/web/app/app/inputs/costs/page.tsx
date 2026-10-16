"use client";

// Giá vốn theo SKU (spec 06 §6, FR-INP-01..03): bảng sửa trực tiếp, thêm dòng có ngày hiệu lực, tải mẫu Excel,
// tải file lên với bảng lỗi theo dòng, hộp "SKU chưa có giá vốn".
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Badge, ErrorBox, Field, PageHeader, Spinner } from "@/components/ui";
import { ApiError, api, errorMessage, rawFetch, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDate, formatVnd } from "@/lib/format";
import { can, useTenant } from "@/lib/tenant";

type Cost = components["schemas"]["CostOut"];
type Upload = components["schemas"]["UploadOut"];

function todayVn(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

function parseMoney(s: string): number | null {
  const clean = s.replace(/[.\s₫]/g, "").replace(",", ".");
  const n = Number(clean);
  return clean && Number.isFinite(n) && n >= 0 ? n : null;
}

function CostRow({ c, editable, onSaved }: { c: Cost; editable: boolean; onSaved: () => void }) {
  const [value, setValue] = useState(String(c.unit_cost_vnd));
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      const v = parseMoney(value);
      if (v === null) throw new Error("Giá vốn phải là số không âm");
      return unwrap(
        api.PUT("/v1/inputs/product-costs/{cost_id}", {
          params: { path: { cost_id: c.id } },
          body: { unit_cost_vnd: v },
        }),
      );
    },
    onSuccess: () => {
      setErr(null);
      onSaved();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/v1/inputs/product-costs/{cost_id}", { params: { path: { cost_id: c.id } } })),
    onSuccess: onSaved,
    onError: (e) => setErr(errorMessage(e)),
  });
  const dirty = value !== String(c.unit_cost_vnd);
  return (
    <tr>
      <td className="font-mono text-xs">{c.seller_sku}</td>
      <td className="text-right">
        {editable ? (
          <input
            className="input w-36 text-right"
            inputMode="numeric"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && dirty && save.mutate()}
            aria-label={`Giá vốn ${c.seller_sku}`}
          />
        ) : (
          formatVnd(c.unit_cost_vnd)
        )}
      </td>
      <td>{formatDate(c.valid_from)}</td>
      <td>{c.valid_to ? formatDate(c.valid_to) : <Badge tone="green">Đang áp dụng</Badge>}</td>
      <td className="text-slate-500">{c.note}</td>
      <td className="whitespace-nowrap text-right">
        {editable && dirty && (
          <button
            type="button"
            className="btn-primary px-2 py-1 text-xs"
            onClick={() => save.mutate()}
            disabled={save.isPending}
          >
            Lưu
          </button>
        )}
        {editable && (
          <button
            type="button"
            className="ml-2 text-xs text-red-600 hover:underline"
            onClick={() =>
              confirm(`Xóa giá vốn ${c.seller_sku} từ ${formatDate(c.valid_from)}?`) && del.mutate()
            }
          >
            Xóa
          </button>
        )}
        {err && <div className="text-xs text-red-700">{err}</div>}
      </td>
    </tr>
  );
}

export default function CostsPage() {
  const { tenantId, tenant } = useTenant();
  const editable = can(tenant, "inputs.write");
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ seller_sku: "", unit_cost_vnd: "", valid_from: todayVn(), note: "" });
  const [formErr, setFormErr] = useState<string | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const costs = useQuery({
    queryKey: ["costs", tenantId],
    queryFn: () => unwrap(api.GET("/v1/inputs/product-costs")),
    enabled: !!tenantId,
  });
  const missing = useQuery({
    queryKey: ["missing-costs", tenantId],
    queryFn: () => unwrap(api.GET("/v1/inputs/product-costs/missing")),
    enabled: !!tenantId,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["costs", tenantId] });
    void qc.invalidateQueries({ queryKey: ["missing-costs", tenantId] });
  };
  const add = useMutation({
    mutationFn: async () => {
      const v = parseMoney(form.unit_cost_vnd);
      if (!form.seller_sku.trim()) throw new Error("Nhập SKU");
      if (v === null) throw new Error("Giá vốn phải là số không âm");
      return unwrap(
        api.POST("/v1/inputs/product-costs", {
          body: {
            seller_sku: form.seller_sku.trim(),
            unit_cost_vnd: v,
            valid_from: form.valid_from,
            note: form.note || null,
          },
        }),
      );
    },
    onSuccess: () => {
      setForm({ seller_sku: "", unit_cost_vnd: "", valid_from: todayVn(), note: "" });
      setFormErr(null);
      refresh();
    },
    onError: (e) => setFormErr(errorMessage(e)),
  });

  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return (costs.data ?? []).filter((c) => !f || c.seller_sku.toLowerCase().includes(f));
  }, [costs.data, filter]);

  const downloadTemplate = async () => {
    const r = await rawFetch("/v1/inputs/product-costs/template");
    if (!r.ok) return setUploadErr("Không tải được file mẫu");
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "gia-von-mau.xlsx";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const onFile = async (file: File) => {
    setUploading(true);
    setUpload(null);
    setUploadErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await rawFetch("/v1/inputs/product-costs/upload", { method: "POST", body: fd });
      const body = await r.json();
      if (!r.ok)
        throw new ApiError(r.status, body.code ?? "UPLOAD_FAILED", body.detail ?? "Không đọc được file");
      setUpload(body as Upload);
      refresh();
    } catch (e) {
      setUploadErr(errorMessage(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Giá vốn"
        subtitle="Giá vốn theo SKU và ngày hiệu lực; dùng để tính lãi thật"
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={downloadTemplate}>
              Tải file mẫu Excel
            </button>
            {editable && (
              <label className="btn-primary cursor-pointer">
                {uploading ? "Đang tải lên…" : "Tải file lên"}
                <input
                  type="file"
                  accept=".xlsx,.csv"
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void onFile(f);
                    e.target.value = "";
                  }}
                />
              </label>
            )}
          </>
        }
      />

      {uploadErr && (
        <div className="mb-4">
          <ErrorBox error={new Error(uploadErr)} />
        </div>
      )}
      {upload && (
        <div className="card mb-4">
          <p className="text-sm">
            Đã nhận <strong>{upload.rows_ok}</strong>/{upload.rows_total} dòng
            {upload.rows_error > 0 && (
              <>
                , <strong className="text-red-700">{upload.rows_error}</strong> dòng lỗi
              </>
            )}
            .
          </p>
          {upload.errors.length > 0 && (
            <table className="table mt-3">
              <thead>
                <tr>
                  <th>Dòng</th>
                  <th>Cột</th>
                  <th>Lý do</th>
                </tr>
              </thead>
              <tbody>
                {upload.errors.map((e, i) => (
                  <tr key={i} className={e.warning ? "bg-amber-50" : "bg-red-50"}>
                    <td>{e.row}</td>
                    <td>{e.column}</td>
                    <td>
                      {e.warning && <Badge tone="yellow">Cảnh báo</Badge>} {e.message_vi}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {(missing.data?.sku_count ?? 0) > 0 && (
        <div className="card mb-4 border-amber-200 bg-amber-50">
          <h2 className="mb-2 font-semibold text-amber-900">
            {missing.data?.sku_count} SKU chưa có giá vốn, chiếm {formatVnd(missing.data?.revenue_vnd)} doanh
            thu 30 ngày
          </h2>
          <ul className="space-y-1 text-sm">
            {missing.data?.items.slice(0, 20).map((m) => (
              <li key={m.seller_sku} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{m.seller_sku}</span>
                <span className="text-slate-600">{m.product_name}</span>
                <span className="text-slate-500">· {formatVnd(m.net_revenue_30d)}</span>
                {editable && (
                  <button
                    type="button"
                    className="text-brand-600 hover:underline"
                    onClick={() => {
                      setForm((f) => ({ ...f, seller_sku: m.seller_sku }));
                      document.getElementById("cost-amount")?.focus();
                    }}
                  >
                    Điền nhanh
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {editable && (
        <form
          className="card mb-4 grid gap-3 sm:grid-cols-5 sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Field label="SKU">
            <input
              className="input"
              value={form.seller_sku}
              onChange={(e) => setForm({ ...form, seller_sku: e.target.value })}
            />
          </Field>
          <Field label="Giá vốn (₫)">
            <input
              id="cost-amount"
              className="input"
              inputMode="numeric"
              value={form.unit_cost_vnd}
              onChange={(e) => setForm({ ...form, unit_cost_vnd: e.target.value })}
            />
          </Field>
          <Field label="Áp dụng từ ngày">
            <input
              className="input"
              type="date"
              value={form.valid_from}
              onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
            />
          </Field>
          <Field label="Ghi chú">
            <input
              className="input"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </Field>
          <button type="submit" className="btn-primary" disabled={add.isPending}>
            Thêm giá vốn
          </button>
          {formErr && <p className="text-sm text-red-700 sm:col-span-5">{formErr}</p>}
        </form>
      )}

      <div className="card">
        <input
          className="input mb-3 max-w-xs"
          placeholder="Lọc theo SKU"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {costs.isLoading ? (
          <Spinner />
        ) : costs.error ? (
          <ErrorBox error={costs.error} onRetry={() => costs.refetch()} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có giá vốn nào.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th className="text-right">Giá vốn</th>
                  <th>Từ ngày</th>
                  <th>Đến ngày</th>
                  <th>Ghi chú</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <CostRow key={`${c.id}-${c.updated_at}`} c={c} editable={editable} onSaved={refresh} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Giá vốn mới sẽ được áp dụng sau lần cập nhật dữ liệu kế tiếp (khoảng 10–20 phút).
        </p>
      </div>
    </div>
  );
}
