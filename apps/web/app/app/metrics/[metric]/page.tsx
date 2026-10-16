"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { ErrorBox, PageHeader, Spinner, TextLink } from "@/components/ui";
import { api, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { useTenant, useTenantHref } from "@/lib/tenant";

const UNIT: Record<string, string> = {
  VND: "Đồng (₫)",
  ratio: "Tỷ số (x)",
  percent: "Phần trăm (%)",
  count: "Số lượng",
};
const TYPE: Record<string, string> = { simple: "Chỉ số gốc", ratio: "Tỷ lệ", derived: "Chỉ số ghép" };
const GRAIN: Record<string, string> = { day: "ngày", week: "tuần", month: "tháng" };

export default function MetricDetail() {
  const { metric } = useParams<{ metric: string }>();
  const { tenantId } = useTenant();
  const href = useTenantHref();
  const q = useQuery({
    queryKey: ["metric", tenantId, metric],
    queryFn: () => unwrap(api.GET("/v1/metrics/{metric}", { params: { path: { metric } } })),
    enabled: !!tenantId,
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const m = q.data;
  if (!m) return null;
  const history = (m.history ?? []) as { version: string; date: string; change_vi: string }[];
  return (
    <div className="max-w-3xl">
      <div className="mb-2 text-sm">
        <TextLink href={href("/app/metrics")}>← Sổ tay chỉ số</TextLink>
      </div>
      <PageHeader title={m.name_vi} subtitle={`${m.metric} · phiên bản ${m.version}`} />
      <div className="card space-y-4 text-sm">
        <p className="text-base">{m.description_vi}</p>
        {m.formula_vi && (
          <div>
            <h2 className="font-semibold text-slate-700">Cách tính</h2>
            <p>{m.formula_vi}</p>
          </div>
        )}
        {m.source_note_vi && (
          <div>
            <h2 className="font-semibold text-slate-700">Nguồn dữ liệu</h2>
            <p>{m.source_note_vi}</p>
          </div>
        )}
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-slate-500">Loại</dt>
            <dd>{TYPE[m.type] ?? m.type}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Đơn vị</dt>
            <dd>{UNIT[m.unit] ?? m.unit}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Hướng tốt</dt>
            <dd>
              {m.good_direction === "up"
                ? "Càng cao càng tốt"
                : m.good_direction === "down"
                  ? "Càng thấp càng tốt"
                  : "Tùy bối cảnh"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Xem theo</dt>
            <dd>{m.time_grains.map((g) => GRAIN[g] ?? g).join(", ")}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-slate-500">Cắt được theo</dt>
            <dd>
              {(m.dimensions as { name: string; name_vi: string }[])
                .filter((d) => d.name !== "date")
                .map((d) => d.name_vi)
                .join(", ") || "—"}
            </dd>
          </div>
          {m.synonyms_vi.length > 0 && (
            <div className="sm:col-span-2">
              <dt className="text-slate-500">Còn gọi là</dt>
              <dd>{m.synonyms_vi.join(", ")}</dd>
            </div>
          )}
        </dl>
        <div>
          <h2 className="mb-2 font-semibold text-slate-700">Lịch sử thay đổi</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Phiên bản</th>
                <th>Ngày</th>
                <th>Thay đổi</th>
              </tr>
            </thead>
            <tbody>
              {[...history].reverse().map((h) => (
                <tr key={h.version}>
                  <td>{h.version}</td>
                  <td>{formatDate(h.date)}</td>
                  <td>{h.change_vi}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
