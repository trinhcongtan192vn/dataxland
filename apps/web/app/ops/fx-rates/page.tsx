"use client";

// Tỷ giá nhập tay khi lấy tỷ giá Vietcombank lỗi (spec 01 §6, spec 05 §6.9). Ưu tiên hơn tỷ giá tự động cùng ngày.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, Field, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/tenant";

export default function FxRates() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [f, setF] = useState({ date: "", currency: "USD", rate_vnd: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const list = useQuery({ queryKey: ["fx"], queryFn: () => unwrap(api.GET("/v1/admin/fx-rates")) });
  const add = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/v1/admin/fx-rates", {
          body: { date: f.date, currency: f.currency, rate_vnd: Number(f.rate_vnd) },
        }),
      ),
    onSuccess: () => {
      setMsg({ ok: true, text: "Đã lưu; áp dụng ở lần chạy pipeline kế tiếp." });
      void qc.invalidateQueries({ queryKey: ["fx"] });
    },
    onError: (e) => setMsg({ ok: false, text: errorMessage(e) }),
  });
  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Tỷ giá"
        subtitle="Tỷ giá tự động lấy từ Vietcombank 18:30 hằng ngày; nhập tay khi nguồn lỗi"
      />
      {me?.staff_role === "data_lead" && (
        <form
          className="card mb-4 grid gap-3 sm:grid-cols-4 sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Field label="Ngày">
            <input
              className="input"
              type="date"
              required
              value={f.date}
              onChange={(e) => setF({ ...f, date: e.target.value })}
            />
          </Field>
          <Field label="Ngoại tệ">
            <input
              className="input"
              required
              pattern="[A-Z]{3}"
              value={f.currency}
              onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })}
            />
          </Field>
          <Field label="Tỷ giá bán ra (₫)">
            <input
              className="input"
              required
              inputMode="decimal"
              value={f.rate_vnd}
              onChange={(e) => setF({ ...f, rate_vnd: e.target.value })}
            />
          </Field>
          <button type="submit" className="btn-primary" disabled={add.isPending}>
            Lưu tỷ giá
          </button>
          {msg && (
            <p className={`text-sm sm:col-span-4 ${msg.ok ? "text-green-700" : "text-red-700"}`}>
              {msg.text}
            </p>
          )}
        </form>
      )}
      <div className="card">
        <h2 className="mb-2 font-semibold">Tỷ giá đã nhập tay</h2>
        {list.isLoading ? (
          <Spinner />
        ) : list.error ? (
          <ErrorBox error={list.error} />
        ) : (list.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa có.</p>
        ) : (
          <table className="table">
            <tbody>
              {(list.data ?? []).map((r) => (
                <tr key={`${r.date}-${r.currency}`}>
                  <td>{formatDate(String(r.date))}</td>
                  <td>{String(r.currency)}</td>
                  <td className="text-right tabular-nums">{Number(r.rate_vnd).toLocaleString("vi-VN")} ₫</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
