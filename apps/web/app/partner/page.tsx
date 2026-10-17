"use client";

// Trang agency (spec 06 §8, FR-AGY-01, FR-AGY-02): bảng các shop đã cấp quyền, sắp theo số cờ rồi chi tiêu.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Value } from "@/components/money";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatAsOf } from "@/lib/format";

export default function PartnerHome() {
  const q = useQuery({
    queryKey: ["partner-tenants"],
    queryFn: () => unwrap(api.GET("/v1/partner/tenants")),
  });
  return (
    <div>
      <PageHeader
        title="Các shop bạn quản lý"
        subtitle="Chi tiêu tháng này, tiến độ ngân sách, ROAS thật và cờ cần chú ý"
      />
      <div className="card overflow-x-auto">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorBox error={q.error} />
        ) : (q.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">Chưa shop nào cấp quyền cho agency của bạn.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Shop</th>
                <th className="text-right">Chi quảng cáo tháng này</th>
                <th className="text-right">Tiến độ ngân sách</th>
                <th className="text-right">ROAS thật</th>
                <th>Cờ cần chú ý</th>
                <th>Cập nhật</th>
              </tr>
            </thead>
            <tbody>
              {(q.data ?? []).map((t) => (
                <tr key={t.tenant_id}>
                  <td>
                    <Link
                      className="font-medium text-brand-600 hover:underline"
                      href={`/partner/${t.tenant_id}?t=${t.tenant_id}`}
                    >
                      {t.name}
                    </Link>
                    {t.error && <div className="text-xs text-red-700">{t.error}</div>}
                  </td>
                  <td className="text-right">
                    <Value value={t.ad_spend_mtd} unit="VND" />
                  </td>
                  <td className="text-right">
                    <span
                      className={
                        t.budget_pacing && t.budget_pacing > 1.15 ? "font-semibold text-red-700" : ""
                      }
                    >
                      <Value value={t.budget_pacing} unit="ratio" />
                    </span>
                  </td>
                  <td className="text-right">
                    <Value value={t.roas_blended} unit="ratio" />
                  </td>
                  <td>
                    {t.flags.length === 0 ? (
                      <span className="text-xs text-green-700">Không có</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {t.flags.map((f, i) => (
                          <Badge key={i} tone="red">
                            {String((f as { message_vi?: string }).message_vi ?? "")}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="text-xs">{formatAsOf(t.data_as_of)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
