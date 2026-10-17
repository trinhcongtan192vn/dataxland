"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { Badge, ErrorBox, Spinner } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { platformLabel } from "@/lib/metrics";

const KIND: Record<string, string> = { env: "Biến môi trường", secret: "Secret", web_env: "Biến của web" };

export default function IntegrationGuide() {
  const { key } = useParams<{ key: string }>();
  const q = useQuery({
    queryKey: ["integration", key],
    queryFn: () => unwrap(api.GET("/v1/ops/integrations/{key}", { params: { path: { key } } })),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const p = q.data;
  if (!p) return null;
  return (
    <div>
      <div className="mb-2 text-sm">
        <Link className="text-brand-600 hover:underline" href="/ops/integrations">
          ← Hướng dẫn tích hợp
        </Link>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <article className="card prose-dx text-sm">
          <ReactMarkdown>{p.guide_md}</ReactMarkdown>
        </article>
        <aside className="space-y-4">
          <div className="card">
            <h2 className="mb-2 font-semibold">Trạng thái cấu hình</h2>
            <ul className="space-y-2 text-sm">
              {p.checks.map((c) => (
                <li key={c.name}>
                  <div className="flex items-center justify-between gap-2">
                    <code className="text-xs">{c.name}</code>
                    {c.configured === null ? (
                      <Badge>Kiểm ở web</Badge>
                    ) : c.configured ? (
                      <Badge tone="green">Đã cấu hình</Badge>
                    ) : (
                      <Badge tone={c.required ? "red" : "gray"}>
                        {c.required ? "Thiếu" : "Chưa có (tùy chọn)"}
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-slate-500">
                    {KIND[c.kind] ?? c.kind} · {c.label_vi}
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-500">
              Màn này không bao giờ hiện giá trị của khóa hay token.
            </p>
          </div>
          {p.tenants.length > 0 && (
            <div className="card">
              <h2 className="mb-2 font-semibold">Nguồn của khách</h2>
              <ul className="space-y-2 text-sm">
                {p.tenants.map((t) => (
                  <li key={`${t.tenant_id}-${t.source}-${t.account_id}`}>
                    <Link className="text-brand-600 hover:underline" href={`/ops/tenants/${t.tenant_id}`}>
                      {t.tenant_name}
                    </Link>{" "}
                    · {platformLabel(t.source)} {t.account_id}
                    <div className="text-xs">
                      {t.secret_configured === false && <Badge tone="red">Chưa có token</Badge>}
                      {t.secret_configured === true && <Badge tone="green">Có token</Badge>}
                      {t.connected_at && (
                        <span className="ml-1 text-slate-500">kết nối {formatDateTime(t.connected_at)}</span>
                      )}
                      {t.last_error_code && <span className="ml-1 text-red-700">{t.last_error_code}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
