"use client";

// Agency được xem dữ liệu (spec 06 §9, spec 05 §5.3): owner cấp và thu quyền; thu quyền có hiệu lực ngay.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useTenant } from "@/lib/tenant";

export default function PartnersPage() {
  const { tenantId } = useTenant();
  const qc = useQueryClient();
  const [pick, setPick] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const partners = useQuery({
    queryKey: ["partners", tenantId],
    queryFn: () => unwrap(api.GET("/v1/partners")),
    enabled: !!tenantId,
  });
  const grants = useQuery({
    queryKey: ["grants", tenantId],
    queryFn: () => unwrap(api.GET("/v1/partners/grants")),
    enabled: !!tenantId,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["grants", tenantId] });
  const grant = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/partners/grants", { body: { partner_id: pick } })),
    onSuccess: () => {
      setPick("");
      setErr(null);
      refresh();
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/v1/partners/grants/{grant_id}", { params: { path: { grant_id: id } } })),
    onSuccess: refresh,
    onError: (e) => setErr(errorMessage(e)),
  });
  const granted = new Set((grants.data ?? []).map((g) => g.partner_id));

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Agency"
        subtitle="Cho agency quảng cáo xem số liệu quảng cáo và ngân sách của shop"
      />
      <div className="card mb-4 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="label">Cấp quyền cho agency</span>
          <select className="input" value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Chọn agency…</option>
            {(partners.data ?? [])
              .filter((p) => !granted.has(p.partner_id))
              .map((p) => (
                <option key={p.partner_id} value={p.partner_id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
        <button
          type="button"
          className="btn-primary"
          disabled={!pick || grant.isPending}
          onClick={() => grant.mutate()}
        >
          Cấp quyền
        </button>
        {err && <p className="w-full text-sm text-red-700">{err}</p>}
      </div>
      <div className="card">
        {grants.isLoading ? (
          <Spinner />
        ) : grants.error ? (
          <ErrorBox error={grants.error} />
        ) : (grants.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa agency nào được xem dữ liệu.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Agency</th>
                <th>Cấp lúc</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {grants.data?.map((g) => (
                <tr key={g.id}>
                  <td>{g.partner_name}</td>
                  <td>{formatDateTime(g.granted_at)}</td>
                  <td className="text-right">
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() =>
                        confirm(`Thu quyền của ${g.partner_name}? Agency mất quyền xem ngay.`) &&
                        revoke.mutate(g.id)
                      }
                    >
                      Thu quyền
                    </button>
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
