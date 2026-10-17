"use client";

// Hướng dẫn tích hợp (ADR 0001): trạng thái đã/chưa cấu hình từng biến và secret, không bao giờ hiện giá trị.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";

const CAT: Record<string, string> = {
  marketplace: "Sàn thương mại điện tử",
  ads: "Quảng cáo",
  messaging: "Nhắn tin",
  auth: "Đăng nhập",
  email: "Email",
  reference: "Dữ liệu tham chiếu",
  warehouse: "Kho dữ liệu",
  ai: "AI",
};

export default function Integrations() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => unwrap(api.GET("/v1/ops/integrations")) });
  return (
    <div>
      <PageHeader
        title="Hướng dẫn tích hợp"
        subtitle="Cách lấy khóa, token và quyền của từng nền tảng; trạng thái cấu hình hiện tại"
      />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {(q.data ?? []).map((p) => {
            const missing = p.checks.filter((c) => c.required && c.configured === false);
            return (
              <Link
                key={p.key}
                href={`/ops/integrations/${p.key}`}
                className="card block hover:border-brand-500"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">{p.name_vi}</div>
                    <div className="text-xs text-slate-500">{CAT[p.category] ?? p.category}</div>
                  </div>
                  {p.ready ? (
                    <Badge tone="green">Đã cấu hình</Badge>
                  ) : (
                    <Badge tone="yellow">Thiếu {missing.length}</Badge>
                  )}
                </div>
                {p.tenants.length > 0 && (
                  <p className="mt-2 text-xs text-slate-500">
                    {p.tenants.length} nguồn của khách dùng nền tảng này
                    {p.tenants.some((t) => t.secret_configured === false) && (
                      <span className="text-red-700"> · có nguồn chưa có token</span>
                    )}
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
